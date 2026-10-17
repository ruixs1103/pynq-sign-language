"""NumPy-only inference for an exported dynamic RandomForest model."""

from pathlib import Path

import numpy as np


class NumpyDynamicForest:
    def __init__(self, model_path):
        path = Path(model_path)
        data = np.load(path, allow_pickle=False)
        self.children_left = data["children_left"].astype(np.int32)
        self.children_right = data["children_right"].astype(np.int32)
        self.features = data["features"].astype(np.int32)
        self.thresholds = data["thresholds"].astype(np.float32)
        self.values = data["values"].astype(np.float32)
        self.roots = data["roots"].astype(np.int32)
        self.classes_ = data["labels"].astype(str)
        self.feature_dim = int(data["feature_dim"][0])

    def _tree_distribution(self, root, x):
        node = int(root)
        while True:
            feature = int(self.features[node])
            if feature < 0:
                value = self.values[node]
                total = float(value.sum())
                if total <= 0.0:
                    return np.zeros(len(self.classes_), dtype=np.float32)
                return value / total

            if float(x[feature]) <= float(self.thresholds[node]):
                node = int(self.children_left[node])
            else:
                node = int(self.children_right[node])

    def predict_proba(self, x_batch):
        x_batch = np.asarray(x_batch, dtype=np.float32)
        if x_batch.ndim == 1:
            x_batch = x_batch[None, :]
        if x_batch.shape[1] != self.feature_dim:
            raise ValueError(
                f"feature dimension mismatch: {x_batch.shape[1]} != "
                f"{self.feature_dim}"
            )
        result = np.zeros(
            (len(x_batch), len(self.classes_)), dtype=np.float32
        )
        for row, x in enumerate(x_batch):
            for root in self.roots:
                result[row] += self._tree_distribution(root, x)
        if len(self.roots):
            result /= float(len(self.roots))
        return result

    def predict(self, x_batch):
        proba = self.predict_proba(x_batch)
        return self.classes_[np.argmax(proba, axis=1)]
