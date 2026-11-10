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

**Jack partial attach / scan power:** with the 9V jack and USB removed, a
`park_servo` attach at 800 µs held for 10 s without a new brownout. Two early
sequential scans browned out on the second column (10/30 and 19/30 points) when
the servo moved quickly and the stepper was held energized. The working software
mitigation is: 0.1 s between 25 µs servo steps, release the stepper during the
vertical sweep, re-hold before the next yaw, park the servo at 800 µs before
detach, and 0.5 s column cooldown. With that strategy the validation scan
completed 30/30 points and the coarse full scan completed 110/110 points
(99 valid) with no new brownout. This is a software timing mitigation on the
existing 9 V/3 A supply, not a hardware power fix; faster timing or holding the
stepper during the sweep can brown out again.

**ToF motion limitation (mitigated):** ToF is valid at rest after
`sensors_start` (~72.9–74.6 cm, HC agreement within ~0.1 cm), but it can become
stale during servo movement. `0.6.1-tof-watchdog` detects 3 s without
data-ready, suspends polling, and retries after 5 s/10 s; during the successful
coarse scan it recovered 10 times and supplied 103 of 110 points (3 HC). This is
a software mitigation, not a hardware fix: a separate servo supply or shielding
would make ToF fully stable during motion. No claim is made for uninterrupted
ToF sampling during every servo move.

**Web-server hang after a failed scan (mitigated):** after a 0.6.0 validation
scan started from a released stepper and captured 2/30 points, the board's
Wi-Fi stayed visible to ping but HTTP `/api/status` timed out repeatedly. The
board was power-cycled. `0.6.1-tof-watchdog` is now installed and adds a 50 ms
I2C timeout, ToF stall suspension/recovery, and stepper release after the scan.
Validation 30/30 and coarse 110/110 scans then stayed responsive with no new
brownout. Keep this as a historical failure; do not run 0.6.0 scans.

**ToF fixed near reflector (2026-11-10):** live sampling showed HC 111 cm while
ToF mostly returned `wrap_target_fail` with occasional valid 13–16 cm; with a
hand close, HC 13–22 cm and ToF 19–31 cm. The sensor is electrically alive
(I2C 0x29, init, continuous), but its optical path sees a fixed near object at
about 10–16 cm. This is not a 50 cm/4 m range configuration limit. An 8×8
centered ROI (`0.7.2-tof-roi8`) produced `wrap_target_fail` and was reverted.
`0.7.3-tof-obstruction` adds `near_reflector`/`near_count` and reports
`health.vl53l1x=OBSTRUCTED` when ToF is valid <500 mm while HC >1000 mm for 10
samples. Likely causes: protective film/tape on the lens, rack/desk lip in
front of the lens, or a recessed mount. Remove the film and move the sensor
forward until the lens is flush/proud; then recalibrate `tofOffsetMm` against
HC. Do not use ToF for mapping while `near_reflector` is true; HC fallback is
used.

**0.7.0 ToF hard-reset hang:** `0.7.0-scan60` added an XSHUT hard reset to
the ToF watchdog. When the ToF was truly faulted, the reset blocked the main
loop and the board became unresponsive. `0.7.1-scan60-safe` removes the hard
reset from the main loop and keeps the 0.6.1 suspend/recover behavior. The board
then completed 60-degree room scans without hanging. Do not re-enable a
main-loop XSHUT reset without a separate task/timeout.

**Expired scan commands:** a dense 5°/50 µs scan stopped at 40/250 with
`expired_no_action`; the ToF fault delayed the command queue beyond the
firmware's 500 ms expiry. The PC `servo_to` now checks the observed target and
retries an expired nudge only if the servo did not move. A 10°/25 µs scan then
completed 247/247. This is a PC-side mitigation, not a firmware queue fix.

**3D projection flip fixed:** the old 3D projection used `center + y2`, so +Y
was drawn downward and the 3D view looked vertically flipped relative to the
2D plan. The projection now uses `center - y2`, with +X right, +Y up and +Z up;
the default camera is isometric (`viewYaw -0.65`, `viewPitch 0.55`, zoom 1.4).
The 2D top-down and 3D isometric now share the same plan orientation.

**Doors and wall segments:** the WC door is on the left wall (red) and the
exit door on the right wall (yellow). Prior wall segments
0.12×2.2×2.4 m are added on both sides so each door is embedded in a wall
instead of floating in front of the measured wall. The measured right wall
still sits slightly inside the 2.7 m room rectangle; the wall prior fills the
gap so the door and wall touch. The fan is purple, the desk green.

**Scan direction:** the commanded sweep is labelled −60° (chair side) → fan →
bed/wardrobe → +60°, clockwise. The effective FOV at yaw 0.76 is ±45.6°; the
top-down view draws the start/end labels and the clockwise note.

**Estimated solid blocks:** the top-down/blocks viewer is a 2.5D estimate from
one fixed viewpoint. Returns <40 cm are removed; low table/mount returns below
the sensor plane inside 75 cm and below-floor returns are also removed. A small
thin tall cluster close to the scanner is classified `mount` and hidden. Points
are clustered, a thick wall cluster is split at its largest along-wall gap,
rectangles are fitted and extruded to the observed top. Hidden sides are
inferred; it is not a full mesh. At yaw scale 0.76 the measured dense map shows
a wall and the fan; the former table-edge block `#6` is hidden. The wall block
is 3.06 m long because it includes the corner/side surface; the intended room
rectangle is 2.70×2.20 m. Wall display thickness uses the robust 25–75% spread
while `width_observed_m` keeps the full HC beam spread.

**Room prior is an estimate, not measured data:** the prior room is
2.70×2.20 m (5.94 m²), bathroom 1.50×1.50 m (2.25 m²), desk niche ~0.40 m²,
total 8.59 m². The plan frame is sensor at the left wall, +X right, +Y up.
Prior bed 2.00×1.20×0.57 m is bottom-right with its long axis along the bottom
wall; wardrobe 0.70×0.60×2.00 m is bottom-left (front ~0.85 m); chair/desk are
top-left; WC door is left, exit door right. They are dashed and toggleable,
based on photos/user measurements and stored per scan, not hard-coded. Do not
treat prior boxes as measured evidence or include them in training until
confirmed. The measured wall/wardrobe block is not the 70 cm wardrobe; the
actual wardrobe is the bottom-left prior.

**Yaw scale is provisional:** the commanded yaw is larger than the effective
mechanical yaw. The user-tuned default is **0.76** plus **map rotation 10.7°**
to make the measured right wall vertical; effective FOV is about ±45.6°, not
±60°. At 0.76 the wall panels merge; 0.77–0.80 separates them. The Yaw scale and
Rotasi inputs re-project points/blocks live, and manual labels are remapped to
the nearest box. Confirm the values against a known target before treating the
map as calibrated.

**Bed and wardrobe:** the tall right-side measured block is not the 70 cm
wardrobe; it is the right wall/corner. The actual wardrobe is the bottom-left
prior (front ~0.85 m), and the bed is the bottom-right prior with its long axis
along the bottom wall. Confirm the prior placement visually before labelling
them as measured. A new ToF/fine scan is needed for measured points on the low
bed and the bottom-left wardrobe.

**Manual annotations are per scan:** labels/hide/merge, point labels, label
catalog, manual/prior boxes and the room outline are stored in
`research/mapping/scans/<id>/annotations.json`. Box ids change when the yaw
scale changes; annotations are remapped to the nearest box within 0.8 m, so
verify them after a large scale change and reset if a hide/merge maps wrongly.
Point labels use the stable `point_index` from `points.csv`. The current dense
scan has a manual `fan` box, a prior bed and a prior wardrobe, and 31 fan points
labelled for the 3D dataset.

**3D object export is not a trained model:** `ml/export_pointcloud.py` writes
per-label CSV/NPZ patches and `objects.csv`. Prior boxes have zero measured
points and must not be treated as training samples until confirmed. The HLK
`empty`/`human`/`non-human` model is a separate time-series task; the 3D object
export is for 3D classification/segmentation.

**Live human marker is rule-based:** the 3D capsule/top-down highlight appears
only after 3 confirmed HLK frames with `energy>=40` and 30–600 cm. It is
suppressed during scan mode and holds for 6 s after the target disappears. It
is not a trained human/non-human classifier and can be triggered by other
moving targets. The DL model is not deployed; non-human live markers wait for
the 3-class model and a true held-out session.

**Binary empty/human is rule-separable:** the clean dataset has 2,234 empty
frames with zero moving-energy positives and 3,342 human frames with 93.9%
positive. A rule `max(moving_energy)>0` reached 100% on the same validation
split, while the 1D CNN reached 82.7% (human recall 77.2%). Do not deploy the
binary DL model as the primary detector; keep the rule for movement/presence.
A meaningful DL target must be harder: human vs non-human, stationary-human
presence, or activity classification, evaluated on a true held-out session.

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
