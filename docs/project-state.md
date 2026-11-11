# Project state

Updated: 2026-11-12. USB bring-up, SSID discovery, LAN dashboard access, real
application OTA, sensor health and the PC mapping dashboard are verified.
**`0.9.0-hybrid-alert` is the current firmware** (v3 logits model + hybrid
HLK/AI alert) and is installed from `app0`. The TFLite Micro empty/human
classifier is live (`ready=true`, model `…-v3-logits`, arena 5,128 bytes). The
**AI alert** is verified end-to-end on 9V: the HLK 30–75 cm parking rule beeps
faster as the target approaches; the AI hybrid adds room-presence beeps at
700 ms beyond the near field, with a fast HLK trigger/release. `0.8.2-ml-alert`
crashed at boot in the ESP_TF Softmax Prepare path; the image was read back
byte-identical to the artifact, so this was a firmware/library layout issue, not
a corrupt OTA. The ToF near
reflector was the
protective lens cover; after removal, ToF is valid at ~2.4 m. The **canonical
full reference scan** `20261110T184241Z` completed **475/475 points (473 valid,
452 ToF + 21 HC)** in **33 min 44 s** with yaw 5 deg over ±60 deg, tilt 25 µs
over 500–950 µs, **8 samples/point**, dwell 500 ms and 250 ms sample interval.
Reconstruction with **yaw 1.00**, **Mirror Y ON**, and **auto-align rotation
-1.1°** produced 450 filtered points, 23 mount points, 60 ceiling points in the
final auto-aligned view, **3 measured walls + 2 measured objects
(bed, fan) + 7 priors = 12 blocks**. The measured bed #5 is labeled `bed`,
wall-snapped to `-1.2°`, and its fitted 1.834×1.536 m footprint is replaced by
the tape-measured **2.00×1.20 m** lock (same centre/angle); the fan #6 remains
`81.8°` (physically angled). The prior bed was removed; only the measured bed
remains. Wall residual after auto-align is **1.61°** with 3 walls. The new room
outline is **2.70×2.51 m** with **8.6 m² total including the bathroom**
(user measurement). The
prior layout was transferred from `20261110T124935Z` with a translation of
**dx=-0.039 m, dy=+0.137 m**. **Mirror Y is ON by default** because the scanner
yaw axis is opposite the prior/2D frame: the scan is flipped about the prior
room centre (`y=0.356 m`). A **clean fast full scan `20261111T154814Z`** then
completed **475/475 points (470 valid)** in **13.6 min** at 5°/25°, 2 samples,
100 ms interval and 200 ms dwell. It is a coverage/timing check, not the map:
the 2-sample reconstruction is noisier (bed 19 points at 20.4°, ceiling 126,
mount 33) than the 8-sample reference (bed 68 at -1.2°, ceiling 60, mount 23),
so `20261110T184241Z` and its PLY remain canonical. The dashboard now prefers
the higher-sample scan when several full scans exist. The dashboard renders
full-width 3D/2D views,
wall-first reconstruction, per-scan priors, custom labels, auto-align,
wall-constrained object fit, box/point selection, a rule-based human capsule and
the live DL classifier. ToF is `OK` (`near_reflector=false`); scans use ToF with
HC fallback. The deployed DL model is the 14,528-byte int8 **logits** variant
(softmax computed on-device), 32-frame/6-feature, with **97.38% ± 5.24%**
contiguous-block validation; the rule path remains the buzzer/safety fallback.

- Scope/physical checklist: [scope.md](scope.md).
- Handoff notes for the next model/session: [handoff-notes.md](handoff-notes.md).
- ML deployment/build/OTA checklist: [ml-deployment.md](ml-deployment.md).
- ESP32-S3 rev0.2, 16 MB quad flash, native USB Serial/JTAG COM9 identified.
- eFuse reports embedded PSRAM8MB; firmware intentionally does not enable it.
- Existing `default_16MB.csv` OTA layout read and retained. No full-flash erase.
- Complete source, LAN UI, authenticated web OTA, local provisioning tool exist.
- **Running firmware: `0.9.0-hybrid-alert`**, installed through real LAN OTA
  on 2026-11-12 from `app0`. Artifact:
  `analysis/platformio/build-20261111T172341526Z/firmware.bin`, **945,280
  bytes**, SHA-256
  `98e9261c96a4e885f82290295c80fa9f12190f66526f2d67234535be02698fa3`.
  ML is `ready=true`, model `hlk-cnn-20261111T162517Z-logits`, arena
  **5,128 bytes**. Hybrid alert: HLK `moving_energy >= 70` for 2 frames starts
  a provisional 700 ms beep, model `human >= 0.80` confirms, confident empty
  vetoes after 6.5 s, HLK `moving_energy < 20` for 1 s releases; the 30–75 cm
  parking rule remains active and has priority while beeping. Sensors `OK`;
  empty = no AI beep; the rule's near-field interval is intentionally
  distance-dependent (150–2000 ms).
- **Known-good `0.8.1` artifact:** `0.8.1-ml-empty-human`,
  `analysis/platformio/build-20261111T113650019Z/firmware.bin`, **940,592
  bytes**, SHA-256
  `3d19fa9b94df42e50b36605a2753408a027e0441b72149c0f2d9cef541b1130e`.
  `0.8.0` failed `ml_init_failed` because the TFLite Micro resolver was missing
  `MEAN`; `0.8.1` adds it, ML was `ready=true`, live `human` 99.6%, latency
  **4 ms**, arena **5,248 bytes**. Sensors ran with overall **OK**
  (HC/ToF/HLK all OK).
- **Previous firmware (superseded): `0.7.3-tof-obstruction`**.
  Artifact:
  `analysis/platformio/build-20261110T115036698Z/firmware.bin`.
  Size **838144 bytes** / OTA slot **6553600 bytes**. Application SHA-256:
  `53b3526446dead24ff85ae95c17b59f73bd023a1d126f1b41eab1d61bdef9291`.
  It adds `near_reflector`/`near_count` and `health.vl53l1x=OBSTRUCTED` when ToF
  sees a fixed return <500 mm while HC sees >1000 mm for 10 samples. The 8×8 ROI
  test (`0.7.2-tof-roi8`) produced `wrap_target_fail` and was reverted.
- **Installed firmware: `0.8.3-ml-alert-logits`**, build
  `analysis/platformio/build-20261111T144558526Z/firmware.bin`, **942,032
  bytes**, SHA-256
  `5ce5350f2e820c808d3c46d3453502e5506ef0d3fbbaee3e7c8b2f2aff3c3e08`.
  It adds `ml_alert_on/off`: when ML is ready, class `human`, confidence >=
  0.80 and the arm is idle/parked, the buzzer beeps every 700 ms; rule HLK has
  priority and remains the safety fallback. The deployed model is the **logits**
  variant (`src/ml_model_data.h` from
  `research/mapping/ml/model-empty-human-v2-logits/`): the Softmax op is
  stripped and the ESP32 computes a float32 softmax, because the ESP_TF
  TFLite-Micro Softmax Prepare path aborted on this board. Host parity max
  probability delta **0.0019**. Build/RAM: **116,544 bytes (35.6%)**; live
  arena **5,128 bytes**. The earlier `0.8.2-ml-alert` artifact
  (`analysis/platformio/build-20261111T125903948Z/firmware.bin`, 941,920 bytes,
  SHA-256 `ca6bb359…91bf`) is retained as failure evidence; its flash readback
  matched the artifact byte-for-byte, so the OTA was not corrupt.
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
- Portable tests: **87 C++ assertions + 64 Python tests passed**; dashboard JS
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
- TinyML data path added: the PC dashboard **Dataset** tab and
  `tools/mapping/ml/collect.py` record labeled HLK frames to
  `research/mapping/ml/<UTC>-<label>/frames.jsonl`. A test recording wrote
  18 frames. `tools/mapping/ml/train.py` trains a small 1D CNN and exports
  `model.tflite`/`model_data.h`; training itself is pending real labeled data.
  On-device inference is **not** integrated yet and must run only when parked.
- TensorFlow **2.21.0** is installed in `tools/mapping/ml/.venv` (Python 3.12,
  CPU-only). A synthetic two-class smoke test trained a 1D CNN and exported an
  8,040-byte int8 TFLite model plus `model_data.h`; the training/export pipeline
  is proven. `train.py` now splits by session and normalizes using training data
  only, with a chronological per-session fallback.
- Clean **empty baseline** recorded: `20261109T183825Z-empty`, **2,234 frames**,
  `moving_energy=0` for every frame; HLK target state 0/2 (stationary
  background). A 623-frame partial human session had only 12 frames with
  `moving_energy>0`; it and an 18-frame recorder test were moved to
  `research/mapping/ml_partial/` so the default training root contains only the
  clean empty baseline. A new human session is pending operator readiness.
- First binary model trained: human session `20261109T190639Z-human` has
  **3,342 frames**, **93.9%** with `moving_energy>0`; total 5,576 frames and
  1,387 windows (16 frames, stride 4). The 1D CNN reached **82.7% validation
  accuracy** (empty recall 91.0%, human recall 77.2%, confusion
  `[[101,10],[38,129]]`). A simple rule `max(moving_energy)>0` reached **100%**
  on the same validation split. The binary empty-vs-human task is
  rule-separable; the DL model is **not deployed** as the primary detector.
  Artifacts: `research/mapping/ml/model-empty-human/`; evidence:
  `analysis/mapping/ml-training-20261109T193000Z/`.
- **v2 binary model deployed:** 32-frame/6-feature 1D CNN, contiguous 5-block
  validation **97.38% ± 5.24%**, int8 **14,584 bytes**, classes
  `empty/human`. Firmware `0.8.1-ml-empty-human` uses ESP_TF 2.1.1 / TFLite
  Micro with a 64 KiB arena; `/api/status.ml` exposes class, confidence,
  latency, inference count, arena use and mute reason. Live after OTA:
  `ready=true`, `human` **99.6%**, latency **4 ms**, arena **5,248 bytes**.
  Rule HLK remains the buzzer/safety fallback; see `docs/ml-deployment.md`.
- **v2 logits redeploy (`0.8.3-ml-alert-logits`):** the deployed model drops the
  Softmax op (14,528 bytes, `research/mapping/ml/model-empty-human-v2-logits/`)
  because the ESP_TF Softmax Prepare path aborted on this board; softmax is
  computed in float32 on-device. Arena **5,128 bytes**. Adds `ml_alert_on/off`
  (human + confidence >= 0.80, 700 ms beep, rule HLK priority).
- **v3 retrain (`0.9.0-hybrid-alert`):** 32-frame model retrained on four
  sessions (7,784 frames); CV **97.28% ± 4.70%** (hard fold 87.96%, human recall
  79.1%). v2 scored only **57.73%** on the new sessions (227/262 empty windows
  predicted `human`), so v3 replaces it. Deployed logits model:
  `research/mapping/ml/model-empty-human-v3-logits/`. Hybrid policy: HLK fast
  trigger/release, model confirm/veto, parking rule priority. Tests: **102 C++
  + 64 Python**.
- Next DL target must be harder: human vs non-human, stationary-human presence,
  or activity classification. Keep the rule-based movement/presence baseline
  for the demo until a harder model beats it on a held-out session.
- `0.6.1-tof-watchdog` is **OTA-installed** (837856 bytes, SHA-256
  `dc9f968e67b840dd70b4c79c16844e85df87c64b6cedf0d2f185f7cfa9dcf285`). It adds
  `Wire.setTimeOut(50)`, suspends ToF polling after 3 s without data-ready,
  retries after 5 s, and retries every 10 s on failure. Status exposes
  `tof_recoveries` and `tof_stall_suspended`. OTA reboot reported
  `reset_reason=3`, `brownout=false`; sensors then reported HC/ToF/HLK OK.
  Evidence: `analysis/device/ota-tof-watchdog-20261109T181258Z/`.
- **0.6.1 scans succeed with ToF recovery:** validation `20261109T180145Z`
  completed 30/30 points (30 valid, 28 ToF + 2 HC); coarse full
  `20261109T180415Z` completed 110/110 points (106 valid, 103 ToF + 3 HC)
  across yaw ±45°. The watchdog recovered the ToF 2 and 10 times respectively;
  no new brownout and the board stayed responsive. Stepper was released after
  the scan. Evidence:
  `analysis/mapping/scan-success-061-20261109T181300Z/`.
- Final dashboard render: `0.6.1-tof-watchdog`, 110-point coarse map, cyan ToF
  points, orange HC points and magenta HLK arc. Screenshot:
  `analysis/mapping/dashboard-20261109T181300Z/final-tof-map.png`.
- `0.7.0-scan60` added a ToF XSHUT hard reset, but when the ToF was truly
  faulted the reset blocked the main loop and the board became unresponsive.
  `0.7.1-scan60-safe` removes the hard reset from the main loop, keeps yaw
  ±60° (684 half-steps), and keeps the 0.6.1-style suspend/recover watchdog.
  OTA evidence: `analysis/device/ota-scan60-safe-20261109T210859Z/`.
- **0.7.1 room scans:** coarse `20261109T203919Z` 130/130 points (109 valid,
  21 ToF + 88 HC); dense `20261109T205833Z` 247/247 points (219 valid,
  50 ToF + 169 HC) across yaw ±60°, sensor height 770 mm. No new brownout;
  stepper released after scan. Evidence:
  `analysis/mapping/scan-success-60-20261109T210900Z/`.
- **Top-down + solid-block viewer:** `reconstruct.py` projects points to a
  top-down grid, clusters them, splits a thick wall cluster at its largest
  along-wall gap, fits oriented rectangles and extrudes estimated boxes. For
  the older 0.7.1 placement, yaw 0.76 + map rotation 10.7° made the measured
  right wall vertical. The plan frame has the sensor on the left wall, wardrobe
  bottom-left, bed bottom-right, chair/desk top-left, WC door left and exit door
  right. The table-edge block `#6` is classified `mount` and hidden. The
  dashboard shows 3D isometric and top-down 2D side by side with
  Points/Blocks/Both, Jarak and Prior toggles.
  Screenshot: `analysis/mapping/dashboard-20261110Tpresence/plan-match-final.png`.
- **3D projection fix:** the old projection put +Y downward (`center + y2`),
  making the 3D view vertically flipped relative to the 2D plan. The projection
  now uses +X right, +Y up and +Z up (`center - y2`), with an isometric default
  (`viewYaw -0.65`, `viewPitch 0.55`, zoom 1.4). **Top 3D** switches to a
  near-top view; the legend states X horizontal, Y vertical plan, Z height.
   The 3D panel is now a local Three.js 0.160 WebGL scene (no CDN): orbit,
   pan and zoom; Top/Iso/Fit/Full camera presets; layer toggles for points,
   walls, priors, objects, labels and grid; click-to-select labels; floor
   grid; a Demo button that restores all layers, closes the sidebar and
   rotates slowly; and the old canvas as fallback when WebGL is unavailable.
   The 2D canvas stays the precise resize/prior editor.
   Presence now derives up to two tracks from the HLK moving and stationary
   distances when both are valid and at least **75 cm** apart (one default
   LD2410 gate), shown as H1/H2 in 3D and 2D with a `2 target (estimasi)`
   badge and radial uncertainty arcs. This is an occupancy estimate,
   not a people counter: HLK has no angle, close targets merge, and
   side-by-side people at the same distance remain one marker.
   The scan is labelled −60° (chair) → +60° (bed/wardrobe), clockwise.
- **Yaw calibration + responsive layout:** for the older 0.7.1 placement the
  commanded yaw was larger than the effective mechanical yaw; the user-tuned
  default was **yaw scale 0.76** (effective FOV ±45.6°) plus **map rotation
  10.7°**. The full ToF scan `20261110T124935Z` uses **yaw 1.00 / rotation
  0.0°** because the sensor mount was realigned and the measured walls are
  axis-aligned. The Yaw scale and Rotasi inputs re-project points/blocks live
  and remap manual labels. The page uses the full desktop width, the map grid
  is responsive, and 2D pan/zoom plus label scaling (1–1.6×) keep numbers
  readable. This remains adjustable per scan, not a measured servo curve.
- **Room prior + area:** per-scan prior. The older 0.7.1 prior was
  2.70×2.20 m bedroom = 5.94 m², bathroom 1.50×1.50 = 2.25 m², desk niche
  0.40 m², total 8.59 m², with bed 2.00×1.20×0.57 m and wardrobe
  0.70×0.60×2.00 m. The full ToF scan `20261110T124935Z` realigns the outline to
  the measured walls: **2.70×2.56 m = 6.91 m²**, total **9.16 m²** with the
  bathroom; measured desk 1.20×1.05×0.87 m, bed 2.15×0.48×0.66 m and fan
  0.57×0.37×0.53 m; wardrobe 0.70×0.60×2.00 m, chair 0.45×0.45×0.45 m and the
  two doors remain prior-only. Prior wall segments embed the doors; UI colours
  are fan purple, desk green, WC door red, exit door yellow. They are dashed,
  toggleable, per-scan data, not hard-coded, and excluded from training until
  confirmed. The newer full scan `20261110T184241Z` re-measures the outline as
  **2.70×2.51 m** with **8.6 m² total including the bathroom** (user
  measurement), keeps 3 measured walls, and finds two measured objects:
  **bed #5** at `(1.346, 0.004)` with 68 points, locked to the tape-measured
  **2.00×1.20 m**, and **fan #6** at `(0.822, 1.254)` with 33 points in the
  final mirrored view.
  The old priors were translated by `dx=-0.039 m`, `dy=+0.137 m`; #6 matches
  the old fan-sized measured object within 6 cm, supporting that transfer.
  **Mirror Y defaults ON** about the prior room-centre
  (`mirror_center_m=0.356`). **Auto luruskan** searched ±5° and selected
  **-1.1°** (3 walls, residual 1.61°). The bed is labeled `bed` and the
  wall-constrained fit snapped it to **-1.2°** (parallel to the dominant wall);
  the fan remains at **81.8°** because it is small and physically angled. The
  prior bed was removed, leaving **12 blocks** (3 measured walls + bed + fan +
  7 priors). Settings are stored per scan in `room.mirror_y`,
  `room.mirror_center_m`, `room.map_rotation_deg` and `room.snap_wall_objects`.
- **Near-field / mount guard:** returns closer than **40 cm** are excluded;
  low returns below the sensor plane inside **75 cm** and below-floor returns
  are also removed. This eliminates the table/mount corners that previously
  produced blocks hugging the sensor. The fan at ~0.89 m is retained and
  manually labelled `fan`.
- **Distance, selection and annotation UI:** each block has
  `distance_m`/`nearest_m`; top-down draws dashed leaders with `#n` tags. The
  block table lists distance, size, height, points and source. Right-drag
  orbit/pan, left-drag box select, click-box, Shift/Alt add/subtract, custom
  free-text labels with colour catalog, point labels by stable `point_index`,
  and **Buat box dari selection** are implemented. Annotations are stored per
  scan in `annotations.json`; point labels for the fan (31 points) were saved.
  Screenshot: `analysis/mapping/dashboard-20261110Tpresence/prior-room-overlay.png`.
- **3D object dataset export:** `tools/mapping/ml/export_pointcloud.py` writes
  per-label CSV/NPZ patches, `objects.csv` and `manifest.json` under
  `research/mapping/ml/pointcloud/<scan>/`. The dense scan exports 31 fan
  points. This is the 3D-object DL dataset path; the HLK time-series path is
  separate.
- **Rule presence + human marker:** `presence.py` requires valid HLK,
  `target_state>0`, `energy>=40`, 30–600 cm and 3 confirmation frames, with a
  6 s hold. The AI/Presence tab shows class, confidence, distance, energy,
  actuator status, a live energy/distance trend and rule-vs-DL metrics. The 3D
  view draws a 1.7 m human capsule; the top-down view draws a highlighted box,
  leader and live distance. Scan mode suppresses the marker. This marker is the
  rule baseline; the separate v2 DL empty/human classifier is deployed in
  firmware 0.8.1 and live, but does not drive the marker/buzzer. UI check
  screenshots:
  `analysis/mapping/dashboard-20261110Tpresence/human-capsule-ui-check-v2.png`
  and `analysis/mapping/dashboard-20261110Tpresence/ai-presence-human-ui-check-v2.png`.
- A 5°/50 µs dense attempt stopped at 40/250 with `expired_no_action`; the PC
  servo retry now checks the observed target and retries an expired nudge only
  when it did not move. The 10°/25 µs scan then completed 247/247. The final
  5°/25 µs scan `20261110T124935Z` completed **475/475 (472 valid, 445 ToF +
  27 HC)** in 16 min 11 s.
- **ToF near reflector resolved (2026-11-10):** the fixed 10–16 cm return was
  the protective lens cover. After removing it, live status is HC 241.7 cm /
  ToF 246.5 cm, `range_valid`, `near_reflector=false`, health `OK`. Calibration
  at 2.4 m: `hc_offset_mm=-5.0`, `tof_offset_mm=-23.5`, both valid rate 1.0.
  The 8×8 ROI experiment (`0.7.2-tof-roi8`) produced `wrap_target_fail` and was
  reverted. Evidence:
  `analysis/device/tof-near-reflector-20261110T115547Z/` and
  `research/mapping/calibration.json`.
- **Block sidebar + prior editor (2026-11-10):** the Point Cloud 3D tab has a
  **floating right-hand sidebar** (fixed overlay, not a grid column) with
  **Daftar/Edit** tabs. It is closed by default; a `Blok / Prior (N)` button
  opens it and the `×` button closes it, so the 3D/2D canvases keep the full
  card width. Daftar groups blocks by label with global numbering and a filter;
  Edit contains the prior editor (add, convert auto box to prior, delete, 2D
  drag mode, 5/10 cm nudge, X/Y/Z nudge, rotation, numeric fields, `Z>=0`,
  save). The selected box gets a white dashed outline/handles and `SELECTED`
  tag in 2D and a white edge loop in 3D. Overlap selection prefers
  non-wall/smaller boxes (door vs wall) and cycles on repeated clicks; the
  sidebar row selects the exact box. Axis ticks (0.5 m 2D, 1 m 3D) and a Skala
  sumbu toggle were added. **Prior UX revision:** numeric X/Y/Z/length/width/
  angle fields are the primary editor (P/L/T quick buttons removed); Enter
  applies and blurs. The selected box shows 8 white 2D handles; dragging a
  corner/edge moves only that side while the opposite side stays fixed, and
  dragging an auto box promotes it to a prior first. A white crosshair + dashed
  angle ray marks the true object centre/pivot, with a live `L x W x angle`
  tag. **Hapus is permanent:** auto boxes are written to `removed` (separate
  from temporary `hidden`), so Reset keeps objects 5/6/7 deleted. A bounded
  annotation snapshot stack adds **Ctrl+Z / Undo**; Reset asks for confirmation
  and preserves `removed` + priors. **Simpan 3D** writes an ASCII PLY plus JSON
  sidecar under `research/mapping/scenes/<scan>/` with filtered scan points and
  all measured/prior boxes (8 vertices + 12 triangles each). Partition prior is
  centred at `(-0.10, 0.50)` with `0.20 x 0.60 x 2.40 m`, between the WC door
  and the desk niche; the final demo lowers its top to **0.76 m** so the sensor
  at 0.77 m sits on top and stays visible (W50). Every save/nudge/resize/export action shows a busy spinner
  and a success/error toast; static JS/HTML/CSS are served with `charset=utf-8`.
  **Dataset export:** per-run CSV under
  `research/mapping/dataset/clean|dirty/<scan>/<run>/` with `points.csv`,
  `objects.csv`, `manifest.json/csv`, `annotations.json`, `README.txt` and
  `dataset/index.csv`; points include timestamps, raw sensors, XYZ, point/object/
  prior labels, `is_mount`/`is_ceiling` and sample aggregates. **Presence gate:**
  HLK beyond wall+50 cm -> `beyond_wall`, human capsule suppressed, orange
  diagnostic dot; no-target hold 2.5 s, stable distance 3 frames, Clear
  presence. Tests: 87 C++ + 64 Python pass. Evidence:
  `analysis/mapping/dashboard-20261110T124935Z/prior-pivot-handles.png`,
  `prior-pivot-handles-2d.png`, `save-3d-scene.png`; final scene
  `research/mapping/scenes/20261110T124935Z/20261110T173621Z.ply` (531 vertices,
  132 faces, 20,244 bytes, SHA-256 `704ab5da...d4bc09` recorded in the sidecar).
- The PC dashboard loads `/api/mapping/scans` independently of ESP32 health,
  so saved scans and the 3D map remain viewable while the board is offline.
- Local Git `main` initialized; source/docs/tests are saved in the initial
  implementation commit (see `git log -1 --oneline`). No remote and no push;
  hosting details unconfirmed. Firmware, research and local secrets are ignored.

**Current next action:** the new full scan `20261110T184241Z` is complete:
475/475 points, 3 measured walls + 2 measured objects + 8 transferred priors,
per-scan prior, block sidebar with Daftar/Edit tabs, 2D drag + one-side handle
resize + numeric prior editing, selection priority/cycle, axis ticks, Ctrl+Z,
PLY scene export, Mirror Y toggle (default ON), auto-align and wall-constrained
object fit. Labels are final: measured bed #5 (`bed`, `-1.2°`, wall-snapped)
and fan #6 (`fan`, `81.8°`, preserved); prior bed removed. **0.8.3-ml-alert-logits**
is installed and ML is live (logits model, arena 5,128 bytes); the AI alert
passed the 9V acceptance test (empty = no beep, human = 700 ms beeps, 4.2 s
release). The two 30-point validation scans (`20261111T114928Z`,
`20261111T115125Z`) are **dirty** because the operator was active in the room;
they are timing/health checks, not mapping evidence. A unified master dataset
was regenerated at `research/mapping/dataset/aiot_room_dataset_v1.csv` (8,259
rows = 475 mapping points + 7,784 HLK frames from four sessions, timestamped,
labels empty/human; SHA-256 `25ad558d…89b3`). New sessions:
`20261111T152738Z-empty` (1,079 frames, 5 min) and
`20261111T153448Z-human` (1,129 frames, 5 min). Remaining work: optionally
retrain/compare `v3`, then run the first **clean** full scan and regenerate the
master dataset + PLY. The final mapping PLY is
`research/mapping/scenes/20261110T184241Z/20261111T101430Z.ply` (Mirror Y ON,
auto-align -1.1°, wall snap ON, bed 2.00×1.20 m size lock, partition 0.76 m,
12 boxes, 450 points, SHA-256 `7f907da3…77bc`). The configured sensor anchor is
`(-0.139, 0.637, 0.77)` (partition centre); 2D/3D axes, FOV, distance leaders
and presence marks use it, and the 3D axes sit at sensor height 0.77 m.
The UI calls prior boxes **Rencana** (gambaran tambahan, bukan hasil ukur) and
shows a grouped distance/size legend below the 3D view. The DL model is
`research/mapping/ml/model-empty-human-v2/`; deployment steps are in
`docs/ml-deployment.md`. The rule path remains the buzzer/safety fallback.

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

- Research CLI integrity verification: **125 stored artifacts checked, 0 failures**.
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
  delay test; 81 = ToF motion stall with servo detached during sampling;
  82 = 0.6.1 ToF watchdog OTA; 83 = 0.6.1 validation/coarse ToF scans;
  84 = binary empty/human training and rule-baseline comparison;
  85 = 0.7.1 scan60-safe OTA; 86 = 60-degree room scans and solid-block viewer;
  87 = software-only wall split/mount guard/distance/annotations/rule presence;
  88 = final room view screenshot with distances and block table;
  89 = final robust wall-thickness display screenshot;
  90 = yaw calibration, mount removal, full-width layout and 2D zoom;
  91 = room prior, selection/labels and 3D object export;
  92 = 3D projection flip fix, map rotation and plan-aligned prior;
  93 = wall/door intersection, colours, axes and scan direction;
  94 = ToF near-reflector diagnosis and 0.7.3 obstruction firmware;
  95 = full ToF scan reconstruction summary; 96 = final dashboard screenshot;
  97 = 3D object export table; 98 = 3D object export manifest;
  99 = block sidebar/prior editor screenshot; 100 = dataset CSV export UI;
  101 = floating sidebar closed (full map); 102 = floating sidebar open (overlay);
  103 = prior size controls and saved toast; 104 = partition pivot + one-side
  resize handles (full page); 105 = Simpan 3D PLY scene status; 106 = partition
  2D pivot crosshair and 8 resize handles; 107 = new full scan full map;
  108 = new full scan top-down 2D; 109 = new full scan block list;
  110 = new full scan reconstruction summary; 111 = new full scan PLY scene
  (pre-mirror); 112 = Mirror Y ON full map; 113 = Mirror Y ON top-down 2D;
  114 = Mirror Y OFF comparison; 115 = Mirror Y ON PLY scene (pre-auto-align);
  116 = ML v2 metrics; 117 = ML v2 int8 TFLite; 118 = auto-align bed/fan full
  map; 119 = auto-align bed/fan 2D; 120 = auto-align block list; 121 = AI panel
  metrics offline; 122 = final auto-align PLY; 123 = firmware 0.8.0 build;
  124 = firmware 0.8.0 manifest; 125 = PC parity check for firmware-style
  empty/human preprocessing.
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
