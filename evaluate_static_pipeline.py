"""Offline regression checks for the complete static-image pipeline.

This script deliberately evaluates the same binary inputs used by the model.
It also inspects any downloaded board report so camera/PL failures are
separated from classifier failures.
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from labels import STATIC_LABELS
from static_numpy_features import extract_static_feature
from board_static_infer import NumpyStaticPredictor


def _predict_binary(predictor, path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    binary = (image > 0).astype(np.uint8) * 255

    def existing(_frame):
        return binary, {
            "hand_found": bool(np.count_nonzero(binary)),
            "area": int(np.count_nonzero(binary)),
            "frame_w": int(binary.shape[1]),
            "frame_h": int(binary.shape[0]),
        }

    old = predictor.preprocess_fn
    predictor.preprocess_fn = existing
    try:
        result, info = predictor.predict(binary)
    finally:
        predictor.preprocess_fn = old
    return result, info


def evaluate_dataset(root, model, margin_threshold, unknown_gap_threshold):
    predictor = NumpyStaticPredictor(
        model,
        margin_threshold=margin_threshold,
        unknown_gap_threshold=unknown_gap_threshold,
    )
    rows = []
    for label in STATIC_LABELS:
        label_dir = Path(root) / label
        if not label_dir.is_dir():
            continue
        for path in sorted(label_dir.glob("*.png")):
            predicted = _predict_binary(predictor, path)
            if predicted is None:
                continue
            result, info = predicted
            rows.append({
                "expected": label,
                "predicted": result["label"],
                "raw_label": info.get("raw_label"),
                "margin": info.get("score_margin"),
                "path": str(path),
            })

    labels = list(STATIC_LABELS)
    matrix = [[0 for _ in labels] for _ in labels]
    label_index = {label: i for i, label in enumerate(labels)}
    for row in rows:
        if row["expected"] in label_index and row["predicted"] in label_index:
            matrix[label_index[row["expected"]]][label_index[row["predicted"]]] += 1
    correct = sum(matrix[i][i] for i in range(len(labels)))
    accuracy = correct / len(rows) if rows else 0.0
    raw_correct = sum(row["expected"] == row["raw_label"] for row in rows)
    return {
        "root": str(root),
        "samples": len(rows),
        "accuracy": accuracy,
        "raw_accuracy": raw_correct / len(rows) if rows else 0.0,
        "confusion_matrix": matrix,
        "labels": labels,
        "prediction_counts": dict(Counter(row["predicted"] for row in rows)),
        "rows": rows,
    }


def inspect_board_report(root, model, margin_threshold, unknown_gap_threshold):
    predictor = NumpyStaticPredictor(
        model,
        margin_threshold=margin_threshold,
        unknown_gap_threshold=unknown_gap_threshold,
    )
    rows = []
    for binary_path in sorted(Path(root).glob("**/binary_128.png")):
        predicted = _predict_binary(predictor, binary_path)
        if predicted is None:
            continue
        result, info = predicted
        summary_path = binary_path.parent / "summary.json"
        summary = {}
        if summary_path.exists():
            try:
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        rows.append({
            "binary": str(binary_path),
            "input": summary.get("input"),
            "result": result,
            "raw_label": info.get("raw_label"),
            "raw_score": info.get("raw_score"),
            "second_label": info.get("second_label"),
            "second_score": info.get("second_score"),
            "score_margin": info.get("score_margin"),
            "preprocess": summary.get("preprocess", {}),
        })
    return {
        "root": str(root),
        "samples": len(rows),
        "prediction_counts": dict(Counter(row["result"]["label"] for row in rows)),
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default="dataset/processed_static_aug_v1")
    ap.add_argument("--board-report", default=None)
    ap.add_argument("--model", default="models/static_numpy_model.npz")
    ap.add_argument("--output", default="report/static_pipeline_eval.json")
    ap.add_argument(
        "--margin-threshold",
        type=float,
        default=0.0,
        help="低于此类别间分数差时拒识为 unknown",
    )
    ap.add_argument(
        "--unknown-gap-threshold",
        type=float,
        default=0.0,
        help="最佳类别与 unknown 分数差低于此值时拒识",
    )
    args = ap.parse_args()

    payload = {
        "dataset": evaluate_dataset(
            args.dataset, args.model, args.margin_threshold,
            args.unknown_gap_threshold,
        ),
    }
    if args.board_report:
        payload["board_report"] = inspect_board_report(
            args.board_report, args.model, args.margin_threshold,
            args.unknown_gap_threshold,
        )
    payload["dataset"].pop("rows", None)
    if "board_report" in payload:
        payload["board_report"]["rows"] = payload["board_report"]["rows"]
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
