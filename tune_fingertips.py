#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指尖检测参数网格搜索：找出让 1-5 的中位指尖数正确匹配标签的 cos_thr/min_dist_ratio。"""
import glob
import os

import numpy as np

import cv2
from pynq_sign_language import HandSeg, count_fingertips

DS = os.path.join("dataset", "dataset", "raw_static_aug_v1")
seg = HandSeg()
seg.max_ratio, seg.min_ratio = 0.97, 0.005

cache = {}
for lab in range(1, 6):
    d = os.path.join(DS, "number_%d" % lab)
    cnts = []
    for fp in sorted(glob.glob(os.path.join(d, "*.jpg")))[:25]:
        img = cv2.imread(fp)
        if img is None:
            continue
        cnt, _ = seg(img)
        if cnt is not None:
            cnts.append(cnt)
    cache[lab] = cnts
    print("[load] number_%d: %d 轮廓" % (lab, len(cnts)))

print("\ncos_thr  dist    " + "  ".join("n%d" % l for l in range(1, 6)) + "   误差")
best, best_err = None, 1e9
for cos_thr in (0.25, 0.35, 0.45, 0.55):
    for mdr in (0.55, 0.62, 0.70, 0.78):
        meds = []
        for lab in range(1, 6):
            nf = [count_fingertips(c, cos_thr, mdr)[0] for c in cache[lab]]
            meds.append(int(np.median(nf)) if nf else -1)
        err = sum(abs(m - l) for m, l in zip(meds, range(1, 6)))
        flag = ""
        if err < best_err:
            best_err, best = err, (cos_thr, mdr)
            flag = " <="
        print("%5.2f   %5.2f   " % (cos_thr, mdr) +
              "  ".join("%2d" % m for m in meds) + "   %d%s" % (err, flag))

print("\n最优: cos_thr=%.2f min_dist_ratio=%.2f (误差 %d)" % (best[0], best[1], best_err))
