#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端：PL 链路(定点阈值+行缓冲形态学) 出来的 mask 进识别，与 PS 链路对比。"""
import glob
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..")))

import cv2
import numpy as np

from pl_logic_sim import pl_bgr_to_mask, pl_morph
from pynq_sign_language import HandSeg, StaticRecognizer, centroid_xy, feature_vec

W, H = 320, 240
CR_LO, CR_HI, CB_LO, CB_HI = 130, 185, 75, 145
K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.normpath(os.path.join(here, ".."))
ds = os.path.join(root, "dataset", "dataset", "raw_static_aug_v1")
t = json.load(open(os.path.join(root, "sign_templates.json"), encoding="utf-8"))
meta = t["meta"]
rec = StaticRecognizer(t["static"], meta)
mu = np.asarray(meta["mu"], np.float32)
sd = np.asarray(meta["sd"], np.float32)


def gray_world(frame):
    sm = frame[::4, ::4].reshape(-1, 3).astype(np.float32)
    means = sm.mean(axis=0)
    gain = means.mean() / (means + 1e-6)
    lut = [np.clip(np.arange(256, dtype=np.float32) * g, 0, 255).astype(np.uint8)
           for g in gain]
    return cv2.merge([cv2.LUT(c, l) for c, l in zip(cv2.split(frame), lut)])


def biggest(mask, scale):
    res = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = res[0] if len(res) == 2 else res[1]
    if not cnts:
        return None
    cnt = max(cnts, key=cv2.contourArea)
    a = cv2.contourArea(cnt)
    if a < 0.02 * W * H or a > 0.55 * W * H:
        return None
    return cnt


def pl_mask(wb):
    m = pl_bgr_to_mask(wb)
    m = pl_morph(m, True)
    m = pl_morph(m, False)
    m = pl_morph(m, False)
    return pl_morph(m, True)


def ps_mask(wb):
    ycc = cv2.cvtColor(wb, cv2.COLOR_BGR2YCrCb)
    m = cv2.inRange(ycc, (0, CR_LO, CB_LO), (255, CR_HI, CB_HI))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, K)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, K)


agree = tot = acc_p = acc_l = 0
fd = []
ad = []
t_pl = t_ps = 0.0
for d in sorted(os.listdir(ds)):
    mo = re.match(r"^number_(\d+)$", d)
    if not mo:
        continue
    gold = mo.group(1)
    # 每类取 1 张（逐像素仿真慢）
    for fp in sorted(glob.glob(os.path.join(ds, d, "*.jpg")))[:1]:
        img = cv2.resize(cv2.imread(fp), (W, H))
        wb = gray_world(img)

        t0 = time.time()
        mpl = pl_mask(wb)
        t_pl += time.time() - t0
        t0 = time.time()
        mps = ps_mask(wb)
        t_ps += time.time() - t0

        c1, c2 = biggest(mps, 1.0), biggest(mpl, 1.0)
        if c1 is None or c2 is None:
            print("%s: 单侧未检出 (ps=%s pl=%s)" % (gold, c1 is not None, c2 is not None))
            continue
        v1, v2 = feature_vec(c1, meta["mode"]), feature_vec(c2, meta["mode"])
        z1, z2 = (v1 - mu) / sd, (v2 - mu) / sd
        fd.append(float(np.linalg.norm(z1 - z2)))
        ad.append(abs(cv2.contourArea(c1) - cv2.contourArea(c2)) / cv2.contourArea(c1))
        p1 = rec.predict(c1)[0]
        p2 = rec.predict(c2)[0]
        tot += 1
        agree += (p1 == p2)
        acc_p += (p1 == gold)
        acc_l += (p2 == gold)
        print("  数字%s: PS判=%s PL判=%s  面积差%.2f%%  特征距离%.4f"
              % (gold, p1, p2, 100 * ad[-1], fd[-1]))

print("\n样本 %d 张  (纯 Python 逐像素仿真，仅用于验证一致性，不代表板上速度)" % tot)
print("PS/PL 预测一致率: %.0f%%" % (100.0 * agree / max(tot, 1)))
print("PS 准确率 %.0f%%   PL 准确率 %.0f%%" % (100.0 * acc_p / max(tot, 1),
                                              100.0 * acc_l / max(tot, 1)))
print("特征 z 距离 中位 %.4f 最大 %.4f" % (np.median(fd), np.max(fd)))
print("面积相对差 中位 %.2f%% 最大 %.2f%%" % (100 * np.median(ad), 100 * np.max(ad)))
