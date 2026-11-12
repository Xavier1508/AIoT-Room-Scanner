# Tracking sweep - measured human bearing

The LD2410C is a range-only presence radar; it has no angle. The previous
human capsule was drawn at the **current arm yaw**, so it only looked correct
when the arm happened to point at the person. The tracking sweep replaces that
with a measured bearing:

```text
HLK presence cue
  -> sequential yaw sweep (stepper) at 725 us (horizontal, 77 cm)
  -> ToF measured distance at each yaw
  -> compare with the measured scan row for the same yaw + tilt
  -> cluster adjacent angles (never average separate clusters)
  -> require HLK distance/energy consistency
  -> bearing + distance + confidence
  -> provisional lock at one strong angle (1 s verification)
  -> stationary lock: distance updates without rotating the arm
  -> local reacquire +/-20 deg, then full sweep
```

## Backend

`tools/mapping/tracking.py`

- `load_background(scan_id)`: reconstructs the selected scan for the room
  polygon/boxes and loads `ScanRangeMap` from the raw `points.csv` rows.
- `BackgroundMap.background_cm(scan_yaw, tilt_us)`: uses the measured
  ToF/HC range at the nearest scan yaw and servo pulse. The box ray-cast is
  only a fallback. This matters: at 0 deg the boxes said 250.5 cm while the
  scan row said 238.4 cm, a 12 cm error that used to confirm a wall.
- `estimate_track(samples, background)`:
  - candidate when the ToF/HC return is at least **20 cm closer** than the
    measured scan background,
  - HLK distance within **60 cm** and energy >= 40,
  - candidates are clustered by adjacent angle; a wall at one angle and a
    person at another can never average into one false position,
  - at least two angles (span >= 4 deg) and at least one ToF sample are
    required; otherwise `radar` (arc only), never a box,
  - the point must be inside the room polygon and not inside a wall/wardrobe/
    fan; the bed is occupiable.
- `run_tracking_sweep`: **sequential** -60 to +60 deg in 10 deg steps
  (120 deg of arm travel), then one 5 deg fine pass around the top clusters.
  The next full sweep starts from the opposite end. The old center-out order
  travelled about 420 deg and took up to 80 s.
- `TrackSmoother`: confirmed, then `predicted` for 1.5 s, then `stale` (dashed
  amber, last position) until 40 s. The box does not vanish after 3 s.
- `run_tracking_loop`:
  - after a confirmed bearing the arm parks on that bearing and the **lock**
    samples ToF every 200 ms; the box follows distance changes with no arm
    rotation,
  - if the beam loses the target for 1.2 s, a local +/-20 deg sweep reacquires,
  - if that fails, a full sweep runs; the last box stays visible as
    `LAST SEEN` while searching.
- A single strong ToF sample inside the room is not accepted immediately. It
  gets a **provisional lock**: the arm points at it and verifies continuously
  for 1 s. A real body stays closer than the background; a transient edge does
  not.

Server endpoints:

- `POST /api/mapping/track/start` with `confirm_power: true`
- `POST /api/mapping/track/stop`
- `GET /api/mapping/track/status`

The job refuses to start while a scan or dataset recording is running. It turns
off `ml_alert` and `hlk_alert` while tracking; the arm parks and releases at the
end.

## UI

- **Demo** tab is the default; **Advanced** reveals Overview/Scan/Calibration/
  AI-Presence/Dataset.
- Demo controls: **Track**, **Guard**, **Stop**.
- `Track`: arm sweep + stationary lock, box at the measured bearing/distance,
  buzzer muted. The raw yellow HLK dot is hidden while Track is running.
- `Guard`: arm parked, existing AI-gated range beeper active.
- `Stop`: stop tracking and both alert modes.
- Status strip: mode, sweep/lock phase, human state, bearing, distance.
- Box: standard 0.55 x 0.35 x 1.7 m; confirmed is solid, predicted/stale is
  dashed amber with `HUMAN PREDICTED` or `HUMAN LAST SEEN`. Radar-only shows an
  uncertainty arc, never a precise box.

## Live observations (2026-11-12)

- Center test with the old 800 us tilt: confirmed **21.9 deg / 128.5 cm** at
  `(1.053, 1.117) m`; another run **-31.3 deg / 81.7 cm**; a third
  **31.0 deg / 123 cm**. The box appeared in 3D/2D.
- `Track` from Guard turned the AI alert off and started the sweep; `Stop`
  parked the arm and stopped both modes. Guard after Track re-armed the AI gate.
- **Side test exposed two real defects:**
  1. The box ray-cast background was 12-30 cm too far, so a wall at 0 deg
     passed the 15 cm gate. The measured scan row fixes this.
  2. The 800 us beam tilts **7.5 deg down** and hits the bed at about
     183-200 cm. A ToF-only lock at 20 deg/183 cm was therefore the bed, not a
     person. At 725 us (horizontal, 77 cm) the same bearing sees the wall at
     **274 cm**. Tracking now uses 725 us; the bed is below the beam.
- With the person standing **beside/behind the scanner mount**, the HLK saw a
  104 cm target but the ToF at every sweep angle saw the wall (274 cm). The
  candidate point is outside the mapped room polygon and outside the +-60 deg
  cable-safe wedge. No box is drawn there. The old yellow dot at the arm yaw
  was not a person position.
- **725 us fan-side re-test:** confirmed and locked at **36.6 deg / 101 cm**,
  point `(0.737, 1.206) m`; the status strip showed `LOCKED` / `CONFIRMED`
  and the 2D box was solid green. Screenshot:
  `analysis/mapping/dashboard-20261112-ui/demo-lock-725.png`.
- While the local reacquire ran, the last box stayed visible as
  `HUMAN LAST SEEN 1.76 m / 16.5 deg` (dashed amber) instead of disappearing;
  screenshot `analysis/mapping/dashboard-20261112-ui/demo-last-seen-725.png`.
- `Stop` returned the arm to 0, released the servo, and produced no brownout.

## Fast acquisition (2026-11-12, partial live)

The first demo attempt waited at `-10 deg` while the user stood at the centre;
the sweep had not reached 0 deg, and health/presence polling from the browser
was contending with the ESP. The following changes target the demo path:

- **0 deg probe first.** Track starts with one sample at the current/0 deg
  angle. If it is a strong ToF return, a 1 s provisional lock can show the box
  in roughly 2-3 s.
- **Local +/-20 deg at 5 deg**, reusing the probe and stopping as soon as two
  adjacent angles confirm. Then an **outer +/-40 deg ring at 10 deg** only if
  the local pass failed. The full sequential -60..+60 sweep is the fallback.
- **Track-priority ESP cache.** While Track runs, `/api/mapping/health` and
  `/api/mapping/presence` serve the last tracking status instead of calling
  the ESP. Only the tracking worker reads the board. This prevents a browser
  tab from slowing the stepper.
- **Fast stepper wait.** Tracking moves sleep the nominal 100 half-steps/s
  travel time and verify once, falling back to the safe poll loop if the arm
  is still moving. Scan/calibration keeps the fully polled path.
- **Large HUD.** The Demo tab now shows a big state (`MENCARI...`,
  `MANUSIA TERKUNCI`, `TERAKHIR TERLIHAT`, `RADAR SAJA`, `CEK 9V`) plus large
  distance/bearing and a sweep progress bar, readable from ~1.5 m.
- **Radar arc during acquisition.** When only the HLK has a distance, the 2D
  and 3D views draw a dashed uncertainty arc labelled `RADAR ... sudut?`
  instead of a false human box. The raw yellow HLK dot is hidden during Track.
- **Near-field fallback.** If HLK is <=100 cm and the 725 us ToF sees the
  background, one 800 us sample is tried at the same angle; it is accepted only
  within 150 cm, inside the room, and not the bed at 1.5 m.

**Live status:** a lock at **16.5 deg / 153.6 cm** was observed with the new
mode, and the new HUD loaded. During the fast local test the board then
**brownout-reset** (`brownout_reset=true`, `reset_reason=9`), the sensors
stopped, and the stepper rejected a nudge (`Stepper nudge rejected: None`).
The arm was parked at 0, the servo released, and the sensors restarted
(health OK). A full fast-acquisition demo pass is **paused until the 9V
jack/battery is verified**. Do not claim a full live pass yet.


- The arm is limited to **+-60 deg** by the cable-safe firmware limit
  (`scanStepperLimitHalfSteps = 684`). A person beside/behind the mount at
  >60 deg cannot be measured by this head; the HLK range alone is not a
  position.
- A full sweep is roughly **20-35 s** (sequential, 725 us). The stationary lock
  updates distance about 5 times per second; acquisition is not 60 fps.
- Tracking is silent; AI Gate must be off while the arm moves. Guard is a
  separate mode. The firmware mutes ML/alerts during motion and needs about
  6.4 s to refill after parking.
- A true real-time game-style box needs a camera/depth/pose sensor or a second
  head. The current single head cannot produce a bearing for a target outside
  its sweep/room wedge.
- The 725 us background is measured for a standing torso. A person lying flat
  on the bed may be below the horizontal beam and needs the 800 us row or a
  different mount; that case is not claimed here.
- The scan background is static. If furniture is moved, re-scan or re-annotate;
  otherwise a moved object can appear as a target.
- **Brownout is a hard stop.** A board reset stops the sensors and can leave
  the stepper at a non-zero reference; park it manually, restart the sensors,
  and check the 9V jack/battery before another Track. Do not continue a demo
  through a brownout.
