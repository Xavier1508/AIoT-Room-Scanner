# Test report — workbook Uji_dan_hasil IDs

This report distinguishes measured software/device observations, user statements,
and physical results. No synthetic fixture is a live radar result. Initial Excel
had every test as Belum diuji. Original workbook is not modified in Downloads.

| ID | Status currently established | Evidence / remaining limits |
|---|---|---|
| T01 | Lulus — identification | esptool identify-20261105T124021Z: ESP32-S3 rev0.2, 16MB flash, native USB Serial/JTAG COM9. Label N16R8 remains historical user report. |
| T02 | Lulus — user checklist only | User confirmed jack/loads removed and USB-only. No rail-voltage/current/backfeed measurement. |
| T03 | Lulus - build | Current 0.5.0-sequential-scan build, application 837088 bytes / slot 6553600. Pinned toolchain, source/binary hashes in manifest. OTA pending board recovery. |
| T04 | Lulus — software/USB scope | Upload verified hashes; current version returned IDLE/no arms and passed the seven-case USB check with 48 synthetic assertions. Prior 0.1.4 power-cycle/three paced runs are historical checks. This does not measure pin voltage or prove physical actuators. |
| T05 | Lulus — physical confirmation | LAN buzzer test entered BUZZER_TEST, returned IDLE/output OFF; user heard three beep pulses. Evidence `analysis/device/buzzer-20261105T170632Z/`. |
| T06 | Lulus parsial — UART only | 747 valid HLK frames, 0 rejected, 17,181 bytes; decoded target/distance/energy. User observed a table but expected <10 cm while frame said ~30 cm. Distance is uncalibrated; wiring/5V is user-reported, not independently measured. |
| T07 | Tertunda — supply blocked | User reports shield/unknown actuator source; shield input reported about 7–12 V but 5 V rail capacity/regulation is unverified. Motor label, ULN VCC and jumper remain unknown. |
| T08 | Tertunda — no movement after jumper | Temporary enable jumper caused indicator LEDs to illuminate, but user still saw no rotation. This is not classified as a GPIO/motor failure because ULN +/- rail, jumper contact, socket and motor cable remain unverified. |
| T09 | Lulus parsial — user-observed no-load test | User reports servo supplied from shield 5 V header with jack-only/DIP ON; voltage was not independently measured. No-load wiring followed GPIO15 mapping. |
| T10 | Lulus — physical confirmation | After 14-bit LEDC repair in 0.2.1-servo, test returned IDLE/detached and user saw the horn move. Evidence `analysis/device/servo-fixed-20261105T174510Z/`. |
| T11 | Tertunda — servo/load physical verification, brownout found | User reports the legacy small-pulse sequence moves normally and corrected the mechanical zero to 800 µs. 0.4.0 stores base 800 µs, clamp 500–1400 µs, and keeps boot detached. A 25 µs servo attach produced `reset_reason=9`/brownout; loaded movement, actual mechanical range, direction, angle, clearance and holding current remain unmeasured. |
| T12 | Lulus parsial - application OTA | Real LAN OTA installed 0.4.2-mapping-ready; board returned IDLE with stepper reference 0, servo detached, base 800 µs and no arms. Image SHA matched the server response. Electrical rail/current and rollback remain unmeasured/not provided. |
| T13 | Partial handoff ready | Source, sensor health/API/dashboard, PC calibration/scan/3D viewer, reusable tools, documentation, current firmware and handoff notes exist. Real sensor bring-up and calibration capture are measured below; full scan, mapping and model data collection remain pending. |

Additional actual checks: **86 portable C++ synthetic parser/safety/command/SSID-list**
assertions passed, including corrupt/nested/partial frames, engineering frames,
20,000 deterministic noise bytes and recovery, arm expiry/wraparound, OTA
state lock, SSID deduplication/signal sorting/capacity and strict scan-page parsing,
plus the new fine-jog/scan-mode/HLK-alert command and limit checks.
**20 Python tests** passed for image headers, local-address validation,
serial framing, SSID-byte/display/menu handling and OpenAPI contract consistency.
Dashboard JavaScript syntax and the PC mapping app's Python syntax passed.
These do not validate electrical wiring or physical hardware.

Actual `0.1.4-usb` device checks: **3 × 7 cases** passed, with 34 synthetic
assertions each time. Tests rejected unarmed stepper/servo, unknown/parameterized
commands, NUL-containing input and malformed provisioning. No actuator was armed.
The host deliberately uses **250 ms inter-request pacing**. Faster earlier USB
sequences had failures; this is a limited practical-console result, not proof of
high-rate USB robustness. User physical power cycle was followed by POWERON
reset code 1. The prior software-reset code 0 was unknown, not a brownout finding.

Supplementary current Wi-Fi setup tests (not additional workbook T IDs):

| ID | Result | Actual observation |
|---|---|---|
| W01 | Lulus — passive SSID discovery | ESP32-S3 scan completed; 5 AP records / 3 SSID-security choices, 0 hidden, not truncated. No credentials/association. This is one scan at the board's location, not all networks everywhere or 5 GHz. |
| W02 | Lulus — scan safety/control | Observed running scan, rejected unarmed step_test, stop cancelled scan, IDLE/no arms; UART roundtrip 360 ms includes host pacing. No actuator physically exercised. |
| W03 | Lulus — provisioning | Numbered ESP SSID selection completed and device status now reports configured/connected; no password is included in evidence. |
| W04 | Lulus — LAN dashboard/API contract | Device status reports web_ready at `192.168.1.200`, RSSI about -62 dBm. Root `/` returned HTML; `/api/status` and `/api/session` returned JSON as designed. LAN test passed auth, CSRF, POST-only control, unarmed rejection, synthetic self-test and invalid OTA rejection. |
| W05 | Lulus parsial — HLK UART | Passive LAN observation decoded 747 valid frames with no rejected/partial frames. User reports a table in front; reported ~30 cm conflicts with expected <10 cm, so physical distance/geometry is unresolved. |
| W06 | Lulus — long-test deployment | 0.2.2-long-tests installed via real LAN OTA and returned IDLE. Dashboard exposes bounded long tests; physical execution remains user-controlled and unverified. |
| W07 | Lulus — park-pose deployment | 0.2.3-park-pose installed via real LAN OTA and returned IDLE with stepper de-energized and servo detached. `park_pose` was not triggered automatically; physical direction/pose remains unverified. |
| W08 | Lulus — two-axis deployment | 0.2.4-pose-axes installed via real LAN OTA and returned IDLE. Status reported migrated reference 1024 half-step, 114-half-step stepper nudge, 2000 µs servo target, and both axes released; no physical nudge was triggered automatically. |
| W09 | Lulus — legacy servo deployment | 0.2.5-servo-small-test installed via real LAN OTA and returned IDLE with servo detached. Axis-Y controls then ran the legacy small-pulse sequence; physical movement remains user-controlled and unverified. |
| W10 | Lulus — servo hold-tune deployment | 0.2.6-servo-1800-hold installed via real LAN OTA and returned IDLE with stepper reference 0, servo detached, target 1800 µs, and default base source. No servo motion was triggered automatically. |
| W11 | Lulus — servo base-reset deployment | 0.2.7-servo-base-reset installed via real LAN OTA and returned IDLE with stepper reference 0, servo detached, saved base/target 1000 µs, and base source NVS. `servo_1800` then reset to 1800 µs; no motion was triggered automatically. |
| W12 | Lulus — servo scan-range deployment | 0.2.8-servo-scan-range installed via real LAN OTA and returned IDLE with stepper reference 0, servo detached, migrated base/target 900 µs, clamp 500–1400 µs, and `servo_1800` removed. No motion was triggered automatically. |
| W13 | Lulus parsial — sensor bring-up and ToF-ready deployment | 0.3.1-sensor-tof-ready installed via real LAN OTA. With servo explicitly parked at 800 µs and stepper de-energized, I2C scan found address 41 (`0x29`); over five status samples HC-SR04 stayed valid with 29 valid samples/0 timeouts, VL53L1X produced 77 valid samples/0 invalid/0 I2C errors (`raw_status=9`, 210–220 mm), and HLK stayed valid. HC samples were 13.7–16.7 cm. These are bring-up observations, not calibrated geometry. |
| W14 | Lulus parsial — ToF polling throttle, long-run unresolved | 0.3.2-sensor-poll-throttled reset optional XSHUT LOW→HIGH and throttled ToF reads to the 100 ms measurement interval. The first 12 snapshots/~24 s were all valid at `0x29`/raw status 9 with 279 valid samples and 0 I2C errors, but later the same boot became stale; a software stop/start did not recover it. A fresh start later reported raw status 7 (`wrap_target_fail`) with invalid samples and no I2C errors. HC-SR04 and HLK remained valid. Rail/thermal/optical target/sensor-state stability requires physical investigation. |
| W15 | Lulus parsial - mapping-ready firmware + PC dashboard, servo brownout | 0.4.2-mapping-ready installed via real LAN OTA. After `sensors_start`, health was OK/OK/OK, HC ~74 cm, ToF raw ~69 cm → calibrated ~74 cm with +50 mm offset, HLK valid, ToF errors 0. PC dashboard served and proxied the ESP32 API; calibration capture at 75 cm gave HC offset +6/+9 mm and ToF offset +56 mm, both 100% valid over five samples. A 5° stepper nudge succeeded and returned to 0; a 25 µs servo attach caused `reset_reason=9`/brownout. Full scan not run; power path must be fixed first. |
| W16 | Lulus parsial - sequential-scan build, attach-only offline | 0.5.0-sequential-scan built with 837088 bytes and SHA-256 `32968459...e41c5d`. It adds sequential scan guard, servo detach between columns, HLK parking-sensor ramp 75→30 cm, scan/motion muting, 2-frame confirmation and HLK 3D overlay. The attach-only `park_servo` test made the board completely offline (no HTTP/ping/USB), confirming the rail collapses before deliberate movement. OTA and full scan remain pending board recovery/power fix. |

Hardware result note: T05 is the first physical peripheral result. W13 confirms
live communication/range output for HC-SR04, VL53L1X and HLK under the stated
wiring, but does not prove rail voltage, absolute distance accuracy, sensor
alignment, field of view, or object identity/approach direction. Calibration
requires a measured reference target and fixed sensor geometry.

Evidence directories (gitignored, retain locally):

- `analysis/esptool/identify-20261105T124021Z/`
- `analysis/esptool/partition-before-20261105T125601Z/`
- `analysis/platformio/build-20261105T160253954Z/`
- `analysis/esptool/flash-20261105T160603Z/`
- `analysis/device/scan-bringup-20261105T160613Z/`
- `analysis/device/scan-control-20261105T160739Z/`
- `analysis/device/lan-web-20261105T170121Z/`
- `analysis/device/buzzer-20261105T170632Z/`
- `analysis/device/hlk-passive-20261105T172057Z/`
- `analysis/device/actuator-blocked-20261105T173300Z/`
- `analysis/device/ota-servo-20261105T174432Z/`
- `analysis/device/servo-fixed-20261105T174510Z/`
- `analysis/device/stepper-20261105T174814Z/`
- `analysis/device/stepper-jumper-20261105T180353Z/`
- `analysis/device/ota-long-tests-20261105T181751Z/`
- `analysis/platformio/build-20261106T164416774Z/`
- `analysis/device/ota-park-pose-20261106T164819Z/`
- `analysis/platformio/build-20261106T173907305Z/`
- `analysis/device/ota-pose-axes-20261106T174847Z/`
- `analysis/platformio/build-20261106T181633271Z/`
- `analysis/device/ota-servo-small-test-20261106T181851Z/`
- `analysis/platformio/build-20261106T201527036Z/`
- `analysis/device/ota-servo-hold-tune-20261106T201809Z/`
- `analysis/platformio/build-20261106T203007924Z/`
- `analysis/device/ota-servo-base-reset-20261106T203314Z/`
- `analysis/platformio/build-20261106T205207136Z/`
- `analysis/device/ota-servo-scan-range-20261106T205530Z/`
- `analysis/platformio/build-20261107T073911047Z/`
- `analysis/device/ota-sensor-bringup-20261107T073637Z/`
- `analysis/device/sensor-tof-ready-20261107T074113Z/`
- `analysis/platformio/build-20261107T075620661Z/`
- `analysis/device/sensor-poll-stable-20261107T075821Z/`
- `analysis/platformio/build-20261107T080555904Z/`
- `analysis/device/sensor-poll-throttled-20261107T080748Z/`
- `analysis/platformio/build-20261109T045005438Z/`
- `analysis/device/ota-mapping-ready-20261109T045135Z/`
- `analysis/platformio/build-20261109T050140592Z/`
- `analysis/device/ota-mapping-ready-041-20261109T050451Z/`
- `analysis/platformio/build-20261109T051721344Z/`
- `analysis/device/ota-mapping-ready-042-20261109T052016Z/`
- `analysis/mapping/dashboard-20261109T052101Z/`
- `analysis/platformio/build-20261109T091806602Z/`
- `analysis/device/attach-only-offline-20261109T092304Z/`
- `research/mapping/calibration.json` (PC calibration capture)
- `analysis/device/usb-conservative-20261105T154820Z/`
- `analysis/device/usb-confirmed-20261105T154856Z/`
- `analysis/gcc/tests-20261105T160536307Z/`
- `analysis/gcc/tests-20261105T161636731Z/` (final host regression run)

The current application SHA-256 is
`f702ec54952d3cd1c5f997c8c7d77a298c6446218e1d5f5b8ed6fee9d3bf22b6`.
Research CLI verified 48 stored evidence artifacts with zero integrity failures.
Disposable intermediate binary copies were purged after their hashes/logs were
retained; current and verified-baseline deliverables remain. No permanent
research evidence, audit or user data was deleted.

The earlier DIO40 bootloader build failure and preflight quoting failure are
retained as failed-run evidence; they are not successful firmware results.
