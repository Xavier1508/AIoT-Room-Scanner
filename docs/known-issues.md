# Known limits and bring-up history

## Not yet verified physically

No peripheral has been powered/armed by the agent. Motor voltage (5/12 V),
ULN2003 jumper layout, supply current ratings, rail voltages, backfeed protection,
servo variant and mechanics still require operator confirmation/measurement.
No multimeter result exists. GPIO state is not continuity/voltage evidence.

No real HLK readings, buzzer sounds, stepper rotation, servo motion, or combined
load stability have been established. No ToF/3D/AI/CSI/CDM324 result exists.

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
