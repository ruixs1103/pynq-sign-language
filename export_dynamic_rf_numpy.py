"""Export a scikit-learn RandomForest dynamic model to a NumPy-only format.

Run this on the PC where scikit-learn/joblib are installed:
    python export_dynamic_rf_numpy.py
"""

import argparse
from pathlib import Path

import joblib
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="models/dynamic_model.joblib")
    ap.add_argument("--output", default="models/dynamic_model_numpy.npz")
    args = ap.parse_args()

    model = joblib.load(args.input)
    if not hasattr(model, "estimators_") or not hasattr(model, "classes_"):
        raise SystemExit("input model is not a scikit-learn RandomForestClassifier")

    children_left = []
    children_right = []
    features = []
    thresholds = []
    values = []
    roots = []
    offset = 0

    for estimator in model.estimators_:
        tree = estimator.tree_
        roots.append(offset)
        children_left.append(tree.children_left.astype(np.int32) + offset)
        children_right.append(tree.children_right.astype(np.int32) + offset)
        features.append(tree.feature.astype(np.int32))
        thresholds.append(tree.threshold.astype(np.float32))
        values.append(tree.value[:, 0, :].astype(np.float32))
        offset += tree.node_count

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        children_left=np.concatenate(children_left),
        children_right=np.concatenate(children_right),
        features=np.concatenate(features),
        thresholds=np.concatenate(thresholds),
        values=np.concatenate(values, axis=0),
        roots=np.asarray(roots, dtype=np.int32),
        labels=np.asarray([str(c) for c in model.classes_]),
        feature_dim=np.asarray([int(model.n_features_in_)], dtype=np.int32),
        tree_count=np.asarray([len(model.estimators_)], dtype=np.int32),
        format_version=np.asarray(["dynamic_rf_numpy_v1"]),
    )

    print(f"exported: {output}")
    print(f"trees: {len(model.estimators_)}")
    print(f"classes: {[str(c) for c in model.classes_]}")
    print(f"features: {model.n_features_in_}")
    print(f"nodes: {offset}")


if __name__ == "__main__":
    main()
