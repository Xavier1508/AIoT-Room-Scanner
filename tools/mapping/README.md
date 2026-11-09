# tools/mapping

Dependency-free PC tools for the AIoT room scanner.

## Start the dashboard

```powershell
$py = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
Push-Location .\tools\mapping
& $py -B .\mapping_server.py --host 127.0.0.1 --port 8000
Pop-Location
```

Open `http://127.0.0.1:8000/`. The server reads `tools/ops/device.local.json`
(gitignored) and proxies the ESP32 API server-side. Do not port-forward it.

## CLI calibration

```powershell
& $py -B .\tools\mapping\calibrate.py --distance-cm 75 --samples 10 --label "wall 75 cm"
```

Records are appended to `research/mapping/calibration.json`. HC is the
reference; the ToF offset corrects its physically forward-mounted lens.

## CLI scan

```powershell
& $py -B .\tools\mapping\scan.py --yaw-step-deg 10 --tilt-step-us 50 --dwell-ms 300 --samples 3
```

The ESP32 must be IDLE/PARKED with sensors running. The tool enables
`scan_mode_start`, sends explicit fine nudges, saves
`research/mapping/scans/<UTC>/`, then returns to yaw 0 and servo 800 µs.

**Power warning:** a servo attach brownout was observed on 2026-11-09. Do not
run a loaded scan until the servo/5 V rail is fixed and measured under load.

## Files

- `esp_client.py` — LAN client, reuses `tools/ops/device.py`.
- `calibrate.py` — HC/ToF/HLK calibration capture.
- `scan.py` — bounded yaw/tilt scan and CSV/JSONL writer.
- `mapping_server.py` — local HTTP API + static dashboard.
- `static/` — vanilla canvas 3D isometric viewer.
- `common.py` — paths, medians, polar conversion, provisional tilt curve.

Deep-learning training is not implemented here; the output is a clean dataset
for a future PC-side training step.
