# Project state

Updated: 2026-11-09. USB bring-up, SSID discovery, LAN dashboard access, real
application OTA, sensor health and the PC mapping dashboard are verified.
A full coarse sequential scan now completes without brownout using software
power timing. ToF is valid at rest but stalls during servo motion, so scans use
HC fallback points; the 3D map is therefore HC-based, not ToF-based.

- Scope/physical checklist: [scope.md](scope.md).
- Handoff notes for the next model/session: [handoff-notes.md](handoff-notes.md).
- ESP32-S3 rev0.2, 16 MB quad flash, native USB Serial/JTAG COM9 identified.
- eFuse reports embedded PSRAM8MB; firmware intentionally does not enable it.
- Existing `default_16MB.csv` OTA layout read and retained. No full-flash erase.
- Complete source, LAN UI, authenticated web OTA, local provisioning tool exist.
- **Running firmware: `0.5.0-sequential-scan`**, installed through real LAN OTA
  after the board was power-cycled. Current application artifact:
  `analysis/platformio/build-20261109T091806602Z/firmware.bin`.
  Size **837088 bytes** / OTA slot **6553600 bytes**. Application SHA-256:
  `32968459f67083ae247d2cf25e1e1ebe9f8cd7ef066b287322c0e8c348e41c5d`.
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
- Portable tests: **74 C++ assertions + 28 Python tests passed**; dashboard JS
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
  `servo_base_source=default_1800`. `park_servo` held the current target;
  `servo_up_50`/`servo_down_50` adjusted it by 50 µs and kept holding;
  `save_servo_here` persisted the found base. Evidence:
  `analysis/device/ota-servo-hold-tune-20261106T201809Z/`.
- User tuned the servo down to the firmware lower clamp **1000 µs** and saved it
  as the provisional base. The next `−50` was rejected with `servo_pulse_limit`;
  this is the firmware bound, not proof of the servo's mechanical limit. The
  original `park_servo` held the current target rather than resetting to 1800.
- Real LAN OTA installed `0.2.7-servo-base-reset`, returning IDLE with stepper
  reference 0, servo detached, saved base/target **1000 µs**, and
  `servo_base_source=nvs`. `park_servo` returned to the saved base;
  `servo_1800` truly reset the target to 1800 µs; `servo_up_50`/`down_50`
  continued to adjust and hold. Evidence:
  `analysis/device/ota-servo-base-reset-20261106T203314Z/`.
- Real LAN OTA installed `0.2.8-servo-scan-range`, returning IDLE with stepper
  reference 0, servo detached, migrated base/target **900 µs**, clamp
  **500–1400 µs**, and `servo_base_source=migration_default_saved`. The old
  1800 command is removed; ±200 and ±50 hold buttons are available. Evidence:
  `analysis/device/ota-servo-scan-range-20261106T205530Z/`.
- User now reports that the existing actuator tests/signals work and that the
  servo bracket and arm have been installed. This is a user report, not an
  independent electrical or motion measurement.
- User corrected the servo mechanical zero to **800 µs**. `0.4.2` retains the
  saved 800 µs NVS value without attaching or moving the servo at boot;
  `park_servo` applies the saved target explicitly.
- `0.3.2` adds explicit `sensors_start`/`sensors_stop`, HC-SR04 polling on
  GPIO10/11 with bounded timeout and divider-aware validity, VL53L1X I2C
  scan/init/range polling on GPIO8/9, and dashboard/OpenAPI status fields.
- Live stationary sensor test: I2C address 41 (`0x29`) was found. Across five
  status samples, HC-SR04 had 29 valid samples and 0 timeouts at 13.7–16.7 cm;
  VL53L1X had 77 valid samples, 0 invalid and 0 I2C errors at 210–220 mm with
  raw status 9; HLK remained valid. These are bring-up values, not calibrated
  geometry. Evidence: `analysis/device/sensor-tof-ready-20261107T074113Z/`.
- The first 0.3.1 long-run observation later became stale with 85,489 I2C errors;
  this is retained as a failure, not discarded. 0.3.2 adds XSHUT reset and
  interval-limited ToF reads. A 12-snapshot/~24 s retest initially stayed valid
  with 279 ToF samples and 0 I2C errors, but later the same boot became stale;
  a software restart did not recover it. A fresh start then showed raw status 7
  (`wrap_target_fail`) with invalid samples and no I2C errors. HC-SR04/HLK stayed
  valid. Evidence: `analysis/device/sensor-poll-throttled-20261107T080748Z/`.
- `0.4.2-mapping-ready` adds sensor health/error-rate, HLK inside `sensors`,
  fine jog 5°/25 µs, scan mode ±513 half-step / 500–950 µs, HLK proximity
  buzzer, a motion-settle guard, and calibrated HC/ToF values in both dashboards.
  Real OTA returned IDLE with servo detached and base 800 µs.
- Live 0.4.2 sensor health after start: **OK / OK / OK**; HC ~74 cm,
  ToF raw ~69 cm → calibrated ~74 cm with the provisional +50 mm offset,
  HLK valid, ToF I2C errors 0 and responsive true. Evidence:
  `analysis/device/ota-mapping-ready-042-20261109T052016Z/`.
- PC mapping dashboard is implemented under `tools/mapping/` with a
  dependency-free HTTP server, calibration capture, sequential scan orchestrator
  and canvas 3D isometric viewer with an HLK presence overlay. First calibration
  record at 75 cm: HC offset +6/+9 mm, ToF offset +56 mm, both sensors valid
  100% over five samples.
- `0.5.0-sequential-scan` is deployed (837088 bytes, SHA-256
  `32968459f67083ae247d2cf25e1e1ebe9f8cd7ef066b287322c0e8c348e41c5d`) with:
  sequential scan guard, servo-detach between columns, HLK parking-sensor ramp
  75→30 cm, scan/motion muting, 2-frame confirmation, and HLK overlay.
  Real OTA returned IDLE, servo detached, stepper reference 0, base 800 µs;
  status exposes `sequential_guard=true` and alert min/max 30/75 cm.
- USB-only power check: board web/API stayed online, but HC was stale,
  VL53L1X absent and HLK no data. USB-only does **not** power the 5V sensor rail;
  sensors need the 9V jack while the board remains reachable over Wi-Fi.
- `scan_mode_start` test under USB-only power succeeded with
  `scan.mode=true`, `sequential_guard=true`, `alert_muted=true` and
  `hlk_alert.mute_reason=scan_mode`; after stop the mute reason became
  `no_valid_hlk`. No servo attach or scan was performed.
- With the 9V jack and USB removed, `park_servo` at 800 µs attached and held
  without an immediate brownout; HC was valid ~288.8 cm and HLK ~267 cm.
  VL53L1X was absent with an empty I2C scan. A later `sensors_stop` command
  timed out and the board became unreachable again. Partial attach success does
  not prove stable power or a working full scan. Evidence:
  `analysis/device/jack-servo-partial-20261109T124803Z/`.
- After recovery, a controlled jack-powered servo test succeeded:
  `park_servo` → `servo_down_25` (800→775) → `servo_up_25` (775→800) →
  `release_servo`. All returned ok, no brownout, reset reason stayed 1; HC
  ~71.3 cm and HLK ~62 cm. ToF still absent. Evidence:
  `analysis/device/jack-servo-motion-20261109T125129Z/`.
- ToF is not permanently absent. After a clean boot and `sensors_start`, I2C
  `0x29` is present and ToF reads ~76.1 cm while HC reads ~76.0 cm using the
  firmware offsets. Raw values were HC 760 mm and ToF 711 mm; the PC 56 mm ToF
  offset gives ~76.7 cm, within ~0.7 cm of HC. After a reset the firmware leaves
  sensors stopped, so the dashboard shows ToF ABSENT until `sensors_start`.
- Sequential scan attempt 1 (`20261109T132613Z`): 10/30 points, first column
  yaw -10°, servo 500→950 µs, HC valid throughout, ToF stale from the first
  sample. The board then reset with `reset_reason=9`, `brownout=true`. Evidence:
  `analysis/device/scan-brownout-20261109T132901Z/`.
- Sequential scan attempt 2 (`20261109T133153Z`): after parking the servo at
  800 µs before detach, 19/30 points, second column reached 900 µs, HC valid,
  ToF stale for every point. The board reset again with `reset_reason=9`,
  `brownout=true`. Evidence:
  `analysis/device/scan-brownout-2-20261109T133435Z/`.
- **Brownout blocker:** a small validation (`servo_up_25`) reset the board with
  `reset_reason=9`, `brownout=true`. A later attach-only `park_servo` test made
  the board go completely offline (no HTTP/ping/USB), so the rail collapses even
  before deliberate movement. The two scan attempts above confirm the blocker is
  the shared servo/sensor power path, not the ToF wiring. This is an electrical
  finding, not a firmware success claim.
- **Software power strategy works:** with 0.1 s between 25 µs servo steps,
  stepper released during the vertical sweep, 0.5 s column cooldown, and servo
  parked at 800 µs before detach, attach-only held 10 s and a 500→800→500→800 µs
  servo test completed without a new reset. Evidence:
  `analysis/mapping/servo-delay-0.10-20261109T140434Z/`.
- `0.6.0-software-power` is deployed (837424 bytes, SHA-256
  `1d5e8a223adb7547c3459d648791fe082f075af9a044dd886a1bee91c98755ad`).
  It reduces Wi-Fi TX power to 8.5 dBm and exposes HLK alert
  `confirm_frames=3`, `energy_threshold=40`, `parked_stable_ms=1000` with the
  30–75 cm buzzer ramp. OTA reboot reported `reset_reason=3`, `brownout=false`,
  free heap ~236 KB. Evidence:
  `analysis/device/ota-software-power-20261109T144126Z/`.
- **Sequential scans now complete:** validation `20261109T141449Z` reached
  30/30 points (29 valid); coarse full `20261109T141830Z` reached 110/110 points
  (99 valid) across yaw ±45° with no new brownout. Both used HC points because
  the ToF was stale during servo motion. Evidence:
  `analysis/mapping/scan-success-20261109T144200Z/` and
  `research/mapping/scans/20261109T141830Z/`.
- **ToF motion limitation:** after a clean reboot and `sensors_start`, ToF was
  present/initialized/valid at ~72.9–74.6 cm and agreed with HC within ~0.1 cm.
  It became stale at the first servo movement; detaching the servo during
  sampling did not recover it. This is a servo transient/EMI issue on the shared
  rail, not a dead ToF. The scan pipeline correctly falls back to HC. Evidence:
  `analysis/mapping/detach-sampling-20261109T143324Z/`.
- PC 3D dashboard verified in a browser: scan selector, HC points, and HLK
  presence arc render correctly. Screenshot:
  `analysis/mapping/dashboard-20261109T143500Z/pointcloud.png`.
- Local Git `main` initialized; source/docs/tests are saved in the initial
  implementation commit (see `git log -1 --oneline`). No remote and no push;
  hosting details unconfirmed. Firmware, research and local secrets are ignored.

**Current next action:** collect the HLK dataset and train the TinyML model.
The scan power path is now workable with software timing; ToF is at-rest only,
so the HC map is the current geometry. Next: (1) collect labeled HLK windows
(empty/human/non-human; later walking/sitting/standing/lying), (2) train a small
1D CNN/MLP on the PC, (3) quantize/export and integrate it on the ESP32-S3,
(4) run a fine 5°/25 µs scan if time allows, and (5) verify the 30–75 cm buzzer
ramp and scan/motion mute. No ToF point cloud or deep-learning result is claimed
yet.

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

- Research CLI integrity verification: **81 stored artifacts checked, 0 failures**.
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
  43–44 = servo-hold-tune build and OTA; 45–46 = servo-base-reset build and OTA;
  47–48 = servo-scan-range build and OTA; 49–52 = latest workbook, sensor-ready
  build, OTA and live sensor test evidence; 53–60 = poll-throttled build, OTA,
  long-run failure, short-pass, stale/restart and wrap-target evidence;
  61–67 = 0.4.2 build, OTA, post-start health, calibration, brownout and PC
  dashboard screenshots; 68–69 = 0.5.0 sequential-scan build and attach-only
  offline observation; 70–73 = 0.5.0 OTA, USB-only sensor power, scan-mode mute
  and PC mapping health; 74 = jack-powered partial servo attach/ToF absent;
  75 = jack-powered servo small movement success; 76-77 = two sequential scan
  brownouts with ToF stale during servo movement; 78 = 0.6.0 software-power OTA;
  79 = successful validation/coarse scans with HC fallback; 80 = 0.1 s servo
  delay test; 81 = ToF motion stall with servo detached during sampling.
- Build wrappers automatically removed object/ELF/cache scratch; the latest
  build alone purged **43,644,343 bytes** of disposable build state.
- Purged **20 hash-matched intermediate binary copies / 4,025,840 bytes**.
  Their logs/manifests remain; immutable research evidence/audit was not deleted.
  The cleanup summary's initial PowerShell formatting error was repaired from
  retained manifests and verified absence, explicitly noted in its report.
- Retained binary deliverables: current `0.5.0-sequential-scan`, prior
  `0.4.2-mapping-ready`, `0.4.1-mapping-ready`, `0.4.0-mapping-ready`,
  `0.3.2-sensor-poll-throttled`,
  `0.3.1-sensor-tof-ready`, `0.3.0-sensor-bringup`, `0.2.8-servo-scan-range`,
  `0.2.7-servo-base-reset`, `0.2.6-servo-1800-hold`, `0.2.5-servo-small-test`,
  `0.2.4-pose-axes`, `0.2.3-park-pose`, `0.2.2-long-tests`, `0.2.1-servo`,
  `0.2.0-scan` and verified `0.1.4-usb` baseline, clearly separated by run
  folder. Prefer the current mapping-ready build.
  Other intentionally retained files are source, documentation, tests,
  reusable tools, build/upload/test logs, hashes, and permanent research audit.
