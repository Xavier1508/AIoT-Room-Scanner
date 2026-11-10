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

**ToF watchdog (0.7.1):** ToF is valid at rest but remains unreliable during
servo movement and sometimes faults at rest. `0.7.1-scan60-safe` keeps the
0.6.1 suspend/recover watchdog, removes the XSHUT hard reset that could block
the main loop, and exposes `tof_recoveries`/`tof_stall_suspended`. The 0.7.1
room scans used HC fallback (169 HC vs 50 ToF in the dense scan). No ToF
reliability claim is made; a separate servo supply/shielding or sensor
replacement would be required.

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
  sensor origin, ±60° FOV wedge, scale bar, red occluded sectors, numbered
  blocks, dashed distance leaders and a highlighted human box.

`reconstruct.py` removes near-field returns, clusters points in the x/y plane,
splits a thick wall cluster at its largest along-wall gap, fits oriented
rectangles and extrudes them from the floor to the observed top. The blocks are
**estimated** from one fixed viewpoint; hidden sides are inferred.

**Near-field / mount guard:** returns closer than **40 cm** from the sensor
centre are excluded. Low returns below the sensor plane inside **75 cm** are
also treated as the table/arm edge that the downward servo sweep hits; this is
what caused the earlier blocks that appeared to hug the sensor. Below-floor
returns (`z < -5 cm`) are discarded too. The dense 0.7.1 scan now yields six
blocks (two wall segments, two `wall_edge`, the fan, one small object) instead
of one thick wall plus near-field artefacts.

**Distance annotations:** every block carries `distance_m` (centre) and
`nearest_m` (closest footprint corner). The top-down view draws a dashed
leader from the sensor origin with a `#n 2.27 m` tag; the 3D view shows the
distance in the selected block label. The **Jarak** button toggles all distance
leaders/tags so the map does not become too busy.

**Block list and manual annotation:** the table below the canvases lists each
block's number, colour, label, distance, size, height, point count and whether
the label is automatic or manual. Use the block selectors to:

- apply a label (`wall`, `wall_edge`, `fan`, `bed`, `wardrobe`, `chair`,
  `table`, `object`, `mount`),
- hide a false block,
- merge two blocks into one bounding box,
- reset all annotations.

Annotations are stored per scan in
`research/mapping/scans/<id>/annotations.json` and are applied by the
`/reconstruct` endpoint. The fan block is labelled `fan` manually in the
current dense scan.

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

This is deliberately honest: the live prediction is the **rule baseline**.
The binary DL model is not deployed because it scored 82.7% validation versus
100% for `max(moving_energy)>0` on the same split. The panel is the integration
point for the future 3-class `empty`/`human`/`non-human` model.

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
py -3 tools/mapping/ml/train.py --data research/mapping/ml --window 32 --stride 8
```

It trains a small 1D CNN, evaluates it, and exports `model.tflite`,
`model_data.h`, labels, normalization and metrics. The ESP32 inference layer is
not integrated yet; it will run only when the arm is parked, never during the
scan. A quantized model under ~50 KB plus an ~80 KB arena fits the current
~230 KB free heap without PSRAM. The current scan still produces a geometric
HC/ToF point cloud; TinyML is for HLK presence/activity, not point-cloud
geometry.

**Current ML baseline:** the first binary `empty vs human` dataset (5,576
frames, 1,387 windows) trained a 1D CNN to 82.7% validation accuracy, while a
simple `max(moving_energy)>0` rule reached 100% on the same split. The rule is
kept for movement/presence; the DL model is a pipeline baseline, not the
primary detector. A meaningful DL target must be harder: human vs non-human,
stationary-human presence, or activity classification, evaluated on a true
held-out session.

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
- `GET /api/mapping/scans/{id}/reconstruct`
- `GET /api/mapping/scans/{id}/annotations`
- `POST /api/mapping/scans/{id}/annotations`
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
