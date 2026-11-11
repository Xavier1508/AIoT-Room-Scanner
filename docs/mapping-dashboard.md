# Mapping dashboard (PC) — architecture and workflow

The project deliberately separates two web applications:

| Application | Host | Purpose |
|---|---|---|
| Diagnostic/manual | ESP32 | Safety, manual jog, live sensor status, OTA |
| Mapping/deep-learning | PC | Calibration, scan orchestration, 3D point cloud, dataset export |

The ESP32 does not train models and does not serve large point clouds. It
remains the real-time controller; the PC stores scans and renders the 3D view.

## Start the PC dashboard

From the project root, using the existing PlatformIO Python:

```powershell
$py = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
Push-Location .\tools\mapping
& $py -B .\mapping_server.py --host 127.0.0.1 --port 8000
Pop-Location
```

Open `http://127.0.0.1:8000/`.

The server reads `tools/ops/device.local.json` (gitignored) and proxies the
ESP32 API server-side. ESP32 Basic-auth credentials are never sent to the
browser. Default bind is loopback only; do not port-forward this dashboard.

### Restart and auto-start

There are two independent web applications:

- **ESP32 dashboard** `http://<ESP-IP>/` — served by the board itself. It starts
  automatically after boot when Wi-Fi connects. If the board is off, brownout
  looping, or Wi-Fi is down, this page is down; the PC cannot keep it alive.
- **PC mapping dashboard** `http://127.0.0.1:8000/` — served by the PC Python
  process. It stays up even when the ESP32 is offline (health panel shows an
  error), but it stops if its terminal is closed or the process crashes.

For a restart-on-crash supervisor, run:

```powershell
.\tools\ops\start-mapping.cmd
```

Keep the window open. The supervisor restarts `mapping_server.py` after an exit.
To start it automatically at Windows logon, create a shortcut to
`tools\ops\start-mapping.cmd` in `shell:startup` (or a Task Scheduler entry).
That is a user-level system change; do it deliberately. Do not expose the
dashboard to the internet.

If the ESP32 IP changes after DHCP, the PC mapping health panel will time out
even though the PC page is up. Find the new IP from the router DHCP list or
connect USB and run `device.py status`. `aiot-room.local` is the mDNS fallback;
if it does not resolve, the board is likely offline rather than merely on a new
IP.

## Calibration

1. Start the ESP32 sensors and point HC/ToF at the same flat target.
2. In the PC dashboard, open **Calibration**.
3. Enter the measured distance from the HC reference face, choose 10 samples,
   and capture.
4. Repeat at 30, 50, 75, 100, 150 and 250 cm.
5. The JSON record is stored in `research/mapping/calibration.json`.
   `hc_offset_mm` and `tof_offset_mm` are used by the scan pipeline.

HC is the reference sensor. The ToF lens is physically ahead of the HC
reference face, so its raw distance is shorter; the calibration offset corrects
that fixed mounting difference. HLK is presence/proximity only and is not
calibrated to match HC/ToF distance.

## Scan

The ESP32 must be in `IDLE` or `PARKED` with sensors running. The PC sends
`scan_mode_start`, then explicit 5-degree/25-microsecond nudges. The scan is
**sequential** to avoid overlapping actuator current: stepper moves to the yaw,
is **released during the vertical servo sweep** to save holding current, then
re-held before the next yaw. The servo attaches only after the stepper settles,
moves in 25 µs steps with a 0.1 s delay, returns to its 800 µs base, detaches,
and the next column waits for a 0.5 s cooldown. Firmware rejects servo attach
while the stepper is moving and stepper motion while the servo is attached. The
PC also requires a power-confirmation checkbox before starting. Firmware
enforces the mapping envelope:

- stepper: `-513..+513` half-steps (about +/-45.1 degrees nominal)
- servo: `500..950` microseconds (500 = up, 950 = down)

The UI/API exposes a bounded validation mode: yaw step 5/10 degrees, yaw limit
±5/10/15/20/30/45/50/55/60 degrees, tilt step 25/50 microseconds, tilt min/max
inside 500..950 microseconds, servo step delay 0.05–0.5 s, column cooldown
0–5 s, and sample interval 50–1000 ms. Presets: Validation ±10°, Coarse ±60°,
Fine ±60°. The default full grid is yaw -60..+60 degrees in 5-degree steps and
tilt 500..950 microseconds in 25-microsecond steps. A coarse run uses 10
degrees and 50 microseconds; a denser room run uses 10 degrees and 25
microseconds.

**Measured power strategy (2026-11-09):** two early scans browned out when the
servo moved quickly with the stepper held. With the 0.1 s servo step delay,
stepper released during the sweep, 0.5 s cooldown and park-before-detach, the
validation scan completed 30/30 points and the coarse full scan completed
110/110 points (99 valid) with no new brownout. Faster timing or holding the
stepper during the sweep can brown out again; this is a software timing
mitigation on the existing 9 V/3 A supply, not a hardware power fix.

**ToF watchdog and near-reflector flag (0.7.3):** `0.7.3-tof-obstruction` keeps
the 0.6.1 suspend/recover watchdog, removes the XSHUT hard reset from the main
loop, and adds `near_reflector`/`near_count`. If ToF is valid <500 mm while HC
>1000 mm for 10 samples, health becomes `OBSTRUCTED` and the dashboard shows
`NEAR REFLECTOR`. The fixed 10–16 cm return was the protective lens cover;
after it was removed, ToF reads ~2.4 m with `near_reflector=false` and health
`OK`. The full scan uses **445 ToF + 27 HC** points. An 8×8 ROI test produced
`wrap_target_fail` and was reverted. The flag remains as a regression guard if
the lens/mount is obstructed again.

Each point waits for a dwell, takes several status samples, and records median
HC/ToF/HLK values, valid rates, ToF status, and a calibrated range. The scan is
saved under:

```text
research/mapping/scans/<UTC>/
  metadata.json
  points.csv
  samples.jsonl
```

The point cloud is a geometric back-projection, not a deep-learning result.
The provisional tilt curve is 10 microseconds/degree around 725 microseconds;
replace it with a measured `servo_curve` in `calibration.json` before trusting
absolute geometry.

## HLK presence and buzzer

The LD2410C is a wide-beam presence radar, not a mapping rangefinder. It is
muted while scan mode or actuator motion is active, and re-armed only when the
arm is stationary. The buzzer follows a parking-sensor ramp:

- silent above 75 cm
- slow beep at 75 cm
- faster as distance approaches the 30 cm blind-zone clamp
- 2-frame confirmation, energy gate and 10 cm hysteresis

HLK data during the scan is recorded but not used for geometry. After the scan,
the arm should stay parked so the HLK presence blob/arc can be placed in the 3D
viewer consistently.

## 3D viewer

The **Point Cloud 3D** tab shows two views side by side:

- **3D isometric:** cyan ToF points, orange HC points, blue estimated wall
  blocks, light-blue dashed `wall_edge` fragments, green estimated objects,
  magenta HLK presence dot and a green human capsule when presence is confirmed.
- **Top-down 2D:** the same points/blocks on a floor plan with a 0.5 m grid,
  sensor origin, effective FOV wedge, scale bar, red occluded sectors, numbered
  blocks, dashed distance leaders and a highlighted human box. Drag to pan,
  wheel or the **2D zoom** buttons to zoom; **Reset 2D** restores the view.

`reconstruct.py` removes near-field returns, then extracts continuous
axis-aligned wall lines first (the dashboard rotation control makes the walls
horizontal/vertical). This keeps a dense room perimeter from becoming one
room-sized object. Interior points are clustered in 3D so furniture separates
from the ceiling; a surface parallel to a wall and just outside it is treated
as the sloped-ceiling extension and hidden. Sparse or curved scans fall back to
the original 2D clustering. The blocks are **estimated** from one fixed
viewpoint; hidden sides are inferred.

**Yaw calibration and map rotation:** the values are per physical placement.
The full ToF scan `20261110T124935Z` uses **yaw scale 1.00** and **map
rotation 0.0°**: the measured right wall is at x=2.44 m, the bottom wall at
y=-1.06 m and the top wall at y=1.50 m, so the scan is already axis-aligned.
The older `20261109T205833Z` scan used the historical **0.76 / 10.7°** frame
(effective FOV ±45.6°). The **Yaw scale** and **Rotasi** inputs re-project
points/blocks live; manual labels are remapped to the nearest box. The chosen
values are kept in browser localStorage and in the room metadata when
annotations are saved. These are per-scan adjustments, not a measured servo
curve.

**Mirror Y (scan vs prior):** the scanner yaw axis is opposite the
hand-authored prior/2D frame, so without correction measured objects swap
top/bottom relative to the priors. The **Mirror Y** button flips the measured
scan vertically about the prior room-centre (`room.mirror_center_m`, currently
0.355 m) and leaves the priors fixed. It is **ON by default** and persisted per
scan as `room.mirror_y`; turning it off restores the raw sensor orientation.
This is a display/geometry correction, not a new scan. It is also applied by
the PLY and dataset exporters. In scan `20261110T184241Z`, the fan-sized object
#6 was inside the bed prior before the fix; with Mirror Y ON, #6 is at
`(0.806, 1.206)` top-centre and the bed-sized object #5 is at
`(1.427, -0.029)` on the bed side. Evidence: `mirror-on-full-map.png`,
`mirror-on-topdown-2d.png`, `mirror-off-topdown-2d.png` under
`analysis/mapping/dashboard-20261110T184241Z/`.

**Auto luruskan and wall-constrained objects:** `POST
/api/mapping/scans/{id}/auto-align` searches a bounded ±5° rotation and scores
measured walls by weighted angle residual, wall support, length, thickness,
wall count, and whether a large low object can be snapped to a wall. It also
penalizes extra/missing walls and large global rotations. The selected result
is saved as `room.map_rotation_deg` with the residual shown in the UI. For scan
`20261110T184241Z` it selected **-1.1°** with 3 walls and residual **1.61°**.
The **Objek lurus** toggle (`room.snap_wall_objects`, default ON) re-fits a
large low object to the nearest fitted wall angle within 30°, while small
objects keep PCA. Bed #5 is `bed`, `-1.2°`, `angle_source=wall_snap`; fan #6 is
`fan`, `81.8°`, `angle_source=pca`. The prior bed was removed, leaving **12
blocks** (3 measured walls + bed + fan + 7 priors). Final scan evidence:
`auto-align-bed-fan.png`, `auto-align-bed-fan-2d.png`,
`block-list-auto-align.png`.

**3D projection and axes:** the 3D view now uses +X right, +Y up and +Z up,
matching the 2D plan. The previous projection put +Y downward, which made the
3D view look vertically flipped. The default camera is an isometric view
(`viewYaw -0.65`, `viewPitch 0.55`); the **Top 3D** button switches to a
near-top view with X horizontal, Y vertical (plan) and Z height. The legend
below the map states the axis convention.

**WebGL 3D view:** the 3D panel is now a local Three.js 0.160 scene (vendored,
no CDN) with orbit/pan/zoom, camera presets **Top / Iso / Fit / Full**, layer
toggles for points, walls, priors, objects, labels and grid, click-to-select
box labels, a floor grid and a 2D-canvas fallback if WebGL is unavailable. The
**Demo** button activates all layers, sets the isometric camera and closes the
sidebar. The 2D editor remains a canvas because it is the precise
resize/prior editor.

**Dual-track occupancy estimate:** the HLK status exposes separate moving and
stationary distances/energies. When both are valid and separated by at least
**75 cm** (one default LD2410 distance gate), the dashboard draws **H1/H2**
markers with dashed range lines and radial uncertainty arcs, and labels the
occupancy as `2 target (estimasi)`. Closer targets merge into one marker. This
is an occupancy estimate from one radar; HLK has no angle and is not a true
people counter. Two side-by-side people at the same distance remain one marker.
The dashboard mirrors the point cloud with the same yaw-scale → rotation →
mirror order as reconstruction and the PLY exporter, and filters mount rows so
it displays the same 450 points as the scene export. The top-down canvas is
square and fits the measured room outline, with a 1 m scale bar.

**Scan direction:** the scan is labelled from **−60° on the chair side** →
fan → bed/wardrobe → **+60°**, clockwise. The top-down view draws the FOV
boundaries and `start −60° (kursi)` / `end +60° (kasur/lemari)` labels. The
commanded sweep is ±60°; at yaw scale 1.00 the displayed effective FOV is
±60° (the old scan at 0.76 showed ±45.6°).

**Near-field / mount guard:** returns closer than **40 cm** from the sensor
centre are excluded. Low returns below the sensor plane inside **75 cm** are
also treated as the table/arm edge that the downward servo sweep hits; this is
what caused the earlier blocks that appeared to hug the sensor. Below-floor
returns (`z < -5 cm`) are discarded too. A small thin tall cluster close to the
scanner is classified `mount` and hidden as a box. The full scan hides 29 mount
points and 78 sloped-ceiling points.

**Room prior overlay (per scan, optional):** the prior is stored per scan and
is not hard-coded. For the full scan `20261110T124935Z` the measured walls are
bottom `y=-1.06 m`, right `x=2.44 m` and top `y=1.50 m`; the left wall at
`x=-0.26 m` is assumed because the scanner sits in front of it. The resulting
outline is **2.70 × 2.56 m = 6.91 m²**, with the bathroom **2.25 m²** and total
**9.16 m²**. The plan frame is **sensor at (0,0), +X right, +Y up**:

- measured desk **1.20 × 1.05 × 0.87 m** at ~1.2 m
- measured bed **2.15 × 0.48 × 0.66 m** along the right wall
- measured fan **0.57 × 0.37 × 0.53 m** near the scanner
- prior-only wardrobe **0.70 × 0.60 × 2.00 m** at bottom-left
- prior-only chair **0.45 × 0.45 × 0.45 m** at top-left
- WC door on the **left wall** (red), exit door on the **right wall** (yellow)
- prior wall segment **0.12 × 2.56 × 2.4 m** on the assumed left wall
- UI colours: fan **purple**, desk **green**, WC door **red**, exit door
  **yellow**
- sensor rack on the desk edge at **77 cm**, looking right across the room

The measured desk/bed/fan boxes are labelled manual labels on measured points;
the wardrobe/chair/doors have zero measured points and are drawn dashed. The
prior can be toggled with **Prior**. Prior boxes are not measured data and are
excluded from training unless the user confirms them. The older
`20261109T205833Z` scan keeps its historical **0.76 / 10.7°** frame.

**Label readability and distances:** 3D block labels and 2D distance tags
scale up to 1.6× with zoom and never shrink below their base size. The page
uses the full desktop width; the map grid is responsive. Every block carries
`distance_m` and `nearest_m`; the top-down view draws dashed leaders with
`#n 2.27 m` tags, and the **Jarak** button toggles them.

**Selection and manual labelling:** the map now supports Blender/Unity-style
selection:

- **3D:** right-drag orbit, middle-drag pan, wheel zoom, left-drag box select,
  left-click box, Shift add, Alt subtract. **Through** selects all depths
  (x-ray); turn it off to use the camera-depth min/max range.
- **2D:** right-drag pan, wheel zoom, left-drag box select, left-click box.
- Selected points are highlighted white; the selection count is shown.
- **Label titik terpilih** stores point labels by stable `point_index`.
- **Buat box dari selection** fits a manual box to the selected points.
- Custom labels are free text with a datalist/colour catalog, not just a fixed
  dropdown.

Annotations are stored per scan in
`research/mapping/scans/<id>/annotations.json` and include labels, hidden,
merges, point labels, label catalog, manual/prior boxes, room outline and room
metadata. The current scan `20261110T184241Z` has measured labels `bed` (#5,
wall-snapped) and `fan` (#6, PCA), plus prior wardrobe, desk, chair, partition
and both doors. The prior bed was removed. The final map is 12 blocks:
3 measured walls + bed + fan + 7 priors. The 2.70×2.51 m room outline is the
prior rectangle aligned to the measured walls.

**3D object dataset:** `tools/mapping/ml/export_pointcloud.py` exports point
labels and object boxes:

```text
research/mapping/ml/pointcloud/<scan>/
  fan.csv / fan.npz
  objects.csv
  manifest.json
```

Export command (uses the TensorFlow/numpy venv):

```powershell
tools\mapping\ml\.venv\Scripts\python.exe tools/mapping/ml/export_pointcloud.py --scan 20261109T205833Z
```

Only point-labelled patches are training samples. Prior boxes with zero points
are scene priors, not measured training data.

Point labels are suitable for 3D object classification/segmentation. The HLK
`empty`/`human`/`non-human` time-series dataset remains a separate path.

**Human marker:** the **AI / Presence** tab polls the HLK rule at ~1.5 s. When
the rule confirms a target for 3 frames (valid HLK, `target_state>0`,
`energy>=40`, 30–600 cm), the 3D view draws a 1.7 m capsule at the HLK
distance/yaw and the top-down view draws a highlighted box plus a leader with
the live distance and confidence. The marker is suppressed during scan mode
and shown as `holding` for a few seconds after the target disappears. The
class is rule-based `human`; a future DL `non-human` prediction uses the same
marker in orange.

## Presence and AI panel

The **AI / Presence** tab shows:

- rule prediction (`empty`/`human`), confidence, distance, energy, reason and
  confirmation progress,
- actuator status from the HLK proximity buzzer (enabled/state/mute/count/
  last distance and energy),
- DL model metrics and a rule-vs-DL comparison table,
- a live energy/distance trend with per-frame state dots.

The panel shows both paths: the live rule prediction and the live DL result when
firmware `0.8.0` is running. The deployed model is the **v2 binary empty/human**
1D CNN (int8, 14,584 bytes) with **97.38% ± 5.24%** contiguous-block validation.
The older 8,040-byte model was not deployed because it scored 82.7% versus 100%
for `max(moving_energy)>0` on the same split. The rule remains the
buzzer/safety fallback; the panel is also the integration point for the future
3-class `empty`/`human`/`non-human` model.

## Deep learning boundary

The **Dataset** tab records HLK time-series frames for TinyML. It polls the
ESP32 at roughly 3–5 Hz and writes:

```text
research/mapping/ml/<UTC>-<label>/
  frames.jsonl
```

Use one label per session: `empty`, `human`, `non-human`, or activity labels
(`walking`, `sitting`, `standing`, `lying`). Record with the arm parked, not
during a scan. The CLI equivalent is:

```powershell
py -3 tools/mapping/ml/collect.py --label human --duration 60
```

Training runs on the PC:

```powershell
py -3 tools/mapping/ml/train.py --data research/mapping/ml --window 32 --stride 4 --cv-blocks 5
```

It trains a small 1D CNN, evaluates contiguous time blocks, and exports
`model.tflite`, `model_data.h`, `model_metadata.h`, labels, normalization and
metrics. ESP32 inference is integrated through **ESP_TF 2.1.1 / TFLite Micro**
and runs only when sensors are valid, the arm is parked and no scan/motion is
active; it needs ~6.4 s to fill a 32-frame window. A 64 KiB arena plus the
14,584-byte int8 model fits without PSRAM. The current scan still produces a
geometric HC/ToF point cloud; TinyML is for HLK presence, not point-cloud
geometry.

**Current ML v2:** the binary `empty vs human` dataset (5,576 frames, 1,379
windows) trained the deployed 1D CNN to **97.38% ± 5.24%** on contiguous
5-block validation; the older 8,040-byte model scored 82.7% and was not
deployed. The rule `max(moving_energy)>0` remains the buzzer/safety fallback;
the DL is a separate classifier shown in the AI/Presence tab. A future harder
target is human vs non-human or activity classification on a true held-out
session.

## Prior editor, block sidebar and dataset export

The **Point Cloud 3D** tab uses a **floating right-hand block sidebar** (a
fixed overlay, not a layout column) so the 3D/2D canvases keep the full card
width. It is closed by default; the floating `Blok / Prior (N)` button opens it
and the `×` button closes it. The panel overlays the right side of the map
without resizing it, and clicking a block opens the panel on the **Edit** tab.

- **Daftar / Edit tabs** keep the block list and the editor separate; clicking a
  block switches to **Edit** and shows its controls without scrolling the page.
- **Daftar** groups blocks by label (wall, fan, door-wc, bed, ...), keeps the
  global 1..N numbering used on the canvases, and has a label/source filter.
- The **selected summary** shows the number, label, source, distance, size and
  point count with the label colour.
- **Selection outline:** the selected box gets a white dashed outline, corner
  handles and a `SELECTED #n label` tag in 2D; the 3D view gets a white dashed
  edge loop.
- **Overlap selection:** non-wall boxes and smaller footprints win over wall
  surfaces, so a door embedded in a wall can be clicked directly. Clicking the same
  spot again cycles through overlapping boxes. The sidebar stack always selects
  the exact box by row.
- **Edit** contains: add prior, convert an auto box to an editable prior, delete
  a prior, 2D drag mode, step 5/10 cm, X/Y/Z nudge buttons, rotation buttons,
  numeric X/Y/Z/panjang/lebar/sudut fields and **Simpan prior**. Numbers are the
  primary editor: type a value and press **Enter** to save it directly. Z is
  clamped to `>= 0` (no box under the floor); priors are stored per scan in
  `annotations.json`.
- **2D one-side resize:** the selected box shows 8 white handles (4 corners +
  4 edge midpoints). Drag one handle and only that side/corner moves; the
  opposite side stays fixed, so the pivot and size change together. Selecting
  an auto box and dragging a handle automatically promotes it to a prior first.
  The white crosshair marks the true object centre/pivot; the dashed ray shows
  the local angle. A corner/edge label reports `L x W x angle` live.
- **Hapus is permanent:** auto-box Hapus writes the box id to the separate
  `removed` list in `annotations.json`, so **Reset** cannot bring objects 5/6/7
  back. Sembunyikan still uses the temporary `hidden` list; Reset clears
  `labels`, `hidden`, `merges` and point labels but keeps `removed` and priors.
- **Undo:** every successful save (drag, resize, nudge, numeric edit, label,
  delete, reset) pushes the previous annotation snapshot onto a bounded stack.
  **Ctrl+Z** or the **Undo (Ctrl+Z)** button restores it. Inputs keep native
  text undo while focused; after Enter the field blurs so global undo works.
- **Simpan 3D:** writes a self-contained ASCII PLY plus a JSON sidecar under
  `research/mapping/scenes/<scan>/<utc>.ply`. The PLY contains all filtered scan
  points (cyan ToF, orange HC) and every measured/prior box as 8 vertices +
  12 triangles, coloured by label. The sidecar records counts, yaw/rotation,
  mirror state/centre, wall-snap state, box geometry and the SHA-256 of the
  PLY. The status line shows the exact path.
- **Axis scale:** 2D and 3D draw thin numeric ticks (0.5 m in 2D, 1 m in 3D)
  and the selected-box panel shows the exact coordinates. The **Skala sumbu**
  checkbox toggles the ticks. Every save/nudge/resize/export action also shows a
  busy spinner and a success/error toast; static JS/HTML/CSS are served with
  `charset=utf-8` so UI text is not mojibaked.

**Dataset CSV export (Dataset tab):** pick a scan, enter a run label, mark
**Run bersih** when the scan/labels are ready for training, and export. The
exporter writes one folder per run under
`research/mapping/dataset/clean|dirty/<scan_id>/<run_utc>/`:

- `points.csv` — one row per scan point with raw HC/ToF/HLK values, calibrated
  `x_m/y_m/z_m`, `range_source`, `point_utc_est`, `point_label`, containing
  `object_label/object_id/object_source`, `prior_region/prior_label`,
  `is_mount`, `is_ceiling`, and sample aggregates (count, uptime, HLK median).
- `objects.csv` — one row per box with `is_measured`, `is_prior`, label/source,
  geometry, footprint, volume, room and calibration metadata, clean flag and
  notes.
- `manifest.json` / `manifest.csv` — run metadata, counts and SHA-256 hashes.
- `annotations.json` and `README.txt` — the exact labels/priors and column
  notes.
- `research/mapping/dataset/index.csv` — one row per export so clean and dirty
  runs can be found later. Prior boxes have `points=0` and are not training
  ground truth.

**Presence false-positive gate:** the HLK distance is compared with the current
ToF/HC wall distance. If HLK sees farther than the wall + 50 cm, the tracker
reports `beyond_wall`, clears the human marker immediately and the dashboard
draws a small orange `HLK beyond wall` diagnostic instead. A valid HLK target
with no `target_state` uses a shorter 2.5 s hold; three stable distance frames
are required. The **AI / Presence** tab has a **Clear presence** button and
shows the gate reason, wall distance, distance spread, per-track list and an
**estimasi target** badge. The dual-track heuristic uses the HLK moving and
stationary distances separately with a **75 cm** minimum separation; it is an
occupancy estimate, not a people counter.

## Endpoints

- `GET /api/mapping/health`
- `GET /api/mapping/presence`
- `GET /api/mapping/status`
- `POST /api/mapping/command`
- `POST /api/mapping/scan/start`
- `POST /api/mapping/scan/stop`
- `GET /api/mapping/scan/status`
- `GET /api/mapping/scans`
- `GET /api/mapping/scans/{id}/points`
- `GET /api/mapping/scans/{id}/reconstruct?yaw_scale=1.00&map_rotation=0.0&mirror_y=1&mirror_center=0.355`
- `GET /api/mapping/scans/{id}/annotations`
- `POST /api/mapping/scans/{id}/annotations`
- `POST /api/mapping/scans/{id}/auto-align` (body `{yaw_scale, mirror_y, mirror_center_m, search_min, search_max}`)
- `POST /api/mapping/scans/{id}/export`
- `POST /api/mapping/scans/{id}/scene` (body `{yaw_scale, map_rotation, mirror_y, mirror_center_m, snap_wall_objects}`; writes PLY + JSON)
- `GET /api/mapping/dataset`
- `POST /api/mapping/presence/reset`
- `GET /api/mapping/calibration`
- `POST /api/mapping/ml/start`
- `POST /api/mapping/ml/stop`
- `GET /api/mapping/ml/status`
- `POST /api/mapping/calibration/capture`

## Safety

- Scan mode does not move axes by itself; the PC sends each nudge.
- STOP on the ESP32 releases outputs and stops sensors/scan mode.
- A scan error stops scan mode, holds the stepper at its current position, and
  releases the servo if it is still attached. Cleanup never re-attaches the servo.
- Verify cable clearance before the first sweep. The yaw limit is a software
  choice, not a mechanical proof.
