# Handoff notes — AIoT ESP32-S3 room scanner

Updated: 2026-11-12. Current firmware: `0.9.3-ai-gated-rule` (v3 logits model
+ AI-gated range beeper). ML live (`ready=true`, model
`hlk-cnn-20261111T162517Z-logits`, arena 5,128 bytes). `ml_alert_on` requires
the v3 `human` prediction (confidence >= 0.80, two inferences) and a raw HLK
distance of 30-75 cm; the HLK range rule sets the 150-2000 ms interval from the
filtered distance. No AI beep occurs outside 75 cm; `hlk_alert_on` is the
rule-only comparison mode. The earlier `0.8.2-ml-alert` crash was the ESP_TF
Softmax Prepare path, not corruption; the fix strips the Softmax op
(`tools/mapping/ml/strip_softmax.py`) and computes softmax in float32 on the
ESP32. The two 30-point validation scans are dirty (operator active); the fast full
scan `20261111T154814Z` is a coverage/timing check. Two 8-sample maps exist:
`20261110T184241Z` is the cleanest (bed 68/fan 33 at anchors);
`20261112T030324Z` is the newest (475/475, resumed from 373 after a local PC
`WinError 10048`; bed 36/fan 23 at per-scan `eps_m=0.25`, anchors pinned). The
master CSV contains both: 8,734 rows (950 scan points + 7,784 HLK frames),
SHA-256 `75539aa7...d31c`. Live 0.9.3 gate verified for a human at 62-78 cm; a
moving object held by the operator is classified human (binary model
limitation), and a static object at 75 cm is not detected by the HLK. See
`docs/live-gate-test.md` for evidence.

## Project shape

- PlatformIO + Arduino-ESP32 **2.0.17** (`espressif32@6.12.0`), ESP32-S3,
  16 MB flash, OTA partition layout, PSRAM disabled.
- Local LAN dashboard with HTTP Basic + boot-scoped CSRF, authenticated
  application OTA, passive 2.4 GHz Wi-Fi scan/provisioning, HLK-LD2410C UART
  parser, 28BYJ-48/ULN2003 stepper, SG90-class servo.
- Local 3D/2D mapping dashboard, per-scan priors, Mirror Y, auto-align, PLY
  export and a **TFLite Micro empty/human classifier**. The rule HLK path
  remains the buzzer/safety fallback.
- Installed firmware: `0.9.3-ai-gated-rule`, 942,720 bytes (including the
  14,528-byte v3 logits model), RAM 116,576 bytes (35.6%), SHA-256
  `c82805bc5c8015e7af1b560bd6eedddadcdfddd4b32210ac68e6299251c0c6fb`.
  The `0.8.3` and `0.8.1` artifacts remain as fallbacks. See
  `docs/ml-deployment.md`.
  The earlier `0.8.1` artifact (940,592 bytes, SHA-256 `3d19fa9b…130e`) is the
  known-good fallback image. See `docs/ml-deployment.md`.
- USB-only power keeps the board web/API online but does not power the 5V
  sensor rail: HC stale, VL53L1X absent, HLK no data. Use the 9V jack for sensor
  calibration; do not connect USB and jack together.
- Loaded servo movement and rail current still require operator verification;
  scans have run successfully, but voltage/current were not measured.
- PC mapping dashboard: `tools/mapping/mapping_server.py` on
  `http://127.0.0.1:8000/`; see `docs/mapping-dashboard.md`.

## Pin map (from the latest workbook)

| Device | ESP32-S3 pin | Notes |
|---|---|---|
| HLK-LD2410C TX/RX | GPIO16 / GPIO17 | UART RX/TX, 256000 baud, passive parser |
| HLK OUT | GPIO18 | Optional, raw/unverified |
| ULN2003 IN1..IN4 | GPIO4..GPIO7 | Half-step table in `src/stepper.cpp` |
| Servo signal | GPIO15 | 50 Hz LEDC, 14-bit resolution |
| Buzzer | GPIO21 | Active LOW |
| HC-SR04 standard 5 V TRIG | GPIO10 | Output; ECHO is not connected directly |
| HC-SR04 standard 5 V ECHO | GPIO11 | Installed R1=1 kΩ series and R2+R3=1 kΩ+1 kΩ to GND divider |
| VL53L1X SDA | GPIO8 | I2C, 3.3 V logic |
| VL53L1X SCL | GPIO9 | I2C, 3.3 V logic |
| VL53L1X INT | GPIO14 | Optional interrupt |
| VL53L1X XSHUT | GPIO13 | Optional output control |

The workbook is a design map, not continuity or voltage evidence. Verify the
actual breakout labels before powering sensors.

## Current actuator state and findings

- Stepper: the user found and saved the balanced position as relative reference
  **0** in NVS. `park_stepper` holds the current position; `stepper_left_10` /
  `stepper_right_10` move 114 half-steps nominally (about 10° at 4096
  half-steps/rev). This is relative, not homing/absolute.
- Servo: the user reports the legacy small-pulse test moves normally. The older
  hold attempt at 1950/2000 µs did not produce the expected movement under the
  installed arm; the exact cause was not isolated. The current tuning design uses
  a saved base target. The user corrected the mechanical zero to **800 µs**;
  `0.4.0` retains the corrected saved default at **800 µs**. Manual clamp is
  **500–1400 µs**; scan mode clamps to **500–950 µs**. `park_servo` returns to
  the saved base, ±200/±50/±25 µs nudges keep holding. `save_servo_here`
  overwrites the saved base in NVS.
- **Brownout finding:** a 25 µs servo attach produced `reset_reason=9`,
  `brownout=true`. Boot returned IDLE/detached. Do not run loaded servo or a
  full scan until the servo/5 V rail is fixed (separate supply, common ground,
  measured under load). The 500 µs lower bound is a firmware choice, not a
  measured mechanical limit.
- The servo is an elevation/tilt axis; the stepper is the horizontal axis. The
  target mechanical zero is the sensor arm facing forward, not a blind angle.
- OTA and STOP release holds. Support the arm before OTA, release, or power loss.

## Firmware/API invariants

- Boot is safe: buzzer off, stepper coils low, servo detached, no automatic
  motion.
- Motion commands are explicit; STOP bypasses the queue and releases outputs.
- The old `park_pose` command is intentionally rejected with
  `use_separate_axis_commands`.
- `servo_test` / `servo_test_long` remain the legacy small-pulse tests.
- `park_servo`, `servo_up_200` / `servo_down_200`, and `servo_up_50` /
  `servo_down_50` hold position; they do not detach after each adjustment.
  `release_servo` detaches.
- NVS pose references are relative/assumed, never absolute. A reboot restores the
  saved stepper reference and servo base, but physical movement while unpowered
  invalidates the assumption.
- The OTA helper validates the image and SHA locally. The optional
  `X-Firmware-SHA256` header had a compatibility problem on the deployed 0.2.3
  server; the CLI omits that header and compares the server-returned digest.
- The build wrapper hashes sources before and after compilation and refuses an
  artifact if a source changed during the build.

**UI 2026-11-12:** the AI/Presence tab now has a signal chain, status strip,
`Start AI Demo`/`Stop`, `AI Gate`/`Rule Only`, and `Sensors ON/OFF`. The health
proxy forwards `ml_alert`; v3 metrics are shown; the neutral toast replaces the
green fill. Screenshots: `analysis/mapping/dashboard-20261112-ui/`.

## Next steps

1. Two 8-sample maps exist. Use `20261110T184241Z` for the cleanest demo map
   (bed 68/fan 33) or `20261112T030324Z` for the newest scan (bed 36/fan 23,
   anchors pinned, per-scan `eps_m=0.25`). If the tripod/base moved, put it
   back on its mark, re-zero yaw, then run the **Fine** preset again
   (**8 samples/point, 500 ms dwell, about 34 min**). Keep the fan OFF while
   scanning or during the AI demo; the 30-75 cm HLK parking rule is intentional.
2. Live 0.9.3 gate is verified for a human at 62-78 cm (model 0.993-1.0, gate
   true, beeps 1425-2000 ms, stops above 75 cm). Repeat with the operator:
   `ml_alert_on` for a human, `hlk_alert_on` for a moving target at 75 cm.
   A moving object held by the operator is classified human by the binary
   model; a static object at 75 cm is not detected by the HLK. Do not claim
   non-human rejection; see `docs/live-gate-test.md`.
3. Verify the maps: `20261110T184241Z` uses rotation `-1.1 deg`, bed `-1.2 deg`,
   fan `81.8 deg`, 12 blocks; `20261112T030324Z` uses rotation `3.5 deg`, 9
   boxes, bed/fan at the anchors, 443 filtered points.
4. Export final PLY and clean dataset after labels are confirmed.
5. Record demo: boot, calibration, short scan, 2D/3D, Mirror Y, auto-align,
   prior edit, PLY save, AI/Presence DL vs rule.
6. Update `docs/project-state.md`, `docs/test-report.md`,
   `docs/openapi.json` and `docs/third-party-notices.md` after each verified
   OTA/hardware result.

## Evidence and docs

- `docs/project-state.md` — chronological state and next action.
- `docs/test-report.md` — workbook T01–T13 and W01–W15 results.
- `docs/known-issues.md` — historical failures and limits.
- `docs/openapi.json` — local HTTP contract.
- `analysis/device/` — OTA/status evidence; `analysis/platformio/` — builds.
- `research/` — append-only research evidence managed by the research CLI.
