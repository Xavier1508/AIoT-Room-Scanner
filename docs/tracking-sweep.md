# Tracking sweep - measured human bearing

The LD2410C is a range-only presence radar; it has no angle. The previous
human capsule was drawn at the **current arm yaw**, so it only looked correct
when the arm happened to point at the person. The tracking sweep replaces that
with a measured bearing:

```text
HLK presence cue
  -> yaw sweep (stepper) with servo at a fixed tilt
  -> ToF/HC measured distance at each yaw
  -> compare with the static scan background (ray-cast)
  -> require HLK distance/energy consistency
  -> bearing + distance + confidence
  -> alpha-beta tracker -> standard human box
```

## Backend

`tools/mapping/tracking.py`

- `load_background(scan_id)`: reconstructs the selected scan and builds a
  `BackgroundMap` from the measured boxes/room polygon.
- `BackgroundMap.raycast_cm(scan_yaw, tilt_us)`: first wall/object hit along
  the ray, including the 2.5D height check from the servo tilt.
- `estimate_track(samples, background)`:
  - candidate when `ToF/HC` is at least **15 cm closer** than the mapped
    background,
  - HLK distance must be within **60 cm** and energy >= 40,
  - candidate must be inside the room polygon and not inside a wall/wardrobe/
    fan; bed/chair are occupiable,
  - at least two angles must agree; otherwise `radar` (arc only).
- `TrackSmoother`: alpha-beta smooth; confirmed track, then `predicted` for a
  short time and `stale` after 3 s.
- `run_tracking_sweep`: coarse 10-degree yaw sweep over ±60 degrees, one fine
  5-degree pass around the peak; the servo is attached at the fixed tilt and
  the stepper moves outside scan mode (tested: 10-degree move, no brownout).
- `run_tracking_loop`: repeats sweeps while the job is running.

Server endpoints:

- `POST /api/mapping/track/start` with `confirm_power: true`
- `POST /api/mapping/track/stop`
- `GET /api/mapping/track/status`

The job refuses to start while a scan or dataset recording is running. It turns
off `ml_alert` and `hlk_alert` while sweeping; the arm parks and releases at the
end.

## UI

- **Demo** tab is the default; **Advanced** reveals Overview/Scan/Calibration/
  AI-Presence/Dataset.
- Demo controls: **Track**, **Guard**, **Stop**.
- `Track`: arm sweep, box at the measured bearing/distance, buzzer muted.
- `Guard`: arm parked, existing AI-gated range beeper active.
- `Stop`: stop tracking and both alert modes.
- Status strip: mode, sweep phase, human state, bearing, distance.
- Box: standard 0.55 x 0.35 x 1.7 m; confirmed is solid, predicted/stale is
  dashed amber. Radar-only shows an uncertainty arc, never a precise box.

## Live observations (2026-11-12)

- Sweep with a person at the room centre: `confirmed`, bearing **21.9 deg**,
  distance **128.5 cm**, point `(1.053, 1.117) m`.
- A second run confirmed at bearing **-31.3 deg**, distance **81.7 cm**, point
  `(0.558, 0.212) m`; the 3D/2D box appeared at the measured point.
- A later run confirmed at bearing **31.0 deg**, distance **123 cm**; the
  standard box appeared in 3D/2D at the measured point. Screenshots:
  `analysis/mapping/dashboard-20261112-ui/demo-track-confirmed.png`.
- `Track` from Guard turned the AI alert off and started the sweep; `Stop`
  parked the arm and stopped both modes. Guard after Track re-armed the AI gate.
- Empty/reflection case with HLK energy but no ToF/HC closer return: `radar`,
  no box. `Stop` returned the arm to 0, released the servo, and produced no
  brownout.

## Limits

- Update rate is roughly **10-20 s per sweep**, not 60 fps. The tracker
  interpolates briefly, but a fast move can lag.
- Tracking is silent; AI Gate must be off while the arm moves. Guard is a
  separate mode. The firmware mutes ML/alerts during motion and needs about
  6.4 s to refill after parking.
- A true real-time game-style box needs a camera/depth/pose sensor.
- HLK has no angle and can see reflections; the ToF/HC background delta and
  room polygon are the truth gate. A physical absorber behind the HLK may still
  be needed for strong reflections.
