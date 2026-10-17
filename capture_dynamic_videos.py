"""Capture dynamic sign-language videos for hello/thanks/goodbye/help.

The output layout matches train_dynamic_model.py:
    dataset/raw_dynamic_v1/<label>/<label>_YYYYmmdd_HHMMSS_xxx.avi
"""

import argparse
import csv
import time
from datetime import datetime
from pathlib import Path

import cv2

LABEL_KEYS = {
    "1": ("hello", "你好"),
    "2": ("thanks", "谢谢"),
    "3": ("goodbye", "再见"),
    "4": ("help", "帮助"),
    "5": ("unknown", "未知/非目标动作"),
}


def open_camera(index, width, height):
    cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
    if not cap.isOpened():
        cap = cv2.VideoCapture(index)
    if not cap.isOpened():
        raise RuntimeError(f"cannot open camera: {index}")
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    return cap


def ensure_dataset(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for label, _ in LABEL_KEYS.values():
        (root / label).mkdir(parents=True, exist_ok=True)
    return root


def init_manifest(path):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow([
            "filename",
            "relative_path",
            "label",
            "text",
            "timestamp",
            "collector",
            "background",
            "lighting",
            "distance_cm",
            "duration_s",
            "fps",
            "frame_count",
            "width",
            "height",
            "camera",
        ])


def draw_menu(frame, selected_text=None):
    lines = [
        "1 hello(nihao)  2 thanks  3 goodbye  4 help  5 unknown",
        "Press key to record | q/ESC exit",
    ]
    if selected_text:
        lines.append(selected_text)
    y = 28
    for line in lines:
        cv2.putText(
            frame,
            line,
            (12, y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0),
            2,
            cv2.LINE_AA,
        )
        y += 28


def countdown(cap, seconds, width, height, label_text):
    start = time.time()
    while True:
        ok, frame = cap.read()
        if not ok:
            return False
        remain = seconds - (time.time() - start)
        if remain <= 0:
            return True
        frame = cv2.resize(frame, (width, height))
        draw_menu(frame, f"Prepare: {label_text}  recording in {remain:.1f}s")
        cv2.imshow("Dynamic Gesture Capture", frame)
        key = cv2.waitKey(1) & 0xFF
        if key in (27, ord("q"), ord("Q")):
            return False


def record_clip(cap, out_path, duration, fps, width, height, label_text):
    writer = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*"MJPG"),
        fps,
        (width, height),
    )
    count = 0
    start = time.time()
    try:
        while time.time() - start < duration:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.resize(frame, (width, height))
            writer.write(frame)
            count += 1
            draw_menu(frame, f"Recording: {label_text}  {count} frames")
            cv2.imshow("Dynamic Gesture Capture", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
    finally:
        writer.release()
    return count


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--output", default="dataset/raw_dynamic_v1")
    ap.add_argument("--collector", default="A")
    ap.add_argument("--background", default="indoor_wall")
    ap.add_argument("--lighting", default="room_light")
    ap.add_argument("--distance-cm", type=float, default=60)
    ap.add_argument("--duration", type=float, default=3.0)
    ap.add_argument("--countdown", type=float, default=1.5)
    ap.add_argument("--fps", type=float, default=20)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    args = ap.parse_args()

    root = ensure_dataset(args.output)
    manifest = root / "dynamic_metadata.csv"
    init_manifest(manifest)

    cap = open_camera(args.camera, args.width, args.height)
    print("Dynamic capture started.")
    print("1=你好  2=谢谢  3=再见  4=帮助  5=unknown  q=退出")
    print(f"Output: {root}")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                print("camera read failed")
                break
            frame = cv2.resize(frame, (args.width, args.height))
            draw_menu(frame)
            cv2.imshow("Dynamic Gesture Capture", frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q"), ord("Q")):
                break
            item = LABEL_KEYS.get(chr(key))
            if item is None:
                continue

            label, text = item
            label_text = f"{label} / {text}"
            if not countdown(cap, args.countdown, args.width, args.height, label_text):
                break

            stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
            out_path = root / label / f"{label}_{stamp}.avi"
            frame_count = record_clip(
                cap,
                out_path,
                args.duration,
                args.fps,
                args.width,
                args.height,
                label_text,
            )
            if frame_count <= 0:
                print(f"[warn] no frames captured for {label_text}")
                continue

            rel = out_path.relative_to(root).as_posix()
            with manifest.open("a", newline="", encoding="utf-8-sig") as f:
                csv.writer(f).writerow([
                    out_path.name,
                    rel,
                    label,
                    text,
                    stamp,
                    args.collector,
                    args.background,
                    args.lighting,
                    args.distance_cm,
                    args.duration,
                    args.fps,
                    frame_count,
                    args.width,
                    args.height,
                    args.camera,
                ])
            print(f"saved: {out_path} ({frame_count} frames)")
    finally:
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
