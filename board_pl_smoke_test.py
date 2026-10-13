import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from board_static_infer import NumpyStaticPredictor
from pl_preprocess import PLPreprocessor
from preprocess import preprocess_frame


def read_frame(input_path, camera):
    if input_path:
        frame = cv2.imread(input_path)
        if frame is None:
            raise SystemExit(f"cannot read input image: {input_path}")
        return frame

    cap = cv2.VideoCapture(camera, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise SystemExit(f"camera read failed: {camera}")
    return frame


def mask_stats(mask):
    mask = np.asarray(mask)
    nonzero = int(np.count_nonzero(mask))
    total = int(mask.size)
    return {
        "shape": list(mask.shape),
        "dtype": str(mask.dtype),
        "min": int(mask.min()) if total else 0,
        "max": int(mask.max()) if total else 0,
        "mean": float(mask.mean()) if total else 0.0,
        "nonzero": nonzero,
        "nonzero_ratio": float(nonzero / total) if total else 0.0,
        "unique_values_sample": [int(v) for v in np.unique(mask)[:16]],
    }


def binary_difference(a, b):
    if a is None or b is None:
        return None
    a = (np.asarray(a) > 0).astype(np.uint8)
    b = (np.asarray(b) > 0).astype(np.uint8)
    diff = np.abs(a.astype(np.int16) - b.astype(np.int16))
    return {
        "different_pixels": int(diff.sum()),
        "different_ratio": float(diff.mean()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--camera", default="/dev/video0")
    ap.add_argument("--model", default="models/static_numpy_model.npz")
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
    ap.add_argument("--out-dir", default="report/pl_smoke_test")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    frame = read_frame(args.input, args.camera)
    cv2.imwrite(str(out_dir / "input_frame.jpg"), frame)

    cpu_binary, cpu_info = preprocess_frame(frame)
    if cpu_binary is not None:
        cv2.imwrite(str(out_dir / "cpu_binary_128.png"), cpu_binary)

    pl = PLPreprocessor(
        overlay_path=args.overlay,
        dma_name=args.dma_name,
        ip_name=args.ip_name,
        frame_size=args.pl_frame_size,
        input_layout=args.pl_input_layout,
        timeout_s=args.pl_timeout,
    )
    t0 = time.time()
    pl_mask = pl.run_mask(frame)
    pl_elapsed = time.time() - t0
    cv2.imwrite(str(out_dir / "pl_mask.png"), pl_mask)

    pl_binary, pl_info = pl.preprocess_frame(frame)
    if pl_binary is not None:
        cv2.imwrite(str(out_dir / "pl_binary_128.png"), pl_binary)

    cpu_predictor = NumpyStaticPredictor(args.model)
    cpu_result, cpu_pred_info = cpu_predictor.predict(frame)

    pl_predictor = NumpyStaticPredictor(args.model, preprocess_fn=pl.preprocess_frame)
    pl_result, pl_pred_info = pl_predictor.predict(frame)

    payload = {
        "input": args.input or args.camera,
        "overlay": args.overlay,
        "pl": pl.diagnostics(),
        "pl_elapsed_s": pl_elapsed,
        "mask_stats": mask_stats(pl_mask),
        "cpu_preprocess": cpu_info,
        "pl_preprocess": pl_info,
        "cpu_pl_binary_diff": binary_difference(cpu_binary, pl_binary),
        "cpu_result": cpu_result,
        "cpu_predict_info": cpu_pred_info,
        "pl_result": pl_result,
        "pl_predict_info": pl_pred_info,
        "artifacts": {
            "input_frame": str(out_dir / "input_frame.jpg"),
            "cpu_binary": str(out_dir / "cpu_binary_128.png"),
            "pl_mask": str(out_dir / "pl_mask.png"),
            "pl_binary": str(out_dir / "pl_binary_128.png"),
        },
    }

    text = json.dumps(payload, ensure_ascii=False, indent=2)
    (out_dir / "summary.json").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
