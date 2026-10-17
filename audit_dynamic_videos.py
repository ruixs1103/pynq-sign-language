"""Audit dynamic gesture video files before training/evaluation."""

import argparse
import csv
from pathlib import Path

import cv2

from labels import DYNAMIC_LABELS

VIDEO_EXTS = {".avi", ".mp4", ".mov", ".mkv"}


def inspect_video(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        return {
            "ok": False,
            "reason": "cannot_open",
            "frame_count": 0,
            "fps": 0.0,
            "width": 0,
            "height": 0,
            "duration_s": 0.0,
            "read_first_frame": False,
        }

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    ok, _ = cap.read()
    cap.release()

    duration = float(frame_count / fps) if fps > 0 else 0.0
    reason = "ok"
    valid = True
    if not ok:
        reason = "cannot_read_first_frame"
        valid = False
    elif frame_count < 20:
        reason = "too_few_frames"
        valid = False
    elif duration < 1.0:
        reason = "too_short"
        valid = False
    elif width <= 0 or height <= 0:
        reason = "bad_resolution"
        valid = False

    return {
        "ok": valid,
        "reason": reason,
        "frame_count": frame_count,
        "fps": fps,
        "width": width,
        "height": height,
        "duration_s": duration,
        "read_first_frame": bool(ok),
    }


def iter_videos(root):
    root = Path(root)
    for label_dir in sorted(root.iterdir()):
        if not label_dir.is_dir() or label_dir.name not in DYNAMIC_LABELS:
            continue
        for path in sorted(label_dir.iterdir()):
            if path.is_file() and path.suffix.lower() in VIDEO_EXTS:
                yield label_dir.name, path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dataset/raw_dynamic_v1")
    ap.add_argument("--output", default="report/dynamic_video_audit.csv")
    args = ap.parse_args()

    root = Path(args.input)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    counts = {label: 0 for label in DYNAMIC_LABELS}
    bad = []
    for label, path in iter_videos(root):
        info = inspect_video(path)
        counts[label] += 1
        row = {
            "label": label,
            "file": str(path.relative_to(root)),
            "size_bytes": path.stat().st_size,
            **info,
        }
        rows.append(row)
        if not info["ok"]:
            bad.append(row)

    fieldnames = [
        "label",
        "file",
        "size_bytes",
        "ok",
        "reason",
        "frame_count",
        "fps",
        "width",
        "height",
        "duration_s",
        "read_first_frame",
    ]
    with out.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("dynamic video audit")
    print(f"input: {root}")
    print(f"report: {out}")
    print(f"total: {len(rows)}")
    for label in DYNAMIC_LABELS:
        print(f"{label}: {counts[label]}")
    print(f"bad: {len(bad)}")
    for row in bad[:20]:
        print(f"[bad] {row['file']} reason={row['reason']}")


if __name__ == "__main__":
    main()
