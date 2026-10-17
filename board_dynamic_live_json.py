import argparse
import json
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from labels import DYNAMIC_KIND, DYNAMIC_LABELS, make_result
from sequence_features import DEFAULT_SEQ_LEN, extract_sequence_features
from dynamic_numpy_model import NumpyDynamicForest


def open_camera(camera, width, height):
    # PYNQ-Z2 runs Linux; CAP_DSHOW is Windows-only and can silently fail.
    # Prefer an explicit V4L2 device path, then fall back to the numeric node.
    if isinstance(camera, str) and camera.startswith("/dev/video"):
        cap = cv2.VideoCapture(camera, cv2.CAP_V4L2)
    else:
        cap = cv2.VideoCapture(int(camera), cv2.CAP_V4L2)
    if not cap.isOpened():
        cap.release()
        cap = cv2.VideoCapture(camera)
    if not cap.isOpened():
        raise SystemExit(f"camera open failed: {camera}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def predict_dynamic(model, frames, labels, preprocess_fn):
    x = extract_sequence_features(
        frames, seq_len=len(frames), preprocess_fn=preprocess_fn
    )
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(np.stack([x]))[0]
        classes = [str(c) for c in model.classes_]
        best = int(np.argmax(proba))
        label = classes[best]
        confidence = float(proba[best])
        scores = {classes[i]: float(proba[i]) for i in range(len(classes))}
    else:
        label = str(model.predict(np.stack([x]))[0])
        confidence = 1.0
        scores = {label: confidence}
    if label not in labels:
        label = "unknown"
        confidence = 1.0
    return make_result(label, confidence, DYNAMIC_KIND), scores


def load_model(path):
    if str(path).lower().endswith(".npz"):
        return NumpyDynamicForest(path)
    try:
        import joblib
    except ImportError as exc:
        raise RuntimeError(
            "This model is .joblib, but joblib is unavailable. "
            "Use dynamic_model_numpy.npz on the board."
        ) from exc
    return joblib.load(path)


def draw_overlay(frame, result, count, seq_len):
    text = f"{result['label']} / {result['text']}  {result['confidence']:.2f}"
    cv2.putText(
        frame,
        text,
        (12, 28),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.75,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )
    cv2.putText(
        frame,
        f"dynamic frames {count}/{seq_len} | q exit",
        (12, 58),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (0, 255, 0),
        2,
        cv2.LINE_AA,
    )


def show_jupyter_preview(frame_bgr):
    try:
        from IPython.display import Image, clear_output, display

        ok, encoded = cv2.imencode(".jpg", frame_bgr)
        if not ok:
            return False
        clear_output(wait=True)
        display(Image(data=encoded.tobytes(), format="jpeg"))
        return True
    except Exception as exc:
        print(f"jupyter preview unavailable: {exc}")
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="models/dynamic_model_numpy.npz")
    ap.add_argument("--backend", choices=("cpu", "pl"), default="pl")
    ap.add_argument(
        "--overlay",
        default="board/overlays/sign_preprocess_2026_1/sign_preprocess_2026_1.bit",
    )
    ap.add_argument("--camera", default="/dev/video0")
    ap.add_argument("--seq-len", type=int, default=DEFAULT_SEQ_LEN, choices=(16, 24))
    ap.add_argument("--stride", type=int, default=4)
    ap.add_argument(
        "--pl-frame-stride", type=int, default=4,
        help="PL 每隔多少个摄像头帧处理一次，中间帧复用最近 PL 结果",
    )
    # 320x240 is sufficient for the hand ROI and substantially reduces
    # V4L2 capture, feature extraction, JPEG encoding, and notebook refresh cost.
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--output", default="report/latest_dynamic_result.json")
    ap.add_argument("--save-frame", default="report/latest_dynamic_frame.jpg")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--jupyter-preview", action="store_true")
    ap.add_argument(
        "--product",
        action="store_true",
        help="展示模式：自动启用 Jupyter 预览并持续保存带结果画面",
    )
    ap.add_argument("--preview-interval", type=float, default=0.25)
    args = ap.parse_args()
    if args.pl_frame_stride < 1:
        raise SystemExit("--pl-frame-stride 必须 >= 1")

    # A single switch makes the board demo reproducible in a notebook.
    # It keeps capture, inference, result JSON, and the annotated preview in
    # one process instead of asking the presenter to run separate pipelines.
    if args.product:
        args.jupyter_preview = True
        args.preview_interval = min(args.preview_interval, 0.12)

    camera = int(args.camera) if str(args.camera).isdigit() else args.camera
    output = Path(args.output)
    save_frame = Path(args.save_frame)
    output.parent.mkdir(parents=True, exist_ok=True)
    save_frame.parent.mkdir(parents=True, exist_ok=True)

    model = load_model(args.model)
    if args.backend == "pl":
        from pl_preprocess import PLPreprocessor
        # Match the CPU training preprocessing thresholds exactly.  The
        # dynamic model was trained on this YCrCb range; using the broader
        # legacy PL range makes its HOG/shape features out-of-domain.
        pl = PLPreprocessor(
            overlay_path=args.overlay,
            timeout_s=3.0,
            thresholds={
                "y_min": 0,
                "y_max": 255,
                "cr_min": 138,
                "cr_max": 170,
                "cb_min": 82,
                "cb_max": 122,
            },
        )
        preprocess_fn = pl.preprocess_frame
        print("preprocess=FPGA PL, classifier=ARM PS")
    else:
        from preprocess import preprocess_frame
        preprocess_fn = preprocess_frame
        print("preprocess=ARM PS CPU, classifier=ARM PS")
    cap = open_camera(camera, args.width, args.height)
    buffer = deque(maxlen=args.seq_len)
    feature_buffer = deque(maxlen=args.seq_len)
    count = 0

    print("dynamic live json app started. Press Ctrl+C to stop.")
    if args.product:
        print("product demo mode: camera + inference + annotated Jupyter preview + JSON")
    print(f"model={args.model}")
    print(f"camera={camera} seq_len={args.seq_len} stride={args.stride}")

    last_result = make_result("unknown", 1.0, DYNAMIC_KIND)
    last_scores = {}
    last_preview = 0.0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("camera read failed")
                time.sleep(0.2)
                continue

            buffer.append(frame.copy())
            if args.backend == "pl" and (
                len(feature_buffer) == 0 or count % args.pl_frame_stride == 0
            ):
                # Run PL exactly once per captured frame. The cached mask and
                # metadata are reused by dynamic feature extraction instead
                # of triggering 16 DMA transfers for every prediction window.
                pl_binary, pl_info = preprocess_fn(frame)
                feature_buffer.append((pl_binary, pl_info))
            else:
                if args.backend == "pl" and feature_buffer:
                    feature_buffer.append(feature_buffer[-1])
                else:
                    feature_buffer.append(frame.copy())
            count += 1

            if len(buffer) == args.seq_len and count % args.stride == 0:
                try:
                    last_result, last_scores = predict_dynamic(
                        model, list(feature_buffer), set(DYNAMIC_LABELS), preprocess_fn
                    )
                except Exception as exc:
                    # 1.0 here would falsely suggest a confident prediction;
                    # zero explicitly marks an inference failure.
                    last_result = make_result("unknown", 0.0, DYNAMIC_KIND)
                    last_scores = {"error": str(exc)}
                    print(f"dynamic inference error: {type(exc).__name__}: {exc}")

                payload = {
                    "count": count,
                    "timestamp": time.time(),
                    "seq_len": args.seq_len,
                    "stride": args.stride,
                    "backend": args.backend,
                    "result": last_result,
                    "scores": last_scores,
                }
                # Atomic replacement prevents the PC dashboard from reading a
                # half-written JSON/JPEG while the board is updating results.
                output_tmp = output.with_suffix(output.suffix + ".tmp")
                output_tmp.write_text(
                    json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                output_tmp.replace(output)
                frame_tmp = save_frame.with_suffix(save_frame.suffix + ".tmp.jpg")
                cv2.imwrite(str(frame_tmp), frame)
                frame_tmp.replace(save_frame)
                print(
                    f"[{count:04d}] label={last_result['label']} "
                    f"text={last_result['text']} "
                    f"confidence={last_result['confidence']:.4f}"
                )

            if args.show:
                preview = frame.copy()
                draw_overlay(preview, last_result, len(buffer), args.seq_len)
                cv2.imshow("Dynamic Live", preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q"), ord("Q")):
                    break

            if args.jupyter_preview:
                now = time.time()
                if now - last_preview >= args.preview_interval:
                    preview = frame.copy()
                    draw_overlay(
                        preview,
                        last_result,
                        len(buffer),
                        args.seq_len,
                    )
                    show_jupyter_preview(preview)
                    print(
                        f"[{count:04d}] label={last_result['label']} "
                        f"text={last_result['text']} "
                        f"confidence={last_result['confidence']:.4f}"
                    )
                    print("Interrupt kernel to stop.")
                    last_preview = now
    finally:
        cap.release()
        if args.show:
            cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
