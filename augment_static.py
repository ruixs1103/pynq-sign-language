# -*- coding: utf-8 -*-
"""把 number_6 / number_7 增广到与 1-5 相同规模（默认 110 张）。

命名 <原名>_aug_XXX.jpg —— evaluate_features 的 group_key 会剥掉 _aug_XXX，
同一原图的增广样本不会被拆到训练/测试两侧（防泄漏）。
可重复执行：已存在的 _aug_ 文件自动跳过。

    py augment_static.py                # 6/7 都补到 110
    py augment_static.py --classes 6 --target 100
"""
import argparse
import glob
import os
import random

import cv2

DS = os.path.join("dataset", "dataset", "raw_static_aug_v1")
rng = random.Random(6)


def variants(img):
    """每张原图最多 7 个变体：翻转 + 旋转 + 缩放。"""
    h, w = img.shape[:2]
    out = [cv2.flip(img, 1)]
    for ang in (-12, -6, 6, 12):
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), ang, 1.0)
        out.append(cv2.warpAffine(img, M, (w, h),
                                  borderMode=cv2.BORDER_REPLICATE))
    for s in (0.92, 1.06):
        M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), 0, s)
        out.append(cv2.warpAffine(img, M, (w, h),
                                  borderMode=cv2.BORDER_REPLICATE))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--classes", default="6,7")
    ap.add_argument("--target", type=int, default=110)
    args = ap.parse_args()

    for c in [x.strip() for x in args.classes.split(",") if x.strip()]:
        d = os.path.join(DS, "number_" + c)
        files = sorted(glob.glob(os.path.join(d, "*.jpg")))
        raws = [f for f in files if "_aug_" not in os.path.basename(f)]
        need = args.target - len(files)
        print("number_%s: 原始 %d  现有 %d  需增广 %d"
              % (c, len(raws), len(files), max(need, 0)))
        if need <= 0 or not raws:
            continue
        order = raws[:]
        rng.shuffle(order)
        made, vi = 0, 0
        while made < need and vi < len(variants(cv2.imread(order[0]))):
            for f in order:
                if made >= need:
                    break
                img = cv2.imread(f)
                if img is None:
                    continue
                stem = os.path.splitext(os.path.basename(f))[0]
                out = os.path.join(d, "%s_aug_%03d.jpg" % (stem, vi + 1))
                if os.path.exists(out):
                    continue
                cv2.imwrite(out, variants(img)[vi])
                made += 1
            vi += 1
        print("  -> 新增 %d 张，现共 %d 张" % (made, len(glob.glob(os.path.join(d, '*.jpg')))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
