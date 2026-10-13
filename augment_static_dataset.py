import argparse
import csv
import random
import shutil
from pathlib import Path

import cv2
import numpy as np

from labels import STATIC_LABELS

IMG_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def image_files(root):
    return sorted(
        path for path in root.iterdir()
        if path.is_file() and path.suffix.lower() in IMG_EXTS
    )


def clamp_shift(width, height, max_shift_ratio=0.08):
    return (
        random.randint(-int(width * max_shift_ratio), int(width * max_shift_ratio)),
        random.randint(-int(height * max_shift_ratio), int(height * max_shift_ratio)),
    )


def augment_image(image):
    h, w = image.shape[:2]

    angle = random.uniform(-12.0, 12.0)
    scale = random.uniform(0.90, 1.10)
    tx, ty = clamp_shift(w, h)
    center = (w / 2.0, h / 2.0)
    matrix = cv2.getRotationMatrix2D(center, angle, scale)
    matrix[0, 2] += tx
    matrix[1, 2] += ty

    border = tuple(int(x) for x in np.median(image.reshape(-1, 3), axis=0))
    out = cv2.warpAffine(
        image,
        matrix,
        (w, h),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=border,
    )

    alpha = random.uniform(0.85, 1.18)
    beta = random.uniform(-18.0, 18.0)
    out = cv2.convertScaleAbs(out, alpha=alpha, beta=beta)

    if random.random() < 0.30:
        out = cv2.GaussianBlur(out, (3, 3), 0)

    if random.random() < 0.35:
        noise = np.random.normal(0, random.uniform(2.0, 6.0), out.shape)
        out = np.clip(out.astype(np.float32) + noise, 0, 255).astype(np.uint8)

    return out


def copy_originals(src_files, out_dir):
    copied = []
    for src in src_files:
        dst = out_dir / src.name
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="dataset/raw_static_v1")
    ap.add_argument("--output", default="dataset/raw_static_aug_v1")
    ap.add_argument("--target-per-class", type=int, default=80)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    random.seed(args.seed)
    np.random.seed(args.seed)

    input_root = Path(args.input)
    output_root = Path(args.output)

    if not input_root.is_dir():
        raise SystemExit(f"input directory not found: {input_root}")

    if output_root.exists() and args.overwrite:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    report_rows = []

    for label in STATIC_LABELS:
        src_dir = input_root / label
        if not src_dir.is_dir():
            print(f"[warn] missing class directory: {label}")
            continue

        out_dir = output_root / label
        out_dir.mkdir(parents=True, exist_ok=True)

        src_files = image_files(src_dir)
        copy_originals(src_files, out_dir)

        if not src_files:
            print(f"[warn] no source images: {label}")
            continue

        need = max(0, args.target_per_class - len(src_files))
        generated = 0
        for i in range(need):
            src = src_files[i % len(src_files)]
            image = cv2.imread(str(src))
            if image is None:
                report_rows.append({
                    "label": label,
                    "source": str(src),
                    "output": "",
                    "status": "cannot_read",
                })
                continue

            aug = augment_image(image)
            out_name = f"{src.stem}_aug_{i + 1:03d}.jpg"
            out_path = out_dir / out_name
            cv2.imwrite(str(out_path), aug)
            generated += 1
            report_rows.append({
                "label": label,
                "source": str(src),
                "output": str(out_path),
                "status": "generated",
            })

        print(
            f"[{label}] original={len(src_files)} generated={generated} "
            f"total={len(src_files) + generated}"
        )

    report_path = Path("report") / "static_augmentation_report.csv"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with report_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["label", "source", "output", "status"])
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"output: {output_root}")
    print(f"report: {report_path}")


if __name__ == "__main__":
    main()
