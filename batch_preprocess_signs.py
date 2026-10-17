"""批量预处理静态手语图片（B 负责）。

用法：
    python batch_preprocess_signs.py --input data/static --output data/processed/static

输入目录结构：<input>/<label>/<image>.{jpg,jpeg,png,bmp}
输出目录结构：<output>/<label>/<image>.png（128x128 二值图）
同时在 <output>/summary.json 写入统计信息（含无手、出框计数）。
"""

import argparse
import json
import os

import cv2

from labels import STATIC_LABELS
from preprocess import preprocess_frame

IMG_EXTS = (".jpg", ".jpeg", ".png", ".bmp")


def main():
    ap = argparse.ArgumentParser(description="批量预处理静态手语图片")
    ap.add_argument("--input", required=True, help="静态数据根目录")
    ap.add_argument("--output", required=True, help="预处理输出目录")
    args = ap.parse_args()

    if not os.path.isdir(args.input):
        raise SystemExit(f"输入目录不存在: {args.input}")

    summary = {}
    for label in sorted(os.listdir(args.input)):
        label_dir = os.path.join(args.input, label)
        if not os.path.isdir(label_dir):
            continue
        if label not in STATIC_LABELS:
            print(f"[warn] 跳过非法类别目录: {label}")
            continue
        out_dir = os.path.join(args.output, label)
        os.makedirs(out_dir, exist_ok=True)
        stats = {
            "total": 0,
            "ok": 0,
            "no_hand": 0,
            "touches_edge": 0,
            "severely_cropped": 0,
            "max_edge_contact_ratio": 0.0,
        }
        for name in sorted(os.listdir(label_dir)):
            if not name.lower().endswith(IMG_EXTS):
                continue
            stats["total"] += 1
            frame = cv2.imread(os.path.join(label_dir, name))
            if frame is None:
                print(f"[warn] 无法读取图片: {name}")
                continue
            binary, info = preprocess_frame(frame)
            if binary is None:
                stats["no_hand"] += 1
                continue
            if info["touches_edge"]:
                stats["touches_edge"] += 1
            if info["severely_cropped"]:
                stats["severely_cropped"] += 1
            stats["max_edge_contact_ratio"] = max(
                stats["max_edge_contact_ratio"],
                float(info["edge_contact_ratio"]),
            )
            stem = os.path.splitext(name)[0]
            cv2.imwrite(os.path.join(out_dir, stem + ".png"), binary)
            stats["ok"] += 1
        summary[label] = stats
        print(f"[{label}] {stats}")

    os.makedirs(args.output, exist_ok=True)
    with open(os.path.join(args.output, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print(f"完成，统计已写入 {os.path.join(args.output, 'summary.json')}")


if __name__ == "__main__":
    main()
