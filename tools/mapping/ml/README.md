# TinyML dataset and training

This folder prepares the HLK-LD2410C time-series dataset and a small 1D CNN for
the ESP32-S3. Training runs on the PC; the ESP32 only runs inference after the
model is exported.

## 1. Record

Use the PC dashboard **Dataset** tab, or the CLI:

```powershell
py -3 tools/mapping/ml/collect.py --label empty --duration 60
py -3 tools/mapping/ml/collect.py --label human --duration 60
py -3 tools/mapping/ml/collect.py --label non-human --duration 60
```

Record after the scan is finished and the arm is parked. One session = one
label. For activity classes, record separate sessions:

```powershell
py -3 tools/mapping/ml/collect.py --label walking --duration 60
py -3 tools/mapping/ml/collect.py --label sitting --duration 60
py -3 tools/mapping/ml/collect.py --label standing --duration 60
py -3 tools/mapping/ml/collect.py --label lying --duration 60
```

Recommended first target: **empty / human / non-human**. Add activity classes
only after the first model is reliable.

## 2. Train

```powershell
py -3 tools/mapping/ml/train.py --data research/mapping/ml --window 32 --stride 8 --epochs 30
```

TensorFlow is required on the PC. The script writes:

```text
research/mapping/ml/model/
  model.keras
  model.tflite
  model_data.h
  labels.json
  normalization.json
  metrics.json
```

The 1D CNN uses a 32-frame window (~6.4 s at 5 Hz) with features: distance,
energy, target state, moving energy, stationary energy, delta distance.

## 3. Integrate on the ESP32-S3

The intended on-device path is TensorFlow Lite Micro:

1. Add the TFLite Micro library/component for ESP32-S3.
2. Include `model_data.h` and allocate a tensor arena (target 50–80 KB).
3. Keep a ring buffer of the last 32 HLK frames.
4. Run inference only when the arm is parked and the scan is not active.
5. Expose `ml.class`, `ml.confidence` and `ml.model_version` in `/api/status`.
6. Keep the rule-based presence/buzzer path as a fallback if confidence is low.

Memory budget on the current board: ~230 KB free heap, 16 MB flash, 837 KB app
in a 6.5 MB OTA slot. A quantized int8 model under 50 KB plus an 80 KB arena is
realistic without PSRAM. PSRAM remains off unless the model grows.

## 4. Power and timing

- TinyML inference must **not** run during the scan; the servo/stepper power
  budget is the critical path.
- Run inference after the scan, when the arm is parked and the servo detached.
- Use a 5 Hz inference duty cycle (one window every 200 ms with overlap).
- The buzzer remains driven by the rule-based HLK alert until the model is
  validated; do not let an untrained model drive the buzzer.

## 5. Honest limits

- One HLK-LD2410C gives coarse presence/motion features, not camera-level
  activity recognition. Human/non-human is the realistic first target.
- The ToF stalls during servo motion on the current shared rail, so the scan
  uses HC points. HLK is used for presence only, not point-cloud geometry.
- No accuracy is claimed until the dataset is collected and a held-out session
  is evaluated.
