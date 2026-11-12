# Deploying the empty/human 1D-CNN on the ESP32-S3

This page is the reproducible deployment path for the on-device classifier.

**Known-good `0.8.1` artifact:** `0.8.1-ml-empty-human` was OTA-installed and
live-verified on 2026-11-11: `ready=true`, `human` 99.6%, 4 ms, 5,248-byte
arena. Version `0.8.0` failed `ml_init_failed` because its resolver omitted the
model's `MEAN` op; `0.8.1` registers `AddMean()` and uses a 10-op resolver.

**`0.8.2-ml-alert` aborted on boot.** The OTA image
`analysis/platformio/build-20261111T125903948Z/firmware.bin` (941,920 bytes,
SHA-256 `ca6bb359011b1e8d69bdb6e05c562a9c6c37267a258e430aa67007df6fe791bf`)
was read back from `ota_1` byte-identical to the artifact, so the upload and
flash were not corrupt. The board aborted in `MlClassifier::begin()` →
ESP_TF TFLite-Micro `Softmax::Prepare` → `CalculateSoftmaxParams` →
`QuantizeMultiplierGreaterThanOne` (`quantization_util.cc:109`). A clean
rebuild of the identical source produced the same IROM and RAM contents (only
the build timestamp and ELF hash differ), confirming it was not a stale
artifact. A diagnostic build with a 12-byte .bss shift booted normally and
reported runtime `beta=1.000000`, `scale=0.049900`, so the trigger was the
layout-sensitive TFLite-Micro Softmax Prepare path, not the model values.

**`0.8.3-ml-alert-logits` removes the Softmax op** from the deployed model and
computes the 2-class softmax in float32 on the ESP32-S3. The trained weights
and the quantization of every other op are unchanged. Host parity against the
original softmax model: maximum probability difference **0.0019** over random
inputs. It adds `ml_alert_on/off`: human + confidence >= 0.80, arm idle/parked,
buzzer every 700 ms; rule HLK keeps priority. Artifact:
`analysis/platformio/build-20261111T144558526Z/firmware.bin`, **942,032
bytes**, SHA-256
`5ce5350f2e820c808d3c46d3453502e5506ef0d3fbbaee3e7c8b2f2aff3c3e08`.

**`0.9.3-ai-gated-rule` is the current firmware.** It retrains the 32-frame
model on four sessions (v3) and gates the existing 30–75 cm HLK range rule with
the AI prediction: the buzzer may sound only when the model says `human` with
confidence >= 0.80 **and** the target is 30–75 cm. The interval still comes from
the filtered HLK distance (150 ms near 30 cm, 2000 ms at 75 cm), so there is one
beep source and no AI beep outside the range. `hlk_alert_on` is the rule-only
comparison mode (any object) for the exam evaluation. Artifact:
`analysis/platformio/build-20261112T022751083Z/firmware.bin`, **942,720
bytes**, SHA-256
`c82805bc5c8015e7af1b560bd6eedddadcdfddd4b32210ac68e6299251c0c6fb`.
It is OTA-installed from `app0` and reports `ready=true`, model
`hlk-cnn-20261111T162517Z-logits`, arena **5,128 bytes**.

## Model

- Task: **empty vs human** (binary).
- Input: 32 consecutive HLK frames at ~5 Hz, 6 features:
  `distance_cm`, `energy`, `target_state`, `moving_energy`,
  `stationary_energy`, `delta_distance_cm`.
- Architecture: 1D CNN (16/32 filters, BatchNorm, GlobalAveragePooling,
  Dense 32, Dropout). The deployed TFLite **omits the final Softmax op** and
  exposes the two logits.
- Quantization (v3): full int8; input scale `0.01385301`, zero point `11`;
  **logits output** scale `0.05311970`, zero point `45`; softmax is computed
  on-device in float32.
- TFLite size: **14,528 bytes** (logits) from the 14,584-byte softmax model;
  generated headers: `src/ml_model_data.h`, `src/ml_model_metadata.h`.
- Dataset: v2 used 5,576 frames from the two original sessions
  (`20261109T183825Z-empty`, `20261109T190639Z-human`). v3 uses **7,784
  frames** from four sessions (adds `20261111T152738Z-empty`, 1,079 frames, and
  `20261111T153448Z-human`, 1,129 frames).
- Validation: v3 **contiguous 5-block time split per session**, mean accuracy
  **97.28% ± 4.70%**. The hard fold is 87.96% (empty recall 100%, human recall
  79.1%); this is reported, not hidden. v2 scored only **57.73%** on the new
  sessions (227 of 262 empty windows predicted `human`), so the v3 retrain was
  necessary. v3's 100% on the new sessions is training accuracy, not a
  generalization claim.
- Artifacts: `research/mapping/ml/model-empty-human-v3/`
  (`metrics.json`, `model.tflite`, `model.keras`, `labels.json`,
  `normalization.json`, `model_data.h`, `model_metadata.h`) and the deployed
  logits model in `research/mapping/ml/model-empty-human-v3-logits/`
  (`model.tflite`, `model_data.h`). The v2 artifacts remain for comparison.
- PC parity check with firmware-style preprocessing: real human window
  **99.6% human**, real empty window **99.6% empty**
  (`analysis/mapping/ml-deployment-20261111/parity.json`). This is not an
  ESP32 latency/OTA result.

## Firmware behavior

- Version: `0.9.3-ai-gated-rule`.
- Library: `nickjgniklu/ESP_TF@2.1.1` (TensorFlow Lite Micro + ESP-NN).
- Tensor arena: 64 KiB static; the retained build uses **116,576 bytes RAM
  (35.6%)** including the v3 model; the live allocator reports only
  **5,128 bytes**.
- The classifier only runs when sensors are running, HLK is valid and fresh,
  scan mode is off, no servo/stepper motion or actuator test is active, and a
  full 32-frame window has been collected. It resets after scan/motion/invalid
  data and needs about 6.4 s to refill 32 frames at 5 Hz.
- **`ml_alert_on` = AI-gated range beeper.** The v3 model must say `human`
  with confidence >= 0.80 for two consecutive inferences, and the raw HLK rule
  distance must be 30-75 cm. The beep interval comes from the distance filtered
  with a 3-frame median + EMA (150 ms at 30 cm, 2000 ms at 75 cm). There is no
  AI beep outside 75 cm; the stop is strict at 75 cm in this mode.
- **`hlk_alert_on` = rule-only comparison mode** (any object, 30-75 cm, 10 cm
  hysteresis). It is the baseline for the exam comparison; the two modes are
  exclusive. `sensors_start` defaults to the rule mode; `ml_alert_on` switches
  to the AI gate.
- The first human detection from a completely empty room still needs the 32-frame
  window (about 6.4 s). Once the model is `human`, entering 75 cm triggers the
  range beep immediately; the demo starts with the person already in the room.
  All modes are muted during scan/OTA/actuator motion or when sensors are off.

## Build

```powershell
.\tools\ops\test.ps1
.\tools\ops\build.ps1
```

`build.ps1` accepts only the reviewed `nickjgniklu/ESP_TF@2.1.1` dependency.
The retained artifact folder is printed at the end, for example:

```text
analysis/platformio/build-<utc>/
  firmware.bin
  bootloader.bin
  partitions.bin
  boot_app0.bin
  manifest.json
  usage.txt
```

The installed artifact is
`analysis/platformio/build-20261112T022751083Z/firmware.bin`, **942,720
bytes**, SHA-256
`c82805bc5c8015e7af1b560bd6eedddadcdfddd4b32210ac68e6299251c0c6fb`
(`0.9.3-ai-gated-rule`). The earlier `0.8.3` and `0.8.1` artifacts remain as
known-good fallbacks: `0.8.0` installed but reported `ml_init_failed` because
the model uses `MEAN` and the resolver did not register it; `0.8.1` adds
`resolver.AddMean()` and a 10-op resolver.

## OTA

Connect the board to the authorized LAN, confirm the current version and safe
state, then upload only `firmware.bin`:

```powershell
$py = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
& $py -B .\tools\ops\device.py status
& $py -B .\tools\ops\device.py ota .\analysis\platformio\build-20261112T022751083Z\firmware.bin --expect-version 0.9.3-ai-gated-rule
```

Do not upload `bootloader.bin`, `partitions.bin`, or `boot_app0.bin` through the
web OTA endpoint.

## Post-OTA verification

Wait for IDLE and sensors running, then check `/api/status.ml`:

```json
{
  "enabled": true,
  "ready": true,
  "error": false,
  "model_version": "hlk-cnn-20261111T162517Z-logits",
  "window": 32,
  "features": 6,
  "classes": 2,
  "window_ready": true,
  "class": "human",
  "confidence": 0.996,
  "latency_ms": 4,
  "inferences": 228,
  "arena_used_bytes": 5128,
  "mute_reason": "ok"
}
```

Checklist:

1. `enabled/ready/error` are true/true/false.
2. After ~6.4 s with valid HLK, `window_ready=true` and `class` changes.
3. `mute_reason` is `scan_or_motion` while the arm moves or scans, then
   `filling_window` for ~6.4 s, then `ok`.
4. `latency_ms` is recorded; target is well below the 200 ms frame period.
5. `arena_used_bytes` is below 65,536.
6. Empty room: DL says `empty`; person enters: DL says `human`; compare with
   the rule panel. Record screenshots and status JSON.
7. The buzzer rule remains independent; do not claim DL-driven safety.

## Regenerate the model

```powershell
& .\tools\mapping\ml\.venv\Scripts\python.exe -B `
  .\tools\mapping\ml\train.py `
  --data .\research\mapping\ml `
  --output .\research\mapping\ml\model-empty-human-v2 `
  --window 32 --stride 4 --epochs 30 --cv-blocks 5
```

Then copy the new generated headers:

```powershell
Copy-Item .\research\mapping\ml\model-empty-human-v2\model_data.h .\src\ml_model_data.h -Force
Copy-Item .\research\mapping\ml\model-empty-human-v2\model_metadata.h .\src\ml_model_metadata.h -Force
```

The test `tests/test_ml_assets.py` verifies that the firmware header bytes match
the trained `.tflite` and that the labels/window/features match the firmware
contract.
