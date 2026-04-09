#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from magnet_knights_logic import LEARNED_FEATURE_NAMES, LEARNED_FEATURE_SCHEMA_VERSION


def sigmoid(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1.0 / (1.0 + z)
    z = math.exp(value)
    return z / (1.0 + z)


def log_loss(probability: float, target: float) -> float:
    clamped = min(1.0 - 1e-12, max(1e-12, probability))
    return -(target * math.log(clamped) + (1.0 - target) * math.log(1.0 - clamped))


def expand_inputs(patterns: Sequence[str]) -> List[Path]:
    paths: List[Path] = []
    for pattern in patterns:
        candidate = Path(pattern)
        if any(char in pattern for char in "*?[]"):
            paths.extend(sorted(Path().glob(pattern)))
        else:
            paths.append(candidate)
    unique = []
    seen = set()
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    if not unique:
        raise ValueError("no input CSV files matched")
    return unique


def load_examples(paths: Sequence[Path], target_column: str) -> List[Dict[str, object]]:
    examples: List[Dict[str, object]] = []
    feature_columns = [f"feat_{name}" for name in LEARNED_FEATURE_NAMES]
    for path in paths:
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise ValueError(f"{path} does not have a header row")
            missing_columns = [column for column in ["learned_schema_version", *feature_columns, target_column, "game_id"] if column not in reader.fieldnames]
            if missing_columns:
                raise ValueError(f"{path} is missing required columns: {', '.join(missing_columns)}")
            for row in reader:
                if row["learned_schema_version"] != LEARNED_FEATURE_SCHEMA_VERSION:
                    raise ValueError(f"{path} has schema {row['learned_schema_version']}, expected {LEARNED_FEATURE_SCHEMA_VERSION}")
                features = [float(row[f"feat_{name}"]) for name in LEARNED_FEATURE_NAMES]
                examples.append(
                    {
                        "game_key": f"{path.resolve()}::{row['game_id']}",
                        "features": features,
                        "target": float(row[target_column]),
                    }
                )
    if not examples:
        raise ValueError("no training rows loaded")
    return examples


def split_examples(examples: Sequence[Dict[str, object]], validation_fraction: float, seed: int) -> Tuple[List[Dict[str, object]], List[Dict[str, object]]]:
    train: List[Dict[str, object]] = []
    validation: List[Dict[str, object]] = []
    for example in examples:
        key = str(example["game_key"])
        digest = hashlib.sha256(f"{seed}:{key}".encode("utf-8")).hexdigest()
        bucket = int(digest[:8], 16) / 0xFFFFFFFF
        if bucket < validation_fraction:
            validation.append(dict(example))
        else:
            train.append(dict(example))
    if not train or not validation:
        raise ValueError("split produced an empty train or validation set; adjust validation fraction or inputs")
    return train, validation


def compute_normalization(train_examples: Sequence[Dict[str, object]]) -> Tuple[List[float], List[float]]:
    means: List[float] = []
    scales: List[float] = []
    count = len(train_examples)
    for index, name in enumerate(LEARNED_FEATURE_NAMES):
        values = [float(example["features"][index]) for example in train_examples]
        if name == "bias":
            means.append(0.0)
            scales.append(1.0)
            continue
        mean = sum(values) / count
        variance = sum((value - mean) ** 2 for value in values) / count
        scale = math.sqrt(variance)
        if scale < 1e-9:
            scale = 1.0
        means.append(mean)
        scales.append(scale)
    return means, scales


def normalize_features(features: Sequence[float], means: Sequence[float], scales: Sequence[float]) -> List[float]:
    normalized: List[float] = []
    for index, value in enumerate(features):
        scale = scales[index] if abs(scales[index]) > 1e-9 else 1.0
        normalized.append((float(value) - means[index]) / scale)
    return normalized


def fit_logistic_model(
    train_examples: Sequence[Dict[str, object]],
    means: Sequence[float],
    scales: Sequence[float],
    epochs: int,
    learning_rate: float,
    l2: float,
    decay: float,
) -> Tuple[float, List[float]]:
    width = len(LEARNED_FEATURE_NAMES)
    bias = 0.0
    weights = [0.0] * width
    normalized_examples = [
        (normalize_features(example["features"], means, scales), float(example["target"]))
        for example in train_examples
    ]

    for epoch in range(epochs):
        lr = learning_rate / (1.0 + decay * epoch)
        grad_bias = 0.0
        grad_weights = [0.0] * width
        count = len(normalized_examples)

        for features, target in normalized_examples:
            margin = bias
            for index, value in enumerate(features):
                margin += weights[index] * value
            probability = sigmoid(margin)
            error = probability - target
            grad_bias += error
            for index, value in enumerate(features):
                grad_weights[index] += error * value

        bias -= lr * (grad_bias / count)
        for index in range(width):
            penalty = l2 * weights[index]
            weights[index] -= lr * ((grad_weights[index] / count) + penalty)

    return bias, weights


def evaluate_dataset(
    examples: Sequence[Dict[str, object]],
    means: Sequence[float],
    scales: Sequence[float],
    bias: float,
    weights: Sequence[float],
) -> Dict[str, object]:
    losses: List[float] = []
    probabilities: List[float] = []
    targets: List[float] = []
    for example in examples:
        features = normalize_features(example["features"], means, scales)
        margin = bias + sum(weight * value for weight, value in zip(weights, features))
        probability = sigmoid(margin)
        target = float(example["target"])
        probabilities.append(probability)
        targets.append(target)
        losses.append(log_loss(probability, target))
    return {
        "rows": len(examples),
        "log_loss": sum(losses) / len(losses),
        "mean_probability": sum(probabilities) / len(probabilities),
        "mean_target": sum(targets) / len(targets),
        "probabilities": probabilities,
        "targets": targets,
    }


def calibration_lines(probabilities: Sequence[float], targets: Sequence[float], bins: int = 5) -> List[str]:
    lines: List[str] = []
    for index in range(bins):
        lower = index / bins
        upper = (index + 1) / bins
        bucket = [
            (probability, target)
            for probability, target in zip(probabilities, targets)
            if lower <= probability < upper or (index == bins - 1 and probability == upper)
        ]
        if not bucket:
            lines.append(f"- {lower:.1f}-{upper:.1f}: empty")
            continue
        mean_probability = sum(probability for probability, _target in bucket) / len(bucket)
        mean_target = sum(target for _probability, target in bucket) / len(bucket)
        lines.append(f"- {lower:.1f}-{upper:.1f}: rows={len(bucket)} pred={mean_probability:.3f} actual={mean_target:.3f}")
    return lines


def model_dict(
    bias: float,
    weights: Sequence[float],
    means: Sequence[float],
    scales: Sequence[float],
    train_rows: int,
    validation_rows: int,
    metrics: Dict[str, object],
    target_column: str,
) -> Dict[str, object]:
    return {
        "schema_version": LEARNED_FEATURE_SCHEMA_VERSION,
        "feature_names": list(LEARNED_FEATURE_NAMES),
        "bias": bias,
        "weights": list(weights),
        "means": list(means),
        "scales": list(scales),
        "training_rows": train_rows,
        "validation_rows": validation_rows,
        "metadata": {
            "generated_by": "magnet_knights_train.py",
            "target_column": target_column,
            "validation_log_loss": metrics["log_loss"],
            "validation_mean_probability": metrics["mean_probability"],
            "validation_mean_target": metrics["mean_target"],
        },
    }


def write_json_artifact(model: Dict[str, object], path: Path) -> None:
    path.write_text(json.dumps(model, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def write_python_artifact(model: Dict[str, object], path: Path) -> None:
    path.write_text(f"LEARNED_MODEL = {repr(model)}\n", encoding="utf-8")


def write_js_artifact(model: Dict[str, object], path: Path) -> None:
    body = json.dumps(model, indent=2, sort_keys=False)
    path.write_text(f"export const LEARNED_MODEL = {body};\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train a lightweight learned value model for Magnet Knights.")
    parser.add_argument("--input-csv", nargs="+", required=True, help="One or more self-play CSV files or glob patterns.")
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--target-column", default="target_training")
    parser.add_argument("--epochs", type=int, default=800)
    parser.add_argument("--learning-rate", type=float, default=0.08)
    parser.add_argument("--l2", type=float, default=0.0005)
    parser.add_argument("--decay", type=float, default=0.002)
    parser.add_argument("--output-json", type=Path, default=Path("magnet_knights_learned_model.json"))
    parser.add_argument("--output-python", type=Path, default=Path("magnet_knights_learned_model.py"))
    parser.add_argument("--output-js", type=Path, default=Path("magnet_knights_learned_model.js"))
    args = parser.parse_args()

    inputs = expand_inputs(args.input_csv)
    examples = load_examples(inputs, args.target_column)
    train_examples, validation_examples = split_examples(examples, args.validation_fraction, args.seed)
    means, scales = compute_normalization(train_examples)
    bias, weights = fit_logistic_model(
        train_examples,
        means,
        scales,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        l2=args.l2,
        decay=args.decay,
    )

    metrics = evaluate_dataset(validation_examples, means, scales, bias, weights)
    model = model_dict(
        bias=bias,
        weights=weights,
        means=means,
        scales=scales,
        train_rows=len(train_examples),
        validation_rows=len(validation_examples),
        metrics=metrics,
        target_column=args.target_column,
    )
    write_json_artifact(model, args.output_json)
    write_python_artifact(model, args.output_python)
    write_js_artifact(model, args.output_js)

    print(f"Loaded rows: {len(examples)} from {len(inputs)} file(s)")
    print(f"Train rows: {len(train_examples)}")
    print(f"Validation rows: {len(validation_examples)}")
    print(f"Validation log loss: {metrics['log_loss']:.4f}")
    print(f"Validation mean probability: {metrics['mean_probability']:.4f}")
    print(f"Validation mean target: {metrics['mean_target']:.4f}")
    print(f"Target column: {args.target_column}")
    print("Calibration:")
    for line in calibration_lines(metrics["probabilities"], metrics["targets"]):
        print(line)
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_python}")
    print(f"Wrote {args.output_js}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
