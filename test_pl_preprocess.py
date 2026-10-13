import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from pl_preprocess import PLPreprocessor
from preprocess import preprocess_mask


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None)
    ap.add_argument("--camera", default="/dev/video0")
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
    ap.add_argument("--mask-out", default="report/pl_mask.png")
    ap.add_argument("--binary-out", default="report/pl_binary_128.png")
    ap.add_argument("--json-out", default="report/pl_preprocess_test.json")
    args = ap.parse_args()

    frame = read_frame(args.input, args.camera)
    pl = PLPreprocessor(
        overlay_path=args.overlay,
        dma_name=args.dma_name,
        ip_name=args.ip_name,
        frame_size=args.pl_frame_size,
        input_layout=args.pl_input_layout,
        timeout_s=args.pl_timeout,
    )

    mask = pl.run_mask(frame)
    binary, info = preprocess_mask(mask)
    info["backend"] = "pl"
    info["pl_frame_size"] = args.pl_frame_size
    info["pl_input_layout"] = args.pl_input_layout

    nonzero = int(np.count_nonzero(mask))
    total = int(mask.size)
    mask_stats = {
        "shape": list(mask.shape),
        "dtype": str(mask.dtype),
        "min": int(mask.min()),
        "max": int(mask.max()),
        "mean": float(mask.mean()),
        "nonzero": nonzero,
        "nonzero_ratio": float(nonzero / total) if total else 0.0,
        "unique_values_sample": [int(v) for v in np.unique(mask)[:16]],
    }

    mask_out = Path(args.mask_out)
    binary_out = Path(args.binary_out)
    json_out = Path(args.json_out)
    mask_out.parent.mkdir(parents=True, exist_ok=True)
    binary_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.parent.mkdir(parents=True, exist_ok=True)

    cv2.imwrite(str(mask_out), mask)
    if binary is not None:
        cv2.imwrite(str(binary_out), binary)

    payload = {
        "input": args.input or args.camera,
        "mask_out": str(mask_out),
        "binary_out": str(binary_out) if binary is not None else None,
        "pl": pl.diagnostics(),
        "mask_stats": mask_stats,
        "preprocess": info,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    json_out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
