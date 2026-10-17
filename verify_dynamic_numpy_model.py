"""Compare the PC joblib model with the board-compatible NumPy model."""

import argparse

import joblib
import numpy as np

from dynamic_numpy_model import NumpyDynamicForest
from train_dynamic_model import load_dataset


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dataset/dynamic_eval_v1")
    ap.add_argument("--joblib-model", default="models/dynamic_model.joblib")
    ap.add_argument("--numpy-model", default="models/dynamic_model_numpy.npz")
    ap.add_argument("--seq-len", type=int, default=16)
    args = ap.parse_args()

    x, y, _ = load_dataset(args.input, args.seq_len)
    if not x:
        raise SystemExit(f"no videos found: {args.input}")
    X = np.stack(x)

    sklearn_model = joblib.load(args.joblib_model)
    numpy_model = NumpyDynamicForest(args.numpy_model)
    sklearn_pred = sklearn_model.predict(X).astype(str)
    numpy_pred = numpy_model.predict(X).astype(str)
    same = sklearn_pred == numpy_pred
    print(f"samples: {len(y)}")
    print(f"same predictions: {int(same.sum())}/{len(same)}")
    if not np.all(same):
        for index in np.flatnonzero(~same)[:20]:
            print(
                f"[diff] index={index} sklearn={sklearn_pred[index]} "
                f"numpy={numpy_pred[index]} expected={y[index]}"
            )
        raise SystemExit("NumPy model does not match joblib model")
    print("verification passed")


if __name__ == "__main__":
    main()
