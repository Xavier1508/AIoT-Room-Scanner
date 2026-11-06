# Test report — workbook Uji_dan_hasil IDs

This report distinguishes measured software/device observations, user statements,
and physical results. No synthetic fixture is a live radar result. Initial Excel
had every test as Belum diuji. Original workbook is not modified in Downloads.

| ID | Status currently established | Evidence / remaining limits |
|---|---|---|
| T01 | Lulus — identification | esptool identify-20261105T124021Z: ESP32-S3 rev0.2, 16MB flash, native USB Serial/JTAG COM9. Label N16R8 remains historical user report. |
| T02 | Lulus — user checklist only | User confirmed jack/loads removed and USB-only. No rail-voltage/current/backfeed measurement. |
| T03 | Lulus — build | Current build-20261106T173907305Z: 0.2.4-pose-axes, application 797168 bytes / slot 6553600. Pinned toolchain, source/binary hashes in manifest. |
| T04 | Lulus — software/USB scope | Upload verified hashes; current version returned IDLE/no arms and passed the seven-case USB check with 48 synthetic assertions. Prior 0.1.4 power-cycle/three paced runs are historical checks. This does not measure pin voltage or prove physical actuators. |
| T05 | Lulus — physical confirmation | LAN buzzer test entered BUZZER_TEST, returned IDLE/output OFF; user heard three beep pulses. Evidence `analysis/device/buzzer-20261105T170632Z/`. |
| T06 | Lulus parsial — UART only | 747 valid HLK frames, 0 rejected, 17,181 bytes; decoded target/distance/energy. User observed a table but expected <10 cm while frame said ~30 cm. Distance is uncalibrated; wiring/5V is user-reported, not independently measured. |
| T07 | Tertunda — supply blocked | User reports shield/unknown actuator source; shield input reported about 7–12 V but 5 V rail capacity/regulation is unverified. Motor label, ULN VCC and jumper remain unknown. |
| T08 | Tertunda — no movement after jumper | Temporary enable jumper caused indicator LEDs to illuminate, but user still saw no rotation. This is not classified as a GPIO/motor failure because ULN +/- rail, jumper contact, socket and motor cable remain unverified. |
| T09 | Lulus parsial — user-observed no-load test | User reports servo supplied from shield 5 V header with jack-only/DIP ON; voltage was not independently measured. No-load wiring followed GPIO15 mapping. |
| T10 | Lulus — physical confirmation | After 14-bit LEDC repair in 0.2.1-servo, test returned IDLE/detached and user saw the horn move. Evidence `analysis/device/servo-fixed-20261105T174510Z/`. |
| T11 | Tertunda — two-axis physical verification | Separate stepper/servo controls, 114-half-step nudge, ±50 µs servo nudge, independent release and NVS references are software-tested and deployed. Physical direction, angle, clearance and holding current remain unobserved. |
| T12 | Lulus parsial — application OTA | Wi-Fi/LAN contract passed and real OTA changed 0.2.0-scan through 0.2.4-pose-axes; each successful new version returned IDLE with no arms. The final image SHA matched the server response; electrical rail/current/rollback were not independently measured/tested. |
| T13 | Partial handoff ready | Source, reusable tools, contract, documentation, current two-axis firmware and logs exist. Research/audit retained. Real OTA is verified; physical axis direction/pose remains user-controlled and unverified; no remote push. |

Additional actual checks: **68 portable C++ synthetic parser/safety/command/SSID-list**
assertions passed, including corrupt/nested/partial frames, engineering frames,
20,000 deterministic noise bytes and recovery, arm expiry/wraparound, and OTA
state lock, SSID deduplication/signal sorting/capacity and strict scan-page parsing.
**19 Python tests** passed for image headers, local-address validation,
serial framing, SSID-byte/display/menu handling and OpenAPI contract consistency. Dashboard JavaScript syntax
passed. These do not validate electrical wiring or physical hardware.

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

Hardware result note: T05 is the first physical peripheral result. T06 remains
pending until HLK supply and crossed wiring are confirmed by the user; a valid
UART frame will prove communication, not rail voltage, presence identity or
object approach direction.

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
- `analysis/device/usb-conservative-20261105T154820Z/`
- `analysis/device/usb-confirmed-20261105T154856Z/`
- `analysis/gcc/tests-20261105T160536307Z/`
- `analysis/gcc/tests-20261105T161636731Z/` (final host regression run)

The current application SHA-256 is
`69edf4a345afe88dd4968f0aa0dccdba0b70bbd231c0c2eb2377a98b4ed22e97`.
Research CLI verified 40 stored evidence artifacts with zero integrity failures.
Disposable intermediate binary copies were purged after their hashes/logs were
retained; current and verified-baseline deliverables remain. No permanent
research evidence, audit or user data was deleted.

The earlier DIO40 bootloader build failure and preflight quoting failure are
retained as failed-run evidence; they are not successful firmware results.
