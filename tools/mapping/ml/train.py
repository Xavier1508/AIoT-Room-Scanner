#!/usr/bin/env python3
"""Train a small 1D CNN on HLK windows and export TFLite + C header.

This script is intentionally run on the PC, not on the ESP32. It expects
frames.jsonl files produced by collect.py or the Dataset tab. TensorFlow is
required for training; if it is missing the script prints the install command
and exits without changing anything.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

FEATURES = (
    "hlk_distance_cm",
    "hlk_energy",
    "hlk_target_state",
    "moving_energy",
    "stationary_energy",
    "delta_distance_cm",
)


def read_frames(root: Path):
    rows = []
    for path in sorted(root.rglob("frames.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            frame = json.loads(line)
            last = frame.get("hlk_last_reading") or {}
            rows.append({
                "label": frame.get("label") or path.parent.name,
                "distance": frame.get("hlk_distance_cm"),
                "energy": frame.get("hlk_energy"),
                "target_state": frame.get("hlk_target_state"),
                "moving_energy": last.get("moving_energy"),
                "stationary_energy": last.get("stationary_energy"),
            })
    return rows


def build_windows(rows, window: int, stride: int):
    windows, labels = [], []
    for start in range(0, max(0, len(rows) - window + 1), stride):
        chunk = rows[start:start + window]
        if any(row["label"] != chunk[0]["label"] for row in chunk):
            continue
        previous = None
        sample = []
        for row in chunk:
            distance = float(row["distance"] or 0.0)
            sample.append([
                distance,
                float(row["energy"] or 0.0),
                float(row["target_state"] or 0.0),
                float(row["moving_energy"] or 0.0),
                float(row["stationary_energy"] or 0.0),
                distance - previous if previous is not None else 0.0,
            ])
            previous = distance
        windows.append(sample)
        labels.append(chunk[0]["label"])
    return windows, labels


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="research/mapping/ml")
    parser.add_argument("--output", default="research/mapping/ml/model")
    parser.add_argument("--window", type=int, default=32)
    parser.add_argument("--stride", type=int, default=8)
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch", type=int, default=32)
    args = parser.parse_args()

    try:
        import numpy as np
        import tensorflow as tf
    except ImportError as exc:
        print("TensorFlow/numpy belum terpasang.")
        print("Install di environment PC, misalnya:")
        print("  py -3 -m pip install tensorflow")
        print(f"Detail: {exc}")
        return 2

    root = Path(args.data)
    rows = read_frames(root)
    if len(rows) < args.window:
        print(f"data terlalu sedikit: {len(rows)} frame, butuh minimal {args.window}")
        return 2
    windows, labels = build_windows(rows, args.window, args.stride)
    if not windows:
        print("tidak ada window valid; pastikan label konsisten per sesi")
        return 2
    x = np.asarray(windows, dtype=np.float32)
    classes = sorted(set(labels))
    index = {label: i for i, label in enumerate(classes)}
    y = np.asarray([index[label] for label in labels], dtype=np.int32)
    mean = x.mean(axis=(0, 1), keepdims=True)
    std = x.std(axis=(0, 1), keepdims=True)
    std[std == 0] = 1.0
    x = (x - mean) / std

    model = tf.keras.Sequential([
        tf.keras.layers.Input(shape=(args.window, len(FEATURES))),
        tf.keras.layers.Conv1D(8, 3, activation="relu", padding="same"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Conv1D(16, 3, activation="relu", padding="same"),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(len(classes), activation="softmax"),
    ])
    model.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    split = max(1, int(len(x) * 0.8))
    history = model.fit(x[:split], y[:split], validation_data=(x[split:], y[split:]) if split < len(x) else None,
                        epochs=args.epochs, batch_size=args.batch, verbose=2)

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.keras")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    def representative():
        for sample in x[:min(200, len(x))]:
            yield [sample[None, ...].astype(np.float32)]

    converter.representative_dataset = representative
    tflite = converter.convert()
    (out / "model.tflite").write_bytes(tflite)
    (out / "labels.json").write_text(json.dumps(classes, indent=2) + "\n", encoding="utf-8")
    (out / "normalization.json").write_text(json.dumps({
        "features": FEATURES,
        "window": args.window,
        "mean": mean.reshape(-1).tolist(),
        "std": std.reshape(-1).tolist(),
    }, indent=2) + "\n", encoding="utf-8")
    metrics = {
        "frames": len(rows),
        "windows": len(windows),
        "classes": classes,
        "final_accuracy": float(history.history.get("accuracy", [0])[-1]),
        "final_val_accuracy": float(history.history.get("val_accuracy", [0])[-1]) if history.history.get("val_accuracy") else None,
        "tflite_bytes": len(tflite),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    header = ["// Generated by tools/mapping/ml/train.py", "#pragma once", "#include <stdint.h>", ""]
    header.append("alignas(16) const unsigned char g_model[] = {")
    for offset in range(0, len(tflite), 16):
        header.append("  " + ",".join(str(byte) for byte in tflite[offset:offset + 16]) + ",")
    header.append("};")
    header.append(f"const unsigned int g_model_len = {len(tflite)};")
    (out / "model_data.h").write_text("\n".join(header) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
