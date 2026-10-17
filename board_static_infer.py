import argparse
import json

import cv2
import numpy as np

from labels import STATIC_KIND, make_result
from preprocess import preprocess_frame
from static_numpy_features import extract_static_feature


class NumpyStaticPredictor:
    def __init__(
        self,
        model_path="models/static_numpy_model.npz",
        margin_threshold=0.0,
        unknown_gap_threshold=0.0,
        preprocess_fn=None,
    ):
        data = np.load(model_path, allow_pickle=False)
        self.centroids = data["centroids"].astype(np.float32)
        self.labels = data["labels"].astype(str)
        self.prototypes = (
            data["prototypes"].astype(np.float32)
            if "prototypes" in data.files else None
        )
        self.prototype_label_indices = (
            data["prototype_label_indices"].astype(np.int32)
            if "prototype_label_indices" in data.files else None
        )
        self.feature_dim = int(self.centroids.shape[1])
        self.margin_threshold = float(margin_threshold)
        self.unknown_gap_threshold = float(unknown_gap_threshold)
        self.preprocess_fn = preprocess_frame if preprocess_fn is None else preprocess_fn

    def _score(self, x):
        centroid_scores = self.centroids @ x
        if self.prototypes is None or self.prototype_label_indices is None:
            return centroid_scores

        proto_scores = self.prototypes @ x
        knn_scores = np.full(len(self.labels), -1.0, dtype=np.float32)
        for idx in range(len(self.labels)):
            cls_scores = proto_scores[self.prototype_label_indices == idx]
            if len(cls_scores) == 0:
                continue
            top_k = min(5, len(cls_scores))
            top_scores = np.partition(cls_scores, -top_k)[-top_k:]
            knn_scores[idx] = float(top_scores.mean())
        return 0.65 * centroid_scores + 0.35 * knn_scores

    def predict(self, frame_bgr):
        binary, info = self.preprocess_fn(frame_bgr)
        if binary is None:
            return make_result("unknown", 1.0, STATIC_KIND), info
        if self.feature_dim == 128 * 128:
            x = (binary > 0).astype(np.float32).reshape(-1)
            x = x / (np.linalg.norm(x) + 1e-8)
        else:
            x = extract_static_feature(binary)
        scores = self._score(x)
        order = np.argsort(scores)[::-1]
        best = int(order[0])
        second = int(order[1]) if len(order) > 1 else best
        score = float(scores[best])
        second_score = float(scores[second])
        margin = score - second_score

        raw_label = str(self.labels[best])
        final_label = raw_label

        unknown_score = None
        reject_reason = None
        if "unknown" in self.labels:
            unknown_idx = int(np.where(self.labels == "unknown")[0][0])
            unknown_score = float(scores[unknown_idx])

        if raw_label != "unknown":
            if margin < self.margin_threshold:
                final_label = "unknown"
                reject_reason = "low_margin"
            elif (unknown_score is not None
                  and score - unknown_score < self.unknown_gap_threshold):
                final_label = "unknown"
                reject_reason = "too_close_to_unknown"

        info["raw_label"] = raw_label
        info["raw_score"] = score
        info["second_label"] = str(self.labels[second])
        info["second_score"] = second_score
        info["score_margin"] = float(margin)
        if unknown_score is not None:
            info["unknown_score"] = unknown_score
        info["final_label_changed"] = bool(final_label != raw_label)
        info["reject_reason"] = reject_reason

        # Map cosine similarity from [-1, 1] to a bounded confidence-like value.
        confidence = max(0.0, min(1.0, (score + 1.0) / 2.0))
        return make_result(final_label, confidence, STATIC_KIND), info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--model", default="models/static_numpy_model.npz")
    ap.add_argument("--output", default=None)
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
    ap.add_argument("--backend", default="cpu", choices=("cpu", "pl"))
    ap.add_argument(
        "--overlay",
        default="board/overlays/sign_preprocess_2026_1/sign_preprocess_2026_1.bit",
    )
    ap.add_argument("--dma-name", default="axi_dma_0")
    ap.add_argument("--ip-name", default="image_preprocess_0")
    ap.add_argument("--pl-frame-size", type=int, default=360)
    ap.add_argument(
        "--pl-input-layout",
        default="packed_rgb",
        choices=("packed_rgb", "rgbx32"),
    )
    ap.add_argument("--pl-timeout", type=float, default=3.0)
    args = ap.parse_args()

    frame = cv2.imread(args.input)
    if frame is None:
        raise SystemExit(f"cannot read input image: {args.input}")

    preprocess_fn = None
    if args.backend == "pl":
        from pl_preprocess import PLPreprocessor

        pl = PLPreprocessor(
            overlay_path=args.overlay,
            dma_name=args.dma_name,
            ip_name=args.ip_name,
            frame_size=args.pl_frame_size,
            input_layout=args.pl_input_layout,
            timeout_s=args.pl_timeout,
        )
        preprocess_fn = pl.preprocess_frame

    predictor = NumpyStaticPredictor(
        args.model,
        margin_threshold=args.margin_threshold,
        unknown_gap_threshold=args.unknown_gap_threshold,
        preprocess_fn=preprocess_fn,
    )
    result, info = predictor.predict(frame)
    payload = {"result": result, "preprocess": info}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text)


if __name__ == "__main__":
    main()
