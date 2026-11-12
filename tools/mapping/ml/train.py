#!/usr/bin/env python3
"""Train the 1D CNN on HLK windows and export TFLite plus C headers."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
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
                "session": path.parent.name,
                "label": frame.get("label") or path.parent.name,
                "distance": frame.get("hlk_distance_cm"),
                "energy": frame.get("hlk_energy"),
                "target_state": frame.get("hlk_target_state"),
                "moving_energy": last.get("moving_energy"),
                "stationary_energy": last.get("stationary_energy"),
            })
    return rows


def build_windows(rows, window: int, stride: int):
    windows, labels, sessions = [], [], []
    for start in range(0, max(0, len(rows) - window + 1), stride):
        chunk = rows[start:start + window]
        if any(row["label"] != chunk[0]["label"]
               or row["session"] != chunk[0]["session"] for row in chunk):
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
        sessions.append(chunk[0]["session"])
    return windows, labels, sessions


def _normalize(train_x, x):
    mean = train_x.mean(axis=(0, 1), keepdims=True)
    std = train_x.std(axis=(0, 1), keepdims=True)
    std[std == 0] = 1.0
    return (x - mean) / std, mean, std


def _build_model(tf, window: int, classes: int):
    return tf.keras.Sequential([
        tf.keras.layers.Input(shape=(window, len(FEATURES))),
        tf.keras.layers.Conv1D(16, 3, padding="same", activation="relu"),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Conv1D(32, 3, padding="same", activation="relu"),
        tf.keras.layers.BatchNormalization(),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(32, activation="relu"),
        tf.keras.layers.Dropout(0.2),
        tf.keras.layers.Dense(classes, activation="softmax"),
    ])


def _blocked_cv(tf, np, x, y, sessions, classes, window, folds, epochs, batch):
    block = np.zeros(len(y), dtype=int)
    for session in sorted(set(sessions)):
        indices = np.where(sessions == session)[0]
        for order, index in enumerate(indices):
            block[index] = min(folds - 1, int(order * folds / len(indices)))
    metrics = []
    for fold in range(folds):
        val = block == fold
        train = ~val
        if not train.any() or not val.any():
            continue
        x_train = x[train]
        x_val, _, _ = _normalize(x_train, x[val])
        x_train, _, _ = _normalize(x_train, x_train)
        y_train = np.asarray([classes.index(value) for value in y[train]])
        y_val = np.asarray([classes.index(value) for value in y[val]])
        model = _build_model(tf, window, len(classes))
        model.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                      loss="sparse_categorical_crossentropy",
                      metrics=["accuracy"])
        weights = {
            index: len(y_train) / (len(classes) * max(1, int((y_train == index).sum())))
            for index in range(len(classes))
        }
        model.fit(x_train, y_train, epochs=epochs, batch_size=batch,
                  verbose=0, class_weight=weights,
                  callbacks=[tf.keras.callbacks.EarlyStopping(
                      monitor="loss", patience=8, restore_best_weights=True)])
        prediction = model.predict(x_val, verbose=0).argmax(axis=1)
        accuracy = float((prediction == y_val).mean())
        metrics.append({
            "fold": fold,
            "val_windows": int(len(y_val)),
            "accuracy": accuracy,
            "confusion": _confusion(tf, y_val, prediction, len(classes)),
        })
        print(f"fold {fold}: val={len(y_val)} accuracy={accuracy:.4f}")
    return metrics


def _confusion(tf, truth, prediction, classes):
    matrix = tf.math.confusion_matrix(
        truth, prediction, num_classes=classes).numpy().tolist()
    return matrix


def _tflite_predict(tf, np, model_bytes, x, labels):
    interpreter = tf.lite.Interpreter(model_content=model_bytes)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    scale, zero_point = input_detail["quantization"]
    out_scale, out_zero = output_detail["quantization"]
    correct = 0
    for sample, truth in zip(x, labels):
        quantized = np.clip(np.round(sample / scale + zero_point), -128, 127).astype(np.int8)
        interpreter.set_tensor(input_detail["index"], quantized[None, ...])
        interpreter.invoke()
        output = interpreter.get_tensor(output_detail["index"])[0]
        if out_scale:
            output = (output.astype(np.float32) - out_zero) * out_scale
        if int(np.argmax(output)) == int(truth):
            correct += 1
    return correct / max(1, len(x)), {
        "input_scale": float(scale),
        "input_zero_point": int(zero_point),
        "output_scale": float(out_scale),
        "output_zero_point": int(out_zero),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default="research/mapping/ml")
    parser.add_argument("--output", default="research/mapping/ml/model")
    parser.add_argument("--window", type=int, default=32)
    parser.add_argument("--stride", type=int, default=4)
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--batch", type=int, default=32)
    parser.add_argument("--cv-blocks", type=int, default=5)
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
    windows, labels, sessions = build_windows(rows, args.window, args.stride)
    if not windows:
        print("tidak ada window valid; pastikan label konsisten per sesi")
        return 2
    x = np.asarray(windows, dtype=np.float32)
    classes = sorted(set(labels))
    print(f"frames={len(rows)} windows={len(windows)} classes={classes}")
    cv = _blocked_cv(tf, np, x, np.asarray(labels), np.asarray(sessions),
                     classes, args.window, args.cv_blocks, args.epochs, args.batch)
    cv_accuracies = [item["accuracy"] for item in cv]
    cv_mean = float(np.mean(cv_accuracies)) if cv_accuracies else None
    cv_std = float(np.std(cv_accuracies)) if cv_accuracies else None

    x_norm, mean, std = _normalize(x, x)
    y = np.asarray([classes.index(value) for value in labels], dtype=np.int32)
    weights = {
        index: len(y) / (len(classes) * max(1, int((y == index).sum())))
        for index in range(len(classes))
    }
    model = _build_model(tf, args.window, len(classes))
    model.compile(optimizer=tf.keras.optimizers.Adam(1e-3),
                  loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    history = model.fit(
        x_norm, y, epochs=args.epochs, batch_size=args.batch, verbose=2,
        class_weight=weights,
        callbacks=[tf.keras.callbacks.EarlyStopping(
            monitor="loss", patience=8, restore_best_weights=True)])

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.keras")
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = tf.int8
    converter.inference_output_type = tf.int8

    def representative():
        for sample in x_norm[:min(300, len(x_norm))]:
            yield [sample[None, ...].astype(np.float32)]

    converter.representative_dataset = representative
    tflite = converter.convert()
    (out / "model.tflite").write_bytes(tflite)
    (out / "labels.json").write_text(json.dumps(classes, indent=2) + "\n",
                                     encoding="utf-8")
    (out / "normalization.json").write_text(json.dumps({
        "features": list(FEATURES),
        "window": args.window,
        "mean": mean.reshape(-1).tolist(),
        "std": std.reshape(-1).tolist(),
    }, indent=2) + "\n", encoding="utf-8")
    tflite_accuracy, quantization = _tflite_predict(
        tf, np, tflite, x_norm, y)
    version = "hlk-cnn-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_accuracy = float(history.history.get("accuracy", [0])[-1])
    metrics = {
        "model_version": version,
        "features": list(FEATURES),
        "window": args.window,
        "stride": args.stride,
        "frames": len(rows),
        "windows": len(windows),
        "classes": classes,
        "sessions": sorted(set(sessions)),
        "cv_blocks": args.cv_blocks,
        "cv_folds": cv,
        "cv_accuracy_mean": cv_mean,
        "cv_accuracy_std": cv_std,
        "final_train_accuracy": final_accuracy,
        "tflite_train_accuracy": tflite_accuracy,
        "tflite_bytes": len(tflite),
        "quantization": quantization,
        "note": ("cv_accuracy_* is contiguous time-block validation within each "
                 "session; tflite_train_accuracy is a conversion sanity check, not "
                 "a generalization score."),
    }
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n",
                                      encoding="utf-8")
    header = ["// Generated by tools/mapping/ml/train.py", "#pragma once",
              "#include <stdint.h>", ""]
    header.append("alignas(16) const unsigned char g_model[] = {")
    for offset in range(0, len(tflite), 16):
        header.append("  " + ",".join(str(byte) for byte in tflite[offset:offset + 16]) + ",")
    header.append("};")
    header.append(f"const unsigned int g_model_len = {len(tflite)};")
    (out / "model_data.h").write_text("\n".join(header) + "\n", encoding="utf-8")
    metadata = ["// Generated by tools/mapping/ml/train.py", "#pragma once", ""]
    metadata.append(f'#define ML_MODEL_VERSION "{version}"')
    metadata.append(f"#define ML_WINDOW {args.window}")
    metadata.append(f"#define ML_FEATURES {len(FEATURES)}")
    metadata.append(f"#define ML_CLASSES {len(classes)}")
    metadata.append("static const char* const ML_LABELS[] = {" +
                    ", ".join(json.dumps(value) for value in classes) + "};")
    metadata.append("static const float ML_MEAN[] = {" +
                    ", ".join(f"{value:.8f}f" for value in mean.reshape(-1)) + "};")
    metadata.append("static const float ML_STD[] = {" +
                    ", ".join(f"{value:.8f}f" for value in std.reshape(-1)) + "};")
    (out / "model_metadata.h").write_text("\n".join(metadata) + "\n",
                                          encoding="utf-8")
    print(json.dumps(metrics, indent=2))
    print(f"output: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
