"""Jupyter-friendly interactive static gesture test.

Run inside a Jupyter cell with:
    %run board_static_interactive.py --backend pl --camera /dev/video0

Each shot:
    camera preview/countdown -> capture -> PL preprocessing -> PS normalization
    -> NumPy static inference -> save/display input, mask and normalized binary.
"""

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from board_static_infer import NumpyStaticPredictor
from preprocess import (
    correct_mask_polarity,
    preprocess_frame,
    preprocess_mask,
)


def show_frame(frame_bgr, title):
    """Refresh an inline Jupyter preview; fall back to no-op outside Jupyter."""
    try:
        from IPython.display import Image, clear_output, display

        ok, encoded = cv2.imencode(".jpg", frame_bgr)
        if ok:
            clear_output(wait=True)
            display(Image(data=encoded.tobytes(), format="jpeg"))
            print(title)
            return True
    except Exception:
        pass
    return False


def show_file(path, title):
    try:
        from IPython.display import Image, clear_output, display

        clear_output(wait=True)
        display(Image(filename=str(path)))
        print(title)
        return True
    except Exception:
        return False


def show_processed(input_path, raw_mask_path, corrected_mask_path, binary_path, title):
    """Display raw PL mask, corrected mask and normalized binary."""
    try:
        import matplotlib.pyplot as plt

        raw = cv2.cvtColor(cv2.imread(str(input_path)), cv2.COLOR_BGR2RGB)
        raw_mask = cv2.imread(str(raw_mask_path), cv2.IMREAD_GRAYSCALE)
        corrected_mask = cv2.imread(
            str(corrected_mask_path), cv2.IMREAD_GRAYSCALE
        )
        binary = cv2.imread(str(binary_path), cv2.IMREAD_GRAYSCALE)
        fig, axes = plt.subplots(1, 4, figsize=(15, 4))
        axes[0].imshow(raw)
        axes[0].set_title("input")
        axes[1].imshow(raw_mask, cmap="gray", vmin=0, vmax=255)
        axes[1].set_title("raw PL mask")
        axes[2].imshow(corrected_mask, cmap="gray", vmin=0, vmax=255)
        axes[2].set_title("corrected mask")
        axes[3].imshow(binary, cmap="gray", vmin=0, vmax=255)
        axes[3].set_title("normalized 128x128")
        for axis in axes:
            axis.axis("off")
        fig.suptitle(title)
        fig.tight_layout()
        from IPython.display import display
        display(fig)
        plt.close(fig)
        return True
    except Exception as exc:
        print(f"processed image display unavailable: {exc}")
        return False


def show_cpu_processed(input_path, binary_path, title):
    """Display the captured frame and CPU-generated normalized binary image."""
    try:
        import matplotlib.pyplot as plt

        input_image = cv2.cvtColor(
            cv2.imread(str(input_path)), cv2.COLOR_BGR2RGB
        )
        binary = cv2.imread(str(binary_path), cv2.IMREAD_GRAYSCALE)
        fig, axes = plt.subplots(1, 2, figsize=(9, 4))
        axes[0].imshow(input_image)
        axes[0].set_title("input")
        axes[1].imshow(binary, cmap="gray", vmin=0, vmax=255)
        axes[1].set_title("CPU normalized 128x128")
        for axis in axes:
            axis.axis("off")
        fig.suptitle(title)
        fig.tight_layout()
        from IPython.display import display
        display(fig)
        plt.close(fig)
        return True
    except Exception as exc:
        print(f"processed image display unavailable: {exc}")
        return False


def open_camera(camera, width, height):
    cap = cv2.VideoCapture(camera, cv2.CAP_V4L2)
    if not cap.isOpened():
        cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        raise RuntimeError(f"camera open failed: {camera}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def countdown_capture(cap, seconds, preview_interval, window_preview=False):
    start = time.time()
    last_preview = 0.0
    latest = None
    while True:
        ok, frame = cap.read()
        if not ok:
            raise RuntimeError("camera read failed during countdown")
        latest = frame
        elapsed = time.time() - start
        remaining = seconds - elapsed
        if remaining <= 0:
            return latest
        now = time.time()
        if now - last_preview >= preview_interval:
            title = (
                f"请摆好手势，{remaining:.1f} 秒后拍摄。"
                " 手尽量在画面中央，不要贴边。"
            )
            if window_preview:
                preview = frame.copy()
                cv2.putText(
                    preview, title, (10, 28), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 0), 1, cv2.LINE_AA,
                )
                cv2.imshow("sign-language camera preview", preview)
                if (cv2.waitKey(1) & 0xFF) == ord("q"):
                    raise KeyboardInterrupt
            else:
                show_frame(frame, title)
            last_preview = now
        time.sleep(0.01)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/static_numpy_model.npz")
    ap.add_argument("--camera", default="/dev/video0")
    ap.add_argument("--backend", choices=("cpu", "pl"), default="pl")
    ap.add_argument(
        "--overlay",
        default="board/overlays/sign_preprocess_2026_1/sign_preprocess_2026_1.bit",
    )
    ap.add_argument("--pl-input-layout", choices=("packed_rgb", "rgbx32"), default="packed_rgb")
    ap.add_argument("--pl-timeout", type=float, default=3.0)
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
    ap.add_argument("--countdown", type=float, default=3.0)
    ap.add_argument("--preview-interval", type=float, default=0.15)
    ap.add_argument(
        "--window-preview", action="store_true",
        help="在电脑桌面窗口中实时显示摄像头画面（按 q 可中断）",
    )
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--out-dir", default="report/static_interactive")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    preprocess_fn = None
    pl = None
    latest_binary = None
    latest_info = None
    latest_mask = None
    latest_corrected_mask = None
    if args.backend == "pl":
        from pl_preprocess import PLPreprocessor

        pl = PLPreprocessor(
            overlay_path=args.overlay,
            input_layout=args.pl_input_layout,
            timeout_s=args.pl_timeout,
        )
        print(json.dumps({"pl": pl.diagnostics()}, ensure_ascii=False, indent=2))

        def preprocess_fn(frame):
            nonlocal latest_binary, latest_info, latest_mask
            nonlocal latest_corrected_mask
            latest_mask = pl.run_mask(frame)
            latest_corrected_mask, _ = correct_mask_polarity(latest_mask)
            latest_binary, latest_info = preprocess_mask(latest_mask)
            latest_info["backend"] = "pl"
            latest_info["pl_frame_size"] = pl.frame_size
            latest_info["pl_input_layout"] = pl.input_layout
            return latest_binary, latest_info
    else:
        def preprocess_fn(frame):
            nonlocal latest_binary, latest_info
            latest_binary, latest_info = preprocess_frame(frame)
            return latest_binary, latest_info

    predictor = NumpyStaticPredictor(
        args.model,
        margin_threshold=args.margin_threshold,
        unknown_gap_threshold=args.unknown_gap_threshold,
        preprocess_fn=preprocess_fn,
    )
    camera = int(args.camera) if str(args.camera).isdigit() else args.camera
    cap = open_camera(camera, args.width, args.height)
    shot = 0

    print("交互式静态识别已启动。每次回车拍摄，输入 q 退出。")
    try:
        while True:
            command = input("按回车开始倒计时，输入 q 退出：").strip().lower()
            if command == "q":
                break

            shot += 1
            frame = countdown_capture(
                cap,
                args.countdown,
                args.preview_interval,
                args.window_preview,
            )
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            shot_dir = out_dir / f"shot_{shot:03d}_{timestamp}"
            shot_dir.mkdir(parents=True, exist_ok=True)

            input_path = shot_dir / "input_frame.jpg"
            cv2.imwrite(str(input_path), frame)
            result, info = predictor.predict(frame)

            raw_mask_path = None
            corrected_mask_path = None
            binary_path = None
            mask_stats = None
            if latest_mask is not None:
                raw_mask_path = shot_dir / "pl_mask_raw.png"
                corrected_mask_path = shot_dir / "pl_mask_corrected.png"
                cv2.imwrite(str(raw_mask_path), latest_mask)
                cv2.imwrite(str(corrected_mask_path), latest_corrected_mask)
                if latest_binary is not None:
                    binary_path = shot_dir / "binary_128.png"
                    cv2.imwrite(str(binary_path), latest_binary)
                nonzero = int(np.count_nonzero(latest_mask))
                mask_stats = {
                    "min": int(latest_mask.min()),
                    "max": int(latest_mask.max()),
                    "mean": float(latest_mask.mean()),
                    "nonzero": nonzero,
                    "nonzero_ratio": float(nonzero / latest_mask.size),
                    "unique_values": [
                        int(value) for value in np.unique(latest_mask)[:16]
                    ],
                }
            # CPU mode has no PL mask, but its normalized model input must
            # still be saved for diagnosing segmentation and classification.
            if latest_binary is not None:
                binary_path = shot_dir / "binary_128.png"
                cv2.imwrite(str(binary_path), latest_binary)

            payload = {
                "shot": shot,
                "input": str(input_path),
                "backend": args.backend,
                "result": result,
                "preprocess": info,
                "pl": pl.diagnostics() if pl is not None else None,
                "mask_stats": mask_stats,
                "artifacts": {
                    "input": str(input_path),
                    "raw_mask": str(raw_mask_path) if raw_mask_path else None,
                    "corrected_mask": (
                        str(corrected_mask_path)
                        if corrected_mask_path else None
                    ),
                    "binary_128": str(binary_path) if binary_path else None,
                },
            }
            summary_path = shot_dir / "summary.json"
            summary_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            if raw_mask_path is not None and corrected_mask_path is not None:
                show_processed(
                    input_path,
                    raw_mask_path,
                    corrected_mask_path,
                    binary_path,
                    f"第 {shot} 次结果：{result['label']} / {result['text']} "
                    f"confidence={result['confidence']:.4f}",
                )
            elif binary_path is not None:
                show_cpu_processed(
                    input_path,
                    binary_path,
                    f"第 {shot} 次结果：{result['label']} / {result['text']} "
                    f"confidence={result['confidence']:.4f}",
                )
            else:
                show_file(
                    input_path,
                    f"第 {shot} 次结果：{result['label']} / {result['text']} "
                    f"confidence={result['confidence']:.4f}",
                )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            print(f"结果已保存：{summary_path}")
    finally:
        cap.release()
        if args.window_preview:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
