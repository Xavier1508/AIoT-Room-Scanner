# Live AI-gate test - 2026-11-12

Firmware **0.9.3-ai-gated-rule** (v3 32-frame logits model), 9V rail, board
IDLE. The test compares the AI-gated range beeper (`ml_alert_on`) with the
rule-only comparison (`hlk_alert_on`). Raw status snapshots are in
`analysis/device/live-*/`.

## Commands

```powershell
$py = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
& $py -B .\tools\ops\device.py command sensors_start
& $py -B .\tools\ops\device.py command hlk_alert_off
& $py -B .\tools\ops\device.py command ml_alert_on
# ... test ...
& $py -B .\tools\ops\device.py command ml_alert_off
& $py -B .\tools\ops\device.py command sensors_stop
```

## Results

| Case | What happened | Verdict |
| --- | --- | --- |
| Human at 62-78 cm, AI mode | `ml.class=human` 0.993-1.0, `gate=true`, `active=true`, interval **1425-2000 ms**, count **390 -> 399**; outside 75 cm `active=false`, `mute=out_of_range` | **Pass**: the AI prediction gates the actuator; the buzzer stops above 75 cm |
| Moving object at 75 cm, rule-only | `hlk_alert.state=active`, `last_distance_cm=75`, `last_energy=100`, interval 2000 ms, count **373 -> 383** | **Pass**: the rule beeps for any HLK target |
| Moving object held by the operator, AI mode | `ml.class=human` up to 1.0, gate opened, beeped, then changed to `empty` after the object stopped | **Limitation**: the binary empty/human model sees the operator's hand/body motion; it is not an object classifier |
| Static object at 75 cm | HLK `raw=0` / `no_target`; neither rule nor AI beeped | **Null result**: the LD2410 needs movement and its gate resolution is about 75 cm |

Evidence:

- Human: `analysis/device/live-ai-gate-human-20261112T035842Z/human_70cm.jsonl`
- Rule/AI moving object (50 cm): `analysis/device/live-object-20261112T035433Z/`
- Rule/AI moving object (75-80 cm): `analysis/device/live-object-20261112T035603Z/`
- Static object (75 cm): `analysis/device/live-static-20261112T035733Z/`
- AI-only static object (50 cm): `analysis/device/live-ai-gate-20261112T035336Z/`

## Interpretation for the exam

- **Point g:** demonstrated. The v3 model's `human`/`empty` decision opens or
  closes the actuator path; the HLK range rule only supplies the 30-75 cm
  timing. The AI does not beep outside 75 cm.
- **Point h:** the rule-only path beeps for a moving HLK target at 75 cm while
  the AI path adds the human gate. The comparison is honest only for targets
  that the HLK can see. A moving object held by a person is classified as
  `human` (observed confidence up to 1.0), so the current binary model cannot
  claim non-human rejection; a static object is not detected by the HLK at all.
- The beep count is cumulative across mode switches; it is not reset per run.

## Notes

- The HLK LD2410 gate resolution is about **75 cm**; targets at 50 cm were
  invisible (`raw=0`). The 30-75 cm rule therefore starts at the first gate,
  not at 30 cm.
- No brownout occurred; the board stayed IDLE, servo detached and stepper
  released after the tests.
