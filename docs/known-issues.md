# Known limits and bring-up history

## Not yet verified physically

No peripheral has been powered/armed by the agent. Motor voltage (5/12 V),
ULN2003 jumper layout, supply current ratings, rail voltages, backfeed protection,
servo variant and mechanics still require operator confirmation/measurement.
No multimeter result exists. GPIO state is not continuity/voltage evidence.

Real HLK UART frames, buzzer sound, and no-load servo movement have been observed
by the user; those observations are not electrical measurements. Stepper rotation
under load, loaded servo movement, and combined load stability remain unresolved.
ToF ranging and PC point-cloud tooling now exist, but no calibrated 3D map,
trained AI, CSI, or CDM324 result exists. A servo attach brownout is unresolved.

## Network boundary

SSID/password are intentionally not guessed or extracted from Windows. Until
local provisioning finishes, Wi-Fi/web/real OTA remain unverified. Source/build
support for OTA is not equivalent to a successful OTA version change. Standalone
power requires a separate operator action: USB unplugged before jack power.

HTTP Basic and CSRF are LAN access controls, NOT transport encryption or firmware
signatures. NVS/local web-access JSON are not claimed encrypted. OTA has no
implemented automatic rollback. Use only a successor built with OTA retained.

ESP32-S3 only discovers 2.4 GHz, not 5 GHz-only networks. Passive discovery cannot
recover a hidden SSID name; manual entry remains optional for that case. The
48-choice cap and SDK record limit are reported as truncation, never described
as all possible networks. Visible SSID does not prove ownership. Network labels
are untrusted bytes and are escaped in the terminal, never executed as commands.

The first servo attempt on `0.2.0-scan` returned `servo_pwm_setup_failed` before
routing any pulse. Inspection of the pinned Arduino-ESP32/ESP-IDF headers showed
ESP32-S3 LEDC maximum resolution 14 bits, while the initial code requested 16.
The repair is `0.2.1-servo`: 14-bit duty conversion at 50 Hz. It was built,
installed through real LAN OTA, and the user confirmed no-load horn movement.
Stepper supply remains unresolved independently of this servo repair.

The `0.2.4-pose-axes` hold experiment used 1950/2000 us and did not produce the
expected loaded servo movement in the user's observation. The user then reported
that the legacy small-pulse sequence (`1500 -> 1450/1550 -> 1500 us`) moved the
servo normally. The root cause of the hold-specific failure was not isolated;
possible mechanical limit, supply sag, or load torque remain unproven. `0.2.5`
restored the legacy sequence, `0.2.6` added a base-hold tuning mode, `0.2.7`
made the saved-base return explicit, and `0.2.8` set the base to 900 us.
`0.5.0` records the user-confirmed 800 us zero with a 500-1400 us manual clamp,
500-950 us scan clamp, 200/50/25 us hold buttons, and corrects the VL53L1X
active-low data-ready polling condition. The 500 us lower bound is a firmware
choice, not a measured mechanical limit; the servo's actual mechanical range is
still unknown. Physical loaded movement and rail voltage still require operator
measurement.

**Measured brownout (2026-11-09):** after `0.4.0` OTA, a 25 us servo nudge
(`servo_up_25`) attached the servo and the ESP32 reset with `reset_reason=9`,
`brownout=true`. A later attach-only `park_servo` test made the board completely
offline (no HTTP/ping/USB), confirming the rail collapses before deliberate
movement. The board must be power-cycled and the servo/5 V rail fixed/measured
under load. `0.5.0-sequential-scan` adds a software guard and servo-detach
between columns, but software cannot create current; no full scan is claimed.
This is an electrical finding, not a firmware success claim.

**USB-only sensor power:** with USB-C only, the board web/API stays online but
the 5V sensor rail is not adequately powered: HC stale, VL53L1X absent, HLK no
data. Use the 9V jack for sensor calibration; do not connect USB and jack
together. The ESP32 web dashboard still auto-starts over Wi-Fi when jack-powered.

The updated workbook maps the standard 5 V HC-SR04 to TRIG10/ECHO11 with the
installed 1 kΩ + (1 kΩ+1 kΩ) divider, and VL53L1X to SDA8/SCL9 with optional
INT14/XSHUT13. `0.3.2` adds XSHUT reset and interval-limited ToF reads after a
0.3.1 long-run observation became stale with many I2C errors. A 12-snapshot/~24 s
retest initially stayed valid with 0 I2C errors, but later became stale; software
restart did not recover it, and a fresh start reported `wrap_target_fail` without
I2C errors. Bring-up produced valid HC-SR04, VL53L1X and HLK readings at times,
but ToF long-run/optical validity and calibrated geometry remain unresolved.
A 5 V HC-SR04 must not connect ECHO directly to the ESP.

## USB bring-up history (keep failures distinct from successful builds)

- `0.1.0-usb`: built, flashed, booted IDLE and passed basic on-device negative
  tests / 34 synthetic assertions. Rapid extended request sequences exposed
  intermittent missing/late console responses. No observed reset/motion was
  inferred from those failures; the root cause was not proven by logs alone.
- `0.1.1-usb`: experimental IDF interrupt console. Build/upload passed but USB
  status did not respond. Not a successful boot/console test.
- `0.1.2-usb`: experimental HAL polling console. Build/upload passed but USB
  status did not respond. Not a successful boot/console test.
- `0.1.3-usb`: restores the supported core HWCDC native PHY initialization,
  increases RX/TX buffers, bounds TX waits to 2 ms, sends at most one packet per
  loop, and suppresses the SDK's secondary USB log writer. Actual verification
  status is in project-state.md / test-report.md, not implied by this description.
- `0.1.4-usb`: additionally services the HWCDC connection handshake each loop.
  After a user USB power cycle and **250 ms host request spacing**, three complete
  seven-case USB verification runs passed. Do not extrapolate this to high-rate
  transfers: earlier faster exchanges still had missing/partial responses, and
  the exact lower-layer cause was not isolated. Do not blindly retry movement.

Host tooling filters stale response types, resynchronizes framing, avoids
purging a live CDC endpoint and paces requests/long provisioning records.
It never blindly retries a timed-out actuator command. ROM/esptool connectivity
remained available during the experimental console failures.

## Toolchain incidents resolved or documented

- The installed Arduino S3 package has DIO80, not DIO40, bootloader assets.
  The initial DIO40 build failed before upload; DIO80 is used and build-tested.
- A first dependency-preflight attempt had Windows native argument quoting
  errors; single-quoted Python literals fixed it. This did not flash the board.
- PlatformIO 6.12.0 treats an explicit upload_protocol as requiring OpenOCD,
  even for esptool. It auto-downloaded an unneeded global package on the first
  run. The option was removed, offline preflight was added, and the user
  explicitly approved deletion of only that new folder. Removed 897 files /
  6,188,429 bytes. No other global packages were deleted.

Failed-run logs, hashes and user-authorized research audit are retained locally.
Build scratch/objects/ELFs are automatically purged. Do not infer a successful
hardware or network result from a retained binary or a compiler success line.
