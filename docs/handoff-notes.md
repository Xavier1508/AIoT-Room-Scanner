# Handoff notes — AIoT ESP32-S3 room scanner

Updated: 2026-11-09. This note records the current design, measured/user-reported
state, and the next safe steps. It is not a claim of physical measurements that
were not taken.

## Project shape

- PlatformIO + Arduino-ESP32 **2.0.17** (`espressif32@6.12.0`), ESP32-S3,
  16 MB flash, OTA partition layout, PSRAM disabled.
- Local LAN dashboard with HTTP Basic + boot-scoped CSRF, authenticated
  application OTA, passive 2.4 GHz Wi-Fi scan/provisioning, HLK-LD2410C UART
  parser, 28BYJ-48/ULN2003 stepper, SG90-class servo.
- No trained 3D/TinyML/CSI model yet; CDM324 remains disabled. Sensor health,
  calibration capture, scan orchestration and a canvas 3D point-cloud viewer are
  implemented. Deep-learning training is still a PC-side future step.
- Deployed firmware: `0.4.2-mapping-ready`.
- Built but not OTA-deployed: `0.5.0-sequential-scan` (837088 bytes, SHA-256
  `32968459f67083ae247d2cf25e1e1ebe9f8cd7ef066b287322c0e8c348e41c5d`).
  Adds sequential scan guard, servo detach between columns, HLK parking-sensor
  ramp 75→30 cm, scan/motion muting and HLK 3D overlay. The board went offline
  during the attach-only test; power-cycle and verify before OTA.
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

1. Fix the servo/5 V power path first. The 0.4.0 small-motion test caused a
   brownout when the servo attached; do not run loaded movement or a full scan
   until the rail is measured under load and common ground is verified.
2. Keep the arm supported. `park_servo` at 800 µs is explicit; boot is detached.
3. Use the PC dashboard to capture calibration at 30/50/75/100/150/250 cm.
   First record at 75 cm: HC offset +6 mm, ToF offset +56 mm, 100% valid.
4. Only after power is fixed, run a coarse scan 10°/50 µs and inspect the point
   cloud. Then run fine 5°/25 µs and collect repeat scans.
5. Treat ToF long-run state as unresolved until a 10+ minute stationary run
   with zero stale periods is observed. HLK is presence/proximity only; blind
   below 30 cm.
6. Do not train a deep-learning model until calibrated, repeatable scans exist.
   The PC pipeline is ready; ESP32 is collector/control, not a trainer.
7. Update `docs/project-state.md`, `docs/test-report.md`, and
   `docs/openapi.json` after each verified OTA/hardware result.

## Evidence and docs

- `docs/project-state.md` — chronological state and next action.
- `docs/test-report.md` — workbook T01–T13 and W01–W15 results.
- `docs/known-issues.md` — historical failures and limits.
- `docs/openapi.json` — local HTTP contract.
- `analysis/device/` — OTA/status evidence; `analysis/platformio/` — builds.
- `research/` — append-only research evidence managed by the research CLI.
