# Project state

Updated: 2026-11-07. USB bring-up, SSID discovery, LAN dashboard access and real
application OTA are verified; the new park pose still requires user-controlled
physical direction/clearance verification.

- Scope/physical checklist: [scope.md](scope.md).
- Handoff notes for the next model/session: [handoff-notes.md](handoff-notes.md).
- ESP32-S3 rev0.2, 16 MB quad flash, native USB Serial/JTAG COM9 identified.
- eFuse reports embedded PSRAM8MB; firmware intentionally does not enable it.
- Existing `default_16MB.csv` OTA layout read and retained. No full-flash erase.
- Complete source, LAN UI, authenticated web OTA, local provisioning tool exist.
- **Running firmware: `0.2.6-servo-1800-hold`**, built and installed through real LAN OTA.
  Current application artifact: `analysis/platformio/build-20261106T201527036Z/firmware.bin`.
  Size **797472 bytes** / OTA slot **6553600 bytes**. Application SHA-256:
  `4529ee7abf3845b2a72a2354492c8e67e04d5d1b8b95681e3ca3426418aad8ad`.
- On the previous `0.1.4-usb` baseline, the user performed a USB-only physical
  power cycle. Full status then reported
  POWERON reset code 1, IDLE, no arms, buzzer OFF, coils released, servo detached,
  initialized PSRAM size 0, and HLK last_reading null (no fabricated data).
- Three consecutive **conservative USB** verification runs passed: seven cases
  per run, including unarmed/invalid/NUL commands, malformed provisioning with
  no config change, and **34/34 synthetic assertions** on-device each run.
  Host uses 250 ms between requests; this is NOT a high-rate USB stress guarantee.
  Evidence: `analysis/device/usb-conservative-20261105T154820Z/` and
  `analysis/device/usb-confirmed-20261105T154856Z/`.
- Earlier `0.2.0-scan`: USB seven-case verification passed, **48/48 on-device
  synthetic assertions**, IDLE with no arms. Real ESP passive scan completed:
  **5 APs / 3 unique SSID-security choices**, no hidden SSID, no truncation.
  Credentials were not entered and no Wi-Fi association was attempted by this test.
  Evidence: `analysis/device/scan-bringup-20261105T160613Z/`.
- Live scan/stop test observed scan running, rejected unarmed step_test with
  `wifi_scan_in_progress_actuators_idle`, then cancelled scan and returned IDLE.
  Roundtrip 360 ms includes deliberate host pacing; not measured physical stop
  latency. Evidence: `analysis/device/scan-control-20261105T160739Z/`.
- Portable tests: **68 C++ assertions + 19 Python tests passed**; dashboard JS
  syntax and OpenAPI checks passed. Physical pose direction/clearance remains
  separate from software validation.
- Earlier USB failures/experimental images are recorded in known-issues.md;
  do not use the unsuccessful 0.1.1/0.1.2 console experiments.
- Wi-Fi credentials have NOT been requested in chat, read from Windows, or guessed.
- Wi-Fi provisioning is now complete according to device status: configured,
  connected at `192.168.1.200`, RSSI about -62 dBm, web server ready. User reports
  the jack power is still disconnected; standalone-power status remains unproven.
- Root `http://192.168.1.200/` returns the HTML dashboard. `/api/status` and
  `/api/session` intentionally return JSON; seeing JSON at those paths is expected.
- LAN contract evidence: `analysis/device/lan-web-20261105T170121Z/`. It passed
  auth-required status, CSRF-required mutation, POST-only control, unarmed motion
  rejection, synthetic self-test, invalid OTA rejection and root/API content checks.
- Real application OTA is established. The new park pose has not been physically
  triggered in this deployment, so no angle, clockwise direction, cable-clearance,
  or holding-current result is claimed.
- Buzzer T05 is now physically confirmed Lulus: LAN command started the test,
  firmware observed BUZZER_TEST and returned IDLE with output OFF; user heard
  three beep pulses. Evidence: `analysis/device/buzzer-20261105T170632Z/`.
- HLK T06 communication is now partially verified: `hlk_start`/passive observation
  produced 747 valid frames, 0 rejected, 17,181 bytes, and a decoded target state
  with moving/stationary distance about 30 cm and energy 100. User observed a
  table in front of the sensor and expected <10 cm, so the distance is explicitly
  uncalibrated and may reflect mounting/blind-spot/reflective-surface behavior.
  This is not a coordinate or approach-direction result. Evidence:
  `analysis/device/hlk-passive-20261105T172057Z/`.
- During the earlier HLK observation, the user intentionally armed motor/servo;
  `stop` then returned IDLE with motor/servo/buzzer outputs off. At that
  checkpoint no physical motor or servo movement was confirmed, and supply
  ratings/readiness were still pending.
- An earlier user report said servo and stepper did not move during those checks.
  The actuator source was then still the shield/unknown: shield input was
  reported as about 7–12 V, but 5 V rail regulation/capacity was not verified.
  This remains historical blocked/untested evidence, not a GPIO/device failure.
- Current safe LAN status after stop: IDLE, both arms false, stepper off, servo
  detached. HLK remains enabled/valid with 6,229 valid frames; current decoded
  distance is 30 cm. Evidence: `analysis/device/actuator-blocked-20261105T173300Z/`.
- A temporary jumper was installed across the ULN motor-enable header. The
  indicator LEDs illuminated during the next software test, but the user still
  saw no motor rotation. LEDs do not prove motor-coil supply. Close-up ULN
  `+/-`, jumper contact, socket and motor cable inspection is now required.
  Evidence: `analysis/device/stepper-jumper-20261105T180353Z/`.
- Servo T10 is now physically confirmed Lulus: the 14-bit LEDC repair accepted
  the test, SERVO_TEST was observed, user saw the horn move, and firmware returned
  IDLE/detached. Evidence: `analysis/device/servo-fixed-20261105T174510Z/`.
- Real LAN OTA is now proven for the application path: `0.2.1-servo` was observed
  after reboot in IDLE with both arms false. Evidence:
  `analysis/device/ota-servo-20261105T174432Z/`. Automatic rollback remains false.
- Real LAN OTA also installed `0.2.2-long-tests`, returning IDLE with no arms.
  Dashboard now exposes bounded long tests: 512 half-steps forward/reverse and
  repeated small servo pulses. Neither long test has been physically triggered
  automatically. Evidence: `analysis/device/ota-long-tests-20261105T181751Z/`.
- Real LAN OTA installed `0.2.3-park-pose`, returning IDLE with both arms false,
  stepper de-energized, servo detached and OTA inactive. `park_pose` was not
  triggered automatically. Evidence: `analysis/device/ota-park-pose-20261106T164819Z/`.
- Real LAN OTA installed `0.2.4-pose-axes`, returning IDLE with both arms false,
  stepper off, servo detached, and a migrated NVS reference of 1024 half-step
  (90° nominal). The 114-half-step nudge controls and independent axis controls
  are available; no nudge was triggered automatically. Evidence:
  `analysis/device/ota-pose-axes-20261106T174847Z/`.
- Real LAN OTA installed `0.2.5-servo-small-test`, returning IDLE with both arms
  false, stepper off and servo detached. Servo axis buttons then ran the legacy
  small-pulse tests and detached. Evidence:
  `analysis/device/ota-servo-small-test-20261106T181851Z/`.
- Real LAN OTA installed `0.2.6-servo-1800-hold`, returning IDLE with stepper
  reference 0, servo detached, servo target 1800 µs, and
  `servo_base_source=default_1800`. `park_servo` now holds the current target;
  `servo_up_50`/`servo_down_50` adjust it by 50 µs and keep holding;
  `save_servo_here` persists the found base. Evidence:
  `analysis/device/ota-servo-hold-tune-20261106T201809Z/`.
- User now reports that the existing actuator tests/signals work and that the
  servo bracket and arm have been installed. This is a user report, not an
  independent electrical or motion measurement.
- Local Git `main` initialized; source/docs/tests are saved in the initial
  implementation commit (see `git log -1 --oneline`). No remote and no push;
  hosting details unconfirmed. Firmware, research and local secrets are ignored.

**Current next action:** hard-refresh the dashboard and support the arm. Press
`Hold di base 1800 µs`, then use `Geser +50 µs · hold` / `Geser −50 µs · hold`
one click at a time until the sensor arm faces forward. Record the pulse shown in
status, press `Simpan base servo`, and verify after reboot/OTA that `park_servo`
returns to that saved base. If the servo moves unloaded but not loaded, investigate
servo rail/current and leverage; if it does not move at all, inspect signal, horn
spline and servo power. No physical servo motion was triggered automatically by
the agent and no angle claim is made. Sensor implementation remains deferred until
this servo check passes.
HLK remains a communication success but its distance needs a later controlled
observation.

SSID discovery is passive 2.4 GHz only, not host/IP/port scanning. At most 48
deduplicated strongest choices are retained. Hidden SSID has a manual fallback.
Credentials are sent only after the user explicitly selects an authorized network.

For future reprovisioning, use `device.py status` and `lan-test` against only the
IP obtained from the board, and unplug USB before connecting jack power. The
current standalone LAN path, real OTA, new-version reboot, IDLE state and no-arm
state are already evidenced. Motor/servo pose direction and physical readiness
still require operator verification.

Unexpected side effect: PlatformIO initially auto-installed OpenOCD
`tool-openocd-esp32@2.1100.20220706` outside the workspace. The triggering explicit
upload_protocol option was removed and dependency preflight added. The user then
explicitly approved deleting only that extra folder. It was inventoried again
and removed: 897 files / 6,188,429 bytes. No other global packages were deleted.

## Evidence and storage handoff

- Research CLI integrity verification: **44 stored artifacts checked, 0 failures**.
  Evidence 8 = current build manifest; 9 = upload; 10 = USB verification;
  11 = actual passive scan; 12 = live scan/stop; 13/14 = host tests;
  15 = intermediate-retention cleanup; 16 = current application binary;
  17–19 = configured-device status, LAN safety contract and root/API content check;
  20 = buzzer result; 21–23 = HLK/actuator stop evidence; 24 = current safe status;
  25–27 = servo-fix build, real OTA and physical servo result; 28 = stepper
  no-rotation software/safe-state result; 29 = jumper/no-rotation result;
  30–31 = long-test build and OTA; 32–35 = park-pose build, OTA and host-test
  evidence; 36–39 = pose-axes build, OTA and final host-test evidence; 40 =
  post-OTA-helper compatibility test; 41–42 = servo-small-test build and OTA;
  43–44 = servo-hold-tune build and OTA.
- Build wrappers automatically removed object/ELF/cache scratch; the latest
  build alone purged **43,644,343 bytes** of disposable build state.
- Purged **20 hash-matched intermediate binary copies / 4,025,840 bytes**.
  Their logs/manifests remain; immutable research evidence/audit was not deleted.
  The cleanup summary's initial PowerShell formatting error was repaired from
  retained manifests and verified absence, explicitly noted in its report.
- Retained binary deliverables: current `0.2.6-servo-1800-hold`, prior
  `0.2.5-servo-small-test`, `0.2.4-pose-axes`, `0.2.3-park-pose`,
  `0.2.2-long-tests`, `0.2.1-servo`, `0.2.0-scan` and verified `0.1.4-usb`
  baseline, clearly separated by run folder. Prefer the current hold-tune build.
  Other intentionally retained files are source, documentation, tests,
  reusable tools, build/upload/test logs, hashes, and permanent research audit.
