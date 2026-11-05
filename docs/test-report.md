# Test report — workbook Uji_dan_hasil IDs

This report distinguishes measured software/device observations, user statements,
and physical results. No synthetic fixture is a live radar result. Initial Excel
had every test as Belum diuji. Original workbook is not modified in Downloads.

| ID | Status currently established | Evidence / remaining limits |
|---|---|---|
| T01 | Lulus — identification | esptool identify-20261105T124021Z: ESP32-S3 rev0.2, 16MB flash, native USB Serial/JTAG COM9. Label N16R8 remains historical user report. |
| T02 | Lulus — user checklist only | User confirmed jack/loads removed and USB-only. No rail-voltage/current/backfeed measurement. |
| T03 | Lulus — build | Current build-20261105T160253954Z: 0.2.0-scan, application 785856 bytes / slot 6553600. Pinned toolchain, source/binary hashes in manifest. |
| T04 | Lulus — software/USB scope | Upload verified hashes; current version returned IDLE/no arms and passed the seven-case USB check with 48 synthetic assertions. Prior 0.1.4 power-cycle/three paced runs are historical checks. This does not measure pin voltage or prove physical actuators. |
| T05 | Tertunda | Buzzer physically disconnected; no beep test/observation. |
| T06 | Tertunda | HLK physically disconnected; no real UART frames. |
| T07 | Tertunda | Motor label 5/12V, source rating, jumper, wiring readiness unknown. |
| T08 | Tertunda | No motor arming or physical rotation test authorized as ready. |
| T09 | Tertunda | Servo supply/rating and no-load mechanical readiness unverified. |
| T10 | Tertunda | No servo arming or physical movement test. |
| T11 | Tertunda | Single-device tests have not passed physically. |
| T12 | Tertunda — mandatory | OTA implemented, but network provisioning, actual version change and standalone-power verification still required. Workbook's optional wording is overridden. |
| T13 | Partial handoff ready | Source, reusable tools, contract, documentation, USB firmware and logs exist. Research/audit retained. Real LAN/OTA and physical device results remain pending; no remote push. |

Additional actual checks: **48 portable C++ synthetic parser/safety/command/SSID-list**
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
| W03 | Tertunda — user menu/connection | Numbered PowerShell setup was opened but ended before configuration was saved (exit 1; cause/message not captured). A subsequent safe status showed configured=false, connected=false. Actual user selection, credentials, Wi-Fi join and LAN access remain pending; synthetic menu tests are not real association results. |

Evidence directories (gitignored, retain locally):

- `analysis/esptool/identify-20261105T124021Z/`
- `analysis/esptool/partition-before-20261105T125601Z/`
- `analysis/platformio/build-20261105T160253954Z/`
- `analysis/esptool/flash-20261105T160603Z/`
- `analysis/device/scan-bringup-20261105T160613Z/`
- `analysis/device/scan-control-20261105T160739Z/`
- `analysis/device/usb-conservative-20261105T154820Z/`
- `analysis/device/usb-confirmed-20261105T154856Z/`
- `analysis/gcc/tests-20261105T160536307Z/`
- `analysis/gcc/tests-20261105T161636731Z/` (final host regression run)

The current application SHA-256 is
`bcb29ab0c66dbf005d696e6edf92bae966b8bda0579991024a35d7c4b3f7e546`.
Research CLI verified 16 stored evidence artifacts with zero integrity failures.
Disposable intermediate binary copies were purged after their hashes/logs were
retained; current and verified-baseline deliverables remain. No permanent
research evidence, audit or user data was deleted.

The earlier DIO40 bootloader build failure and preflight quoting failure are
retained as failed-run evidence; they are not successful firmware results.
