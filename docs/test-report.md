# Test report — workbook Uji_dan_hasil IDs

This report distinguishes measured software/device observations, user statements,
and physical results. No synthetic fixture is a live radar result. Initial Excel
had every test as Belum diuji. Original workbook is not modified in Downloads.

| ID | Status currently established | Evidence / remaining limits |
|---|---|---|
| T01 | Lulus — identification | esptool identify-20261105T124021Z: ESP32-S3 rev0.2, 16MB flash, native USB Serial/JTAG COM9. Label N16R8 remains historical user report. |
| T02 | Lulus — user checklist only | User confirmed jack/loads removed and USB-only. No rail-voltage/current/backfeed measurement. |
| T03 | Lulus - build | Current 0.5.0-sequential-scan build, application 837088 bytes / slot 6553600. Pinned toolchain, source/binary hashes in manifest. Real LAN OTA deployed. |
| T04 | Lulus — software/USB scope | Upload verified hashes; current version returned IDLE/no arms and passed the seven-case USB check with 48 synthetic assertions. Prior 0.1.4 power-cycle/three paced runs are historical checks. This does not measure pin voltage or prove physical actuators. |
| T05 | Lulus — physical confirmation | LAN buzzer test entered BUZZER_TEST, returned IDLE/output OFF; user heard three beep pulses. Evidence `analysis/device/buzzer-20261105T170632Z/`. |
| T06 | Lulus parsial — UART only | 747 valid HLK frames, 0 rejected, 17,181 bytes; decoded target/distance/energy. User observed a table but expected <10 cm while frame said ~30 cm. Distance is uncalibrated; wiring/5V is user-reported, not independently measured. |
| T07 | Tertunda — supply blocked | User reports shield/unknown actuator source; shield input reported about 7–12 V but 5 V rail capacity/regulation is unverified. Motor label, ULN VCC and jumper remain unknown. |
| T08 | Tertunda — no movement after jumper | Temporary enable jumper caused indicator LEDs to illuminate, but user still saw no rotation. This is not classified as a GPIO/motor failure because ULN +/- rail, jumper contact, socket and motor cable remain unverified. |
| T09 | Lulus parsial — user-observed no-load test | User reports servo supplied from shield 5 V header with jack-only/DIP ON; voltage was not independently measured. No-load wiring followed GPIO15 mapping. |
| T10 | Lulus — physical confirmation | After 14-bit LEDC repair in 0.2.1-servo, test returned IDLE/detached and user saw the horn move. Evidence `analysis/device/servo-fixed-20261105T174510Z/`. |
| T11 | Tertunda — servo/load physical verification, brownout found | User reports the legacy small-pulse sequence moves normally and corrected the mechanical zero to 800 µs. 0.4.0 stores base 800 µs, clamp 500–1400 µs, and keeps boot detached. A 25 µs servo attach produced `reset_reason=9`/brownout; loaded movement, actual mechanical range, direction, angle, clearance and holding current remain unmeasured. |
| T12 | Lulus parsial - application OTA | Real LAN OTA installed 0.5.0-sequential-scan; board returned IDLE with stepper reference 0, servo detached, base 800 µs and no arms. Image SHA matched the server response. Electrical rail/current and rollback remain unmeasured/not provided. |
| T13 | Partial handoff ready | Source, sensor health/API/dashboard, PC calibration/scan/3D viewer, reusable tools, documentation, current firmware and handoff notes exist. Real sensor bring-up and calibration capture are measured below; full scan, mapping and model data collection remain pending. |

Additional actual checks: **87 portable C++ synthetic parser/safety/command/SSID-list**
assertions passed, including corrupt/nested/partial frames, engineering frames,
20,000 deterministic noise bytes and recovery, arm expiry/wraparound, OTA
state lock, SSID deduplication/signal sorting/capacity and strict scan-page parsing,
plus the new fine-jog/scan-mode/HLK-alert command and limit checks.
**52 Python tests** passed for image headers, local-address validation,
serial framing, SSID-byte/display/menu handling, scan yaw/tilt target
generation, scan config bounds, wall-first reconstruction, dataset CSV export,
presence wall gate and OpenAPI contract consistency.
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
| W16 | Lulus parsial - sequential-scan build, attach-only offline | 0.5.0-sequential-scan built with 837088 bytes and SHA-256 `32968459...e41c5d`. It adds sequential scan guard, servo detach between columns, HLK parking-sensor ramp 75→30 cm, scan/motion muting, 2-frame confirmation and HLK 3D overlay. The attach-only `park_servo` test made the board completely offline (no HTTP/ping/USB), confirming the rail collapses before deliberate movement. Full scan remains pending power fix. |
| W17 | Lulus parsial - 0.5.0 OTA, USB-only power and scan mute | 0.5.0-sequential-scan installed via real LAN OTA and returned IDLE/detached with stepper 0. Status exposed sequential_guard=true and alert min/max 30/75 cm, 150-2000 ms ramp. USB-only power kept web/API online but HC was stale, VL53L1X absent and HLK no data; the 5V sensor rail needs the 9V jack. `scan_mode_start` set alert_muted=true and mute_reason=scan_mode; after stop it returned no_valid_hlk. No servo attach or scan was performed. |
| W18 | Lulus parsial - jack-powered servo attach, ToF absent, board later offline | With 9V jack and USB removed, `park_servo` attached at 800 µs and held without immediate brownout; HC valid ~288.8 cm, HLK ~267 cm, VL53L1X absent with empty I2C scan. A later `sensors_stop` timed out and the board became unreachable again (ICMP/HTTP false, USB ports empty). Partial attach success does not establish stable power; ToF wiring must be re-seated. |
| W19 | Lulus parsial - jack-powered servo small movement | After recovery, `park_servo` → `servo_down_25` (800→775) → `servo_up_25` (775→800) → `release_servo` all returned ok with no brownout and reset reason 1. HC ~71.3 cm, HLK ~62 cm, ToF still absent. This establishes small servo movement under jack power; full scan still requires ToF and power stability. |
| W20 | Gagal parsial - sequential scan brownout 1 | Scan `20261109T132613Z` captured 10/30 points at yaw -10°, servo 500→950 µs. HC was valid; ToF was valid before the scan but stale from the first sample. The board reset with `reset_reason=9`, `brownout=true`. Evidence: `analysis/device/scan-brownout-20261109T132901Z/`. |
| W21 | Gagal parsial - sequential scan brownout 2 | Scan `20261109T133153Z` captured 19/30 points after parking the servo at 800 µs before detach; the second column reached 900 µs. HC was valid, ToF stale for every point, and the board reset again with `reset_reason=9`, `brownout=true`. Evidence: `analysis/device/scan-brownout-2-20261109T133435Z/`. |
| W22 | Lulus - attach-only and 0.1 s servo timing | `park_servo` at 800 µs held for 10 s with no new reset. A controlled 500→800→500→800 µs test in 25 µs steps with 0.1 s delay completed without a new reset. The earlier 0.04 s timing browned out. Evidence: `analysis/mapping/servo-delay-0.10-20261109T140434Z/`. |
| W23 | Lulus - validation sequential scan | Scan `20261109T141449Z` completed 30/30 points (29 valid) at yaw ±10°, tilt 500–950 µs, with stepper released during the sweep, 0.1 s servo delay and 0.5 s cooldown. No new brownout; HC fallback because ToF was stale. Evidence: `research/mapping/scans/20261109T141449Z/`. |
| W24 | Lulus - coarse full sequential scan | Scan `20261109T141830Z` completed 110/110 points (99 valid) across yaw ±45° (10° step), tilt 500–950 µs (50 µs step). No new brownout. This is the first full coarse scan; points are HC-based. Evidence: `research/mapping/scans/20261109T141830Z/`. |
| W25 | Lulus parsial - 0.6.0 OTA and ToF motion limitation | `0.6.0-software-power` installed over LAN OTA with Wi-Fi TX 8.5 dBm, HLK confirm 3 frames, energy 40, parked stable 1000 ms. ToF at rest was valid ~72.9–74.6 cm and agreed with HC within ~0.1 cm, but became stale at the first servo movement; detaching the servo during sampling did not recover it. Scans correctly use HC fallback. Evidence: `analysis/device/ota-software-power-20261109T144126Z/`, `analysis/mapping/detach-sampling-20261109T143324Z/`. |
| W26 | Lulus - PC 3D dashboard render | Browser test loaded `http://127.0.0.1:8000/`, showed `0.6.0-software-power`, scan selector, HC points and HLK presence arc. Screenshot: `analysis/mapping/dashboard-20261109T143500Z/pointcloud.png`. |
| W27 | Lulus build - 0.6.1 ToF watchdog, OTA pending | `0.6.1-tof-watchdog` built at 837856 bytes, SHA-256 `dc9f968e...f285`. It adds `Wire.setTimeOut(50)`, suspends ToF polling after 3 s without data-ready, retries after 5 s and every 10 s on failure, and exposes `tof_recoveries`/`tof_stall_suspended`. Not OTA-installed yet; board needs a power cycle. Evidence: `analysis/platformio/build-20261109T151241Z/`. |
| W28 | Gagal - board HTTP hang after scan from released stepper | A validation scan from a released-stepper start captured 2/30 points and then `/api/status` timed out; ping was intermittent and the web server stayed unresponsive. No brownout was read before the hang. Power cycle required before 0.6.1 OTA. The earlier 0.6.0 coarse 110/110 scan remains valid; no new scan is claimed from this failed run. |
| W29 | Lulus - 0.6.1 ToF watchdog OTA | `0.6.1-tof-watchdog` installed over LAN OTA (837856 bytes, SHA-256 `dc9f968e...f285`). Reboot reported `reset_reason=3`, `brownout=false`; sensors then reported HC/ToF/HLK OK, ToF ~75 cm, `tof_recoveries=0`. Evidence: `analysis/device/ota-tof-watchdog-20261109T181258Z/`. |
| W30 | Lulus - 0.6.1 validation and coarse ToF scans | Validation `20261109T180145Z` completed 30/30 (28 ToF + 2 HC); coarse `20261109T180415Z` completed 110/110 (106 valid, 103 ToF + 3 HC) across yaw ±45°. Watchdog recovered ToF 2 and 10 times; no new brownout, board stayed responsive, stepper released after scan. Evidence: `analysis/mapping/scan-success-061-20261109T181300Z/`, screenshot `analysis/mapping/dashboard-20261109T181300Z/final-tof-map.png`. |
| W31 | Lulus pipeline - binary empty/human training, rule baseline wins | 2,234 empty frames (0% moving-energy positives) + 3,342 human frames (93.9% positive) produced 1,387 windows. The 1D CNN reached 82.7% validation accuracy (empty recall 91.0%, human recall 77.2%, confusion `[[101,10],[38,129]]`). A rule `max(moving_energy)>0` reached 100% on the same split. The binary task is rule-separable; the DL model is retained as a pipeline baseline, not deployed. Evidence: `analysis/mapping/ml-training-20261109T193000Z/`, `research/mapping/ml/model-empty-human/`. |
| W32 | Lulus - 0.7.1 scan60-safe after hard-reset hang | `0.7.0-scan60` added a ToF XSHUT hard reset but hung the main loop when the ToF was truly faulted. `0.7.1-scan60-safe` removes the hard reset from the main loop, keeps yaw ±60° (684 half-steps), and preserves the suspend/recover watchdog. OTA reported `reset_reason=3`, `brownout=false`, `tof_hard_resets=0`; board stayed responsive. Evidence: `analysis/device/ota-scan60-safe-20261109T210859Z/`. |
| W33 | Lulus - 60-degree room scans and solid-block viewer | Coarse `20261109T203919Z` completed 130/130 (109 valid, 21 ToF + 88 HC); dense `20261109T205833Z` completed 247/247 (219 valid, 50 ToF + 169 HC) across yaw ±60° at 770 mm sensor height. The reconstruction produced 6 estimated boxes (one 3.28 m wall + five objects); the dashboard shows top-down 2D and 3D solid blocks. A 5°/50 µs attempt failed at 40/250 with `expired_no_action`; the PC servo retry now handles expired nudges, and the 10°/25 µs scan completed. Evidence: `analysis/mapping/scan-success-60-20261109T210900Z/`, screenshot `analysis/mapping/dashboard-20261109T210800Z/final-room-blocks.png`. |
| W34 | Lulus - software-only wall split, mount guard, distances and annotations | `reconstruct.py` now removes returns <40 cm, low table/mount returns <75 cm, and below-floor points; splits a thick wall cluster at its largest along-wall gap; labels `wall_edge`; and reports occluded sectors, `distance_m` and `nearest_m`. The dense scan yields two wall segments, two `wall_edge`, the fan and one small object. Wall display thickness uses the robust 25–75% spread (0.28 m and 0.24 m) while `width_observed_m` keeps the full HC spread (0.56/0.52 m). The dashboard adds numbered block badges, dashed distance leaders, a block table, and manual label/hide/merge/reset stored in `annotations.json`. Python tests increased to 42 and passed; JS syntax passed. Screenshot: `analysis/mapping/dashboard-20261110Tpresence/room-distance-blocks-v4.png`. |
| W35 | Lulus UI check - rule presence and human marker | `presence.py` implements valid-HLK + target + energy>=40 + 30–600 cm + 3-frame confirmation with a 6 s hold; scan mode suppresses it. Unit tests cover confirmation, hold, scan suppression, threshold/range and bounded history. The AI/Presence tab shows class/confidence/distance/energy, actuator status, rule-vs-DL metrics and a live trend; the 3D/top-down views draw a human capsule/highlight with live distance. The UI was checked with an injected present frame while the board was offline; this is a UI check, not a live detection claim. Screenshots: `analysis/mapping/dashboard-20261110Tpresence/human-capsule-ui-check-v2.png`, `analysis/mapping/dashboard-20261110Tpresence/ai-presence-human-ui-check-v2.png`. |
| W36 | Lulus UI/reconstruction - yaw scale, full-width layout, 2D zoom and mount removal | The dense scan's wall thickness is minimised around yaw scale **0.85** (effective FOV ±51°); the Yaw scale input re-projects points/blocks live and remaps manual labels. The table-edge block `#6` is classified `mount` and hidden; the tall right-side block is manually labelled `wardrobe`, and the fan remains at ~0.88 m. The page uses the full desktop width, the map grid is responsive, 2D supports drag-pan and wheel/button zoom, and labels scale up to 1.6× without shrinking below base size. Tests increased to 44 and passed; JS syntax passed. Screenshots: `analysis/mapping/dashboard-20261110Tpresence/final-fullwidth-yaw085-v2.png`, `analysis/mapping/dashboard-20261110Tpresence/topdown-zoom.png`, `analysis/mapping/dashboard-20261110Tpresence/fullwidth-1920.png`. |
| W37 | Lulus UI/data - room prior, selection/labels and 3D object export | User-tuned yaw **0.76** (effective FOV ±45.6°). Per-scan room prior: bedroom 2.70×2.20 m = 5.94 m², bathroom 1.50×1.50 = 2.25 m², desk niche 0.40 m², total 8.59 m²; prior bed 2.00×1.20×0.57 m and wardrobe 0.70×0.60×2.00 m are dashed/toggleable. The measured wall and fan remain; the former `#6` table edge is hidden. Right-drag orbit/pan, left-drag box selection, box click, custom labels, point labels by `point_index`, and create-box-from-selection were exercised: 31 fan points selected and labelled. `export_pointcloud.py` wrote `fan.csv`, `fan.npz`, `objects.csv` and `manifest.json`. Prior boxes are explicitly not measured/training data. Screenshot: `analysis/mapping/dashboard-20261110Tpresence/prior-room-overlay.png`. |
| W38 | Lulus UI/reconstruction - plan orientation, 3D flip fix and map rotation | The 3D projection sign was corrected (`center - y2`), so +X is right, +Y up and +Z up, matching the 2D plan. Map rotation **10.7°** makes the measured right wall vertical. Priors were re-authored to the user plan: sensor left wall, wardrobe bottom-left, bed bottom-right (2.0 m along bottom wall), chair/desk top-left, WC door left, exit door right; room 2.70×2.20 m, bathroom 1.50×1.50 m, niche 0.40 m², total 8.59 m². Prior distances: wardrobe 0.85 m, bed 0.74 m, chair 0.36 m, desk 0.76 m. Tests increased to 45 and passed. Screenshot: `analysis/mapping/dashboard-20261110Tpresence/plan-match-final.png`. |
| W39 | Lulus UI - wall/door intersection, colours, axes and scan direction | Added prior wall segments 0.12×2.2×2.4 m on left/right walls so the WC door (left, red) and exit door (right, yellow) are embedded in walls instead of floating; measured right wall touches the right wall prior. Fan is purple, desk green. The 3D projection is +X right, +Y up, +Z up; **Top 3D** gives a near-top view and the legend states X horizontal, Y vertical plan, Z height. The scan is labelled −60° (chair) → +60° (bed/wardrobe), clockwise. Tests 45 pass. Screenshots: `analysis/mapping/dashboard-20261110Tpresence/plan-match-final.png`, `analysis/mapping/dashboard-20261110Tpresence/top3d-axis.png`. |
| W40 | Lulus diagnosis - ToF fixed near reflector, ROI revert and 0.7.3 obstruction flag | `0.7.2-tof-roi8` (8×8 centered ROI) produced `wrap_target_fail` and no valid far readings, so ROI reduction was reverted. `0.7.3-tof-obstruction` adds near-reflector detection: ToF valid <500 mm while HC >1000 mm for 10 samples sets `near_reflector=true` and `health.vl53l1x=OBSTRUCTED`. Live sample: HC 111 cm, ToF mostly `wrap_target_fail` with occasional valid 13–16 cm; with hand close, HC 13–22 cm and ToF 19–31 cm. This is a fixed optical return at ~10–16 cm, not a 50 cm/4 m range limit; likely lens film/rack lip/recessed mount. Tests: 87 C++ + 45 Python pass. Evidence: `analysis/device/tof-near-reflector-20261110T115547Z/`. |
| W41 | Lulus scan/reconstruction - full 5°/25 µs ToF scan and wall-first map | After removing the protective lens cover, ToF is `range_valid` at ~2.4 m with `near_reflector=false`; calibration at 241.7 cm gave `hc_offset_mm=-5.0`, `tof_offset_mm=-23.5`. Full scan `20261110T124935Z` completed **475/475 (472 valid, 445 ToF + 27 HC)** in 16 min 11 s, yaw ±60°, tilt 500–950 µs. The new physical placement is axis-aligned: **yaw 1.00, map rotation 0.0°** (the old 0.76/10.7° was for the previous mount). `reconstruct.py` now extracts continuous axis-aligned walls first, clusters interior objects in 3D, hides the sloped-ceiling extension, and falls back to the old 2D clustering for sparse/curved scans. Result: 3 measured walls (bottom 1.96 m, right 2.85 m, top 1.64 m) plus measured desk (1.20×1.05×0.87 m), bed (2.15×0.48×0.66 m) and fan (0.57×0.37×0.53 m); 78 ceiling points hidden; 29 mount points. The prior outline was realigned to the measured walls (−0.26..2.44 × −1.06..1.50 m = 2.70×2.56 m, 6.91 m²; total 9.16 m² with bathroom). Tests: 87 C++ + 46 Python pass. Screenshot: `analysis/mapping/dashboard-20261110T124935Z/dashboard-2d3d.png`; summary: `reconstruction-summary.json`; export: `analysis/mapping/ml-export-20261110T124935Z/`. |
| W42 | Lulus UI/data - floating block sidebar, prior editor, selection priority and CSV export | Point Cloud 3D now uses a **floating right-hand sidebar** (fixed overlay, not a grid column) with **Daftar/Edit** tabs. It is closed by default; a `Blok / Prior (N)` button opens it and `×` closes it, so the 3D/2D canvases keep the full card width. Daftar groups blocks by label with global 1..N numbering and a search filter; Edit contains the prior editor (add, convert auto box, delete, 2D drag mode, 5/10 cm nudge, X/Y/Z nudge, rotation, numeric fields, Z>=0 clamp, save). Selected boxes get a white dashed outline + corner handles + `SELECTED` tag in 2D and a white edge loop in 3D. Overlap selection prefers non-wall/smaller boxes (door vs wall) and repeated clicks cycle; the sidebar row always selects the exact box. Axis ticks (0.5 m 2D, 1 m 3D) and a Skala sumbu toggle were added. Dataset tab exports per-run CSV under `research/mapping/dataset/clean|dirty/<scan>/<run>/` (`points.csv`, `objects.csv`, `manifest.json/csv`, `annotations.json`, `README.txt`, plus `dataset/index.csv`); points include `point_utc_est`, raw sensors, calibrated XYZ, point/object/prior labels, `is_mount`/`is_ceiling` and sample aggregates. Presence gate: HLK > wall + 50 cm -> `beyond_wall`, human capsule suppressed, orange diagnostic dot; no-target hold 2.5 s; 3 stable distance frames; Clear presence. Tests: 87 C++ + 52 Python pass. Screenshots: `analysis/mapping/dashboard-20261110T124935Z/sidebar-floating-closed.png`, `sidebar-floating-open.png`, `dataset-export-ui.png`. |

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
- `analysis/device/ota-sequential-050-20261109T094841Z/`
- `analysis/device/jack-servo-partial-20261109T124803Z/`
- `analysis/device/jack-servo-motion-20261109T125129Z/`
- `analysis/device/scan-brownout-20261109T132901Z/`
- `analysis/device/scan-brownout-2-20261109T133435Z/`
- `analysis/platformio/build-20261109T142743Z/`
- `analysis/platformio/build-20261109T151241Z/`
- `analysis/platformio/build-20261109T201351Z/`
- `analysis/device/ota-scan60-safe-20261109T210859Z/`
- `analysis/mapping/scan-success-60-20261109T210900Z/`
- `analysis/mapping/dashboard-20261109T210800Z/`
- `analysis/mapping/dashboard-20261110Tpresence/`
- `research/mapping/scans/20261109T203919Z/`
- `research/mapping/scans/20261109T205833Z/`
- `analysis/device/ota-tof-watchdog-20261109T181258Z/`
- `analysis/mapping/scan-success-061-20261109T181300Z/`
- `analysis/mapping/dashboard-20261109T181300Z/`
- `analysis/device/ota-software-power-20261109T144126Z/`
- `analysis/mapping/servo-delay-0.10-20261109T140434Z/`
- `analysis/mapping/single-column-20261109T140521Z/`
- `analysis/mapping/single-column-release-stepper-20261109T141243Z/`
- `analysis/mapping/detach-sampling-20261109T143324Z/`
- `analysis/mapping/scan-success-20261109T144200Z/`
- `analysis/mapping/dashboard-20261109T143500Z/`
- `research/mapping/scans/20261109T141830Z/`
- `research/mapping/scans/20261109T142924Z/`
- `research/mapping/calibration.json` (PC calibration capture)
- `analysis/device/usb-conservative-20261105T154820Z/`
- `analysis/device/usb-confirmed-20261105T154856Z/`
- `analysis/gcc/tests-20261105T160536307Z/`
- `analysis/gcc/tests-20261105T161636731Z/` (final host regression run)

The current application SHA-256 is
`36a526b600039fc148fe7012a9887da8d916556829e3a114d45eaa8086fe851c`.
Research CLI verified 102 stored evidence artifacts with zero integrity failures.
Disposable intermediate binary copies were purged after their hashes/logs were
retained; current and verified-baseline deliverables remain. No permanent
research evidence, audit or user data was deleted.

The earlier DIO40 bootloader build failure and preflight quoting failure are
retained as failed-run evidence; they are not successful firmware results.
