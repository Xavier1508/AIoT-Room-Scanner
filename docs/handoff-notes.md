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
ESP32. The two 30-point validation scans are dirty (operator active); the fast
full scan `20261111T154814Z` is a coverage/timing check, not the map. The
8-sample reference `20261110T184241Z` and its object anchors (bed/fan) are
canonical; the slow 8-sample scan is pending an empty-room confirmation.
A unified master dataset exists at
`research/mapping/dataset/aiot_room_dataset_v1.csv` (8,259 rows, timestamped,
labels empty/human). The current
mapping reference is scan `20261110T184241Z` with Mirror Y ON, auto-align
rotation `-1.1°`, measured bed/fan labels and no prior bed; see
[project-state.md](project-state.md) for current numbers.

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

## Next steps

1. When the operator confirms the room is empty, run the **Fine** preset
   (**8 samples/point, 500 ms dwell, about 34 min**) for a fresh canonical map
   (the 2-sample fast scan `20261111T154814Z` is only a coverage/timing check).
   Keep the fan OFF while scanning or during the AI demo; the 30-75 cm HLK
   parking rule is intentional. Reconstruct with the anchors, then regenerate
   the PLY, dataset manifest and master CSV.
2. Confirm `/api/status.ml` becomes ready after ~6.4 s, record latency,
   arena use and the live empty/human result; check no brownout. Then verify
   the 0.9.3 AI gate with the operator present: `ml_alert_on` beeps only for a
   human at 30-75 cm, a non-human object stays silent, `hlk_alert_on` beeps
   for any object, and nothing beeps above 75 cm.
3. Verify the final scan `20261110T184241Z`: Mirror Y ON, auto-align `-1.1°`,
   bed `-1.2°` wall-snapped, fan `81.8°` preserved, **12 blocks** (3 measured
   walls + bed + fan + 7 priors), no prior bed.
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
