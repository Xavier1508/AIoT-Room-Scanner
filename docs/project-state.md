# Project state

Updated: 2026-11-05. USB bring-up and SSID-discovery phase handed off;
network provisioning, real OTA and physical peripheral tests remain pending.

- Scope/physical checklist: [scope.md](scope.md).
- ESP32-S3 rev0.2, 16 MB quad flash, native USB Serial/JTAG COM9 identified.
- eFuse reports embedded PSRAM8MB; firmware intentionally does not enable it.
- Existing `default_16MB.csv` OTA layout read and retained. No full-flash erase.
- Complete source, LAN UI, authenticated web OTA, local provisioning tool exist.
- **Running firmware: `0.2.0-scan`**, built and flashed with verified hashes.
  Current application artifact: `analysis/platformio/build-20261105T160253954Z/firmware.bin`.
  Size **785856 bytes** / OTA slot **6553600 bytes**. Hash is in that run's manifest.
  Application SHA-256: `bcb29ab0c66dbf005d696e6edf92bae966b8bda0579991024a35d7c4b3f7e546`.
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
- Current `0.2.0-scan`: USB seven-case verification passed, **48/48 on-device
  synthetic assertions**, IDLE with no arms. Real ESP passive scan completed:
  **5 APs / 3 unique SSID-security choices**, no hidden SSID, no truncation.
  Credentials were not entered and no Wi-Fi association was attempted by this test.
  Evidence: `analysis/device/scan-bringup-20261105T160613Z/`.
- Live scan/stop test observed scan running, rejected unarmed step_test with
  `wifi_scan_in_progress_actuators_idle`, then cancelled scan and returned IDLE.
  Roundtrip 360 ms includes deliberate host pacing; not measured physical stop
  latency. Evidence: `analysis/device/scan-control-20261105T160739Z/`.
- Portable tests: **48 C++ assertions + 19 Python tests passed**; dashboard JS
  syntax check passed. Physical peripherals and live network remain separate.
- Earlier USB failures/experimental images are recorded in known-issues.md;
  do not use the unsuccessful 0.1.1/0.1.2 console experiments.
- Wi-Fi credentials have NOT been requested in chat, read from Windows, or guessed.
- LAN/real OTA/peripheral hardware tests are NOT yet established.
- Keep USB attached and jack/peripheral loads disconnected until instructed.
- Local Git `main` initialized; source/docs/tests are saved in the initial
  implementation commit (see `git log -1 --oneline`). No remote and no push;
  hosting details unconfirmed. Firmware, research and local secrets are ignored.

**Current next action:** run `tools/ops/setup.ps1` when ready. It presents a
numbered ESP-scanned SSID menu, then asks for Wi-Fi and unique web passwords.
The old manual-SSID setup was cancelled at the user's request. The replacement
window was opened but ended with exit code 1 before configuration was stored;
the exact user-terminal message/cause was not captured. A subsequent safe status
check still showed configured=false, connected=false, IDLE. Do not assume a
password/network error or a successful join from that window's exit alone.

On a future setup error the window now stays visible until Enter and saves only
a fixed stage/error type (no input or exception text) under analysis/device.
Only one monitor/setup process may own COM9. Never send passwords to chat or read
`tools/ops/device.local.json` into agent output. No setup window is currently
left running by the agent.

SSID discovery is passive 2.4 GHz only, not host/IP/port scanning. At most 48
deduplicated strongest choices are retained. Hidden SSID has a manual fallback.
Credentials are sent only after the user explicitly selects an authorized network.

After the provisioning process completes: use `device.py status` and `lan-test`
against only the IP obtained from the board, then ask the user to unplug USB
before connecting jack power. Prove standalone LAN access, build a different
version, perform real OTA, and verify new version + IDLE + no arms. T12 is pending
until those real steps succeed. Motor/servo still require physical readiness.

Unexpected side effect: PlatformIO initially auto-installed OpenOCD
`tool-openocd-esp32@2.1100.20220706` outside the workspace. The triggering explicit
upload_protocol option was removed and dependency preflight added. The user then
explicitly approved deleting only that extra folder. It was inventoried again
and removed: 897 files / 6,188,429 bytes. No other global packages were deleted.

## Evidence and storage handoff

- Research CLI integrity verification: **16 stored artifacts checked, 0 failures**.
  Evidence 8 = current build manifest; 9 = upload; 10 = USB verification;
  11 = actual passive scan; 12 = live scan/stop; 13/14 = host tests;
  15 = intermediate-retention cleanup; 16 = current application binary.
- Build wrappers automatically removed object/ELF/cache scratch; the latest
  build alone purged **43,644,343 bytes** of disposable build state.
- Purged **20 hash-matched intermediate binary copies / 4,025,840 bytes**.
  Their logs/manifests remain; immutable research evidence/audit was not deleted.
  The cleanup summary's initial PowerShell formatting error was repaired from
  retained manifests and verified absence, explicitly noted in its report.
- Retained binary deliverables: current `0.2.0-scan` and verified `0.1.4-usb`
  baseline, clearly separated by run folder. Prefer the current scan build.
  Other intentionally retained files are source, documentation, tests,
  reusable tools, build/upload/test logs, hashes, and permanent research audit.
