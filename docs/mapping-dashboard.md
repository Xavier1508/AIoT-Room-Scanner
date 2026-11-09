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
**sequential** to avoid overlapping actuator current: stepper moves and holds,
servo attaches only after the stepper settles, the vertical sweep runs, the
servo detaches, then the next yaw starts. Firmware rejects servo attach while
the stepper is moving and stepper motion while the servo is attached. The PC
also requires a power-confirmation checkbox before starting because a servo
attach brownout was observed on 2026-11-09. Firmware enforces the mapping
envelope:

- stepper: `-513..+513` half-steps (about +/-45.1 degrees nominal)
- servo: `500..950` microseconds (500 = up, 950 = down)

The default grid is yaw -45..+45 degrees in 5-degree steps and tilt 500..950
microseconds in 25-microsecond steps: 19 x 19 = 361 points. A coarse run uses
10 degrees and 50 microseconds.

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

The **Point Cloud 3D** tab uses a dependency-free canvas isometric renderer.
Cyan points are ToF, orange points are HC. Drag to rotate, wheel to zoom.
It visualizes recorded data; it does not infer occupancy or train a model.

## Deep learning boundary

The current pipeline produces a clean dataset for later work. Training is not
performed on the ESP32 and is not claimed by this dashboard. A future training
step can consume `points.csv`/`samples.jsonl` on the PC after enough scans
exist. A geometric occupancy grid is the recommended baseline before any
learned model.

## Endpoints

- `GET /api/mapping/health`
- `GET /api/mapping/status`
- `POST /api/mapping/command`
- `POST /api/mapping/scan/start`
- `POST /api/mapping/scan/stop`
- `GET /api/mapping/scan/status`
- `GET /api/mapping/scans`
- `GET /api/mapping/scans/{id}/points`
- `GET /api/mapping/calibration`
- `POST /api/mapping/calibration/capture`

## Safety

- Scan mode does not move axes by itself; the PC sends each nudge.
- STOP on the ESP32 releases outputs and stops sensors/scan mode.
- A scan error leaves the arm held; it does not auto-release the servo.
- Verify cable clearance before the first sweep. The yaw limit is a software
  choice, not a mechanical proof.
