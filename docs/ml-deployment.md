# Deploying the empty/human 1D-CNN on the ESP32-S3

This page is the reproducible deployment path for the on-device classifier.
**0.8.1-ml-empty-human is OTA-installed and live-verified** on 2026-11-11:
`ready=true`, `human` 99.6%, 4 ms, 5,248-byte arena. Version `0.8.0` failed
`ml_init_failed` because its resolver omitted the model's `MEAN` op; `0.8.1`
registers `AddMean()` and uses a 10-op resolver.

## Model

- Task: **empty vs human** (binary).
- Input: 32 consecutive HLK frames at ~5 Hz, 6 features:
  `distance_cm`, `energy`, `target_state`, `moving_energy`,
  `stationary_energy`, `delta_distance_cm`.
- Architecture: 1D CNN (16/32 filters, BatchNorm, GlobalAveragePooling,
  Dense 32, Dropout, softmax).
- Quantization: full int8, input scale `0.01664284`, zero point `19`;
  output scale `0.00390625`, zero point `-128`.
- TFLite size: **14,584 bytes**; generated headers:
  `src/ml_model_data.h`, `src/ml_model_metadata.h`.
- Dataset: 5,576 frames, 1,379 windows from the two existing sessions
  (`20261109T183825Z-empty`, `20261109T190639Z-human`).
- Validation: **contiguous 5-block time split per session**, mean accuracy
  **97.38% ± 5.24%**. The last block is the hard one (empty recall 90%,
  human recall 85%); this is reported, not hidden.
- Artifacts: `research/mapping/ml/model-empty-human-v2/`
  (`metrics.json`, `model.tflite`, `model.keras`, `labels.json`,
  `normalization.json`, `model_data.h`, `model_metadata.h`).
- PC parity check with firmware-style preprocessing: real human window
  **99.6% human**, real empty window **99.6% empty**
  (`analysis/mapping/ml-deployment-20261111/parity.json`). This is not an
  ESP32 latency/OTA result.

## Firmware behavior

- Version: `0.8.1-ml-empty-human`.
- Library: `nickjgniklu/ESP_TF@2.1.1` (TensorFlow Lite Micro + ESP-NN).
- Tensor arena: 64 KiB static; the retained build uses **116,520 bytes RAM
  (35.6%)** and **940,592 bytes flash (14.3%)** including the model; the live
  allocator reports only **5,248 bytes** used for this model.
- The classifier only runs when:
  - sensors are running,
  - HLK is valid and fresh,
  - scan mode is off,
  - no servo/stepper motion or actuator test is active,
  - a full 32-frame window has been collected.
- It resets the window after scan/motion/invalid data. After the reset it
  needs about 6.4 s to fill 32 frames at 5 Hz.
- The **rule-based HLK path remains the buzzer/safety fallback**; the DL result
  is published for the dashboard and comparison. The DL does not drive the
  buzzer until a later validation beats the rule on a held-out session.

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
`analysis/platformio/build-20261111T113650019Z/firmware.bin`,
940,592 bytes, SHA-256
`3d19fa9b94df42e50b36605a2753408a027e0441b72149c0f2d9cef541b1130e`.
`0.8.0` installed but reported `ml_init_failed`; the model uses `MEAN` and the
resolver did not register it. `0.8.1` adds `resolver.AddMean()` and increases
the resolver to 10 ops.

## OTA when the board is back

Connect the board to the authorized LAN, confirm the current version and safe
state, then upload only `firmware.bin`:

```powershell
$py = "$env:USERPROFILE\.platformio\penv\Scripts\python.exe"
& $py -B .\tools\ops\device.py status
& $py -B .\tools\ops\device.py ota .\analysis\platformio\build-20261111T113650019Z\firmware.bin --expect-version 0.8.1-ml-empty-human
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
  "model_version": "hlk-cnn-20261111T035836Z",
  "window": 32,
  "features": 6,
  "classes": 2,
  "window_ready": true,
  "class": "human",
  "confidence": 0.996,
  "latency_ms": 4,
  "inferences": 228,
  "arena_used_bytes": 5248,
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
