# Handoff notes — AIoT ESP32-S3 room scanner

Updated: 2026-11-07. This note is for the next model/session continuing the
project after the Solana/OpenAI handoff. It records the current design,
measured/user-reported state, and the next safe steps. It is not a claim of
physical measurements that were not taken.

## Project shape

- PlatformIO + Arduino-ESP32 **2.0.17** (`espressif32@6.12.0`), ESP32-S3,
  16 MB flash, OTA partition layout, PSRAM disabled.
- Local LAN dashboard with HTTP Basic + boot-scoped CSRF, authenticated
  application OTA, passive 2.4 GHz Wi-Fi scan/provisioning, HLK-LD2410C UART
  parser, 28BYJ-48/ULN2003 stepper, SG90-class servo.
- No 3D mapping, TinyML, CSI, ToF ranging, or CDM324 implementation yet.
- Current verified firmware: `0.2.8-servo-scan-range` (verify again with
  `device.py status` after any further OTA).

## Pin map (from the latest workbook)

| Device | ESP32-S3 pin | Notes |
|---|---|---|
| HLK-LD2410C TX/RX | GPIO16 / GPIO17 | UART RX/TX, 256000 baud, passive parser |
| HLK OUT | GPIO18 | Optional, raw/unverified |
| ULN2003 IN1..IN4 | GPIO4..GPIO7 | Half-step table in `src/stepper.cpp` |
| Servo signal | GPIO15 | 50 Hz LEDC, 14-bit resolution |
| Buzzer | GPIO21 | Active LOW |
| HC-SR04 3.3 V TRIG | GPIO10 | Only the 3.3 V variant may connect ECHO directly |
| HC-SR04 3.3 V ECHO | GPIO11 | 5 V HC-SR04 needs a divider/level shifter |
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
  a saved base target. The requested base is **900 µs**; the firmware clamp is
  **500–1400 µs**. `park_servo` returns to the saved base, `servo_up_200` /
  `servo_down_200` move the target by 200 µs, `servo_up_50` / `servo_down_50`
  move it by 50 µs, and all keep holding. `save_servo_here` overwrites the saved
  base in NVS. Status exposes `pose.servo_base_source`, `pose.servo_base_saved`,
  `pose.servo_base_us`, `pose.servo_min_us`, `pose.servo_max_us`, and
  `actuators.servo_target_us`. The 500 µs lower bound is a firmware choice, not
  a measured mechanical limit; test the low end in stages.
- Servo supply/current and the 5 V rail capacity are still unmeasured. Do not
  claim the SG90 can lift the arm until loaded movement is observed. Do not use
  9 V on the servo; common ground is required.
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

1. Hard-refresh the dashboard and support the arm.
2. Press `park_servo` to return to the saved base (900 µs).
3. Use `servo_up_200` / `servo_down_200` for fast movement and
   `servo_up_50` / `servo_down_50` for fine adjustment. Record the pulse shown
   in status.
4. Test the low end in stages (900 → 700 → 500); release immediately if the
   servo buzzes or stalls.
5. Press `save_servo_here` to overwrite the base; reboot/OTA and verify
   `park_servo` returns to it. Confirm loaded movement and measure the servo
   supply under load.
5. Only after the servo/arm is mechanically stable, add sensors:
   - VL53L1X on I2C GPIO8/9; detect address and range, no fabricated values.
   - HC-SR04 3.3 V on TRIG10/ECHO11; bounded trigger and timeout handling.
   - Add status/API/dashboard fields and host tests; keep sensor data marked
     stale/invalid until a real frame/measurement exists.
6. Update `docs/project-state.md`, `docs/test-report.md`, and
   `docs/openapi.json` after each verified OTA/hardware result.

## Evidence and docs

- `docs/project-state.md` — chronological state and next action.
- `docs/test-report.md` — workbook T01–T13 and W01–W09 results.
- `docs/known-issues.md` — historical failures and limits.
- `docs/openapi.json` — local HTTP contract.
- `analysis/device/` — OTA/status evidence; `analysis/platformio/` — builds.
- `research/` — append-only research evidence managed by the research CLI.
