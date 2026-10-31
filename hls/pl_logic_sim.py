#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯 Python 复现 skin_morph.cpp 的行缓冲/窗口/时延逻辑，与 OpenCV 逐像素对比。

目的：在没有 HLS 头文件、没有板卡的情况下，先验证行缓冲延迟链和
输出时机的推导是否正确——这部分写错的话，综合出来的 IP 会整体错位。
用小图跑（逐像素循环慢，逻辑与尺寸无关）。
"""
import os
import sys

import cv2
import numpy as np

CR_LO, CR_HI, CB_LO, CB_HI = 130, 185, 75, 145
K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
# 5x5 椭圆核 = 去掉 4 个角
KMASK = np.ones((5, 5), bool)
KMASK[0, 0] = KMASK[0, 4] = KMASK[4, 0] = KMASK[4, 4] = False


def pl_bgr_to_mask(img):
    """等价于 HLS 里的定点 Cr/Cb 计算。"""
    b = img[:, :, 0].astype(np.int16)
    g = img[:, :, 1].astype(np.int16)
    r = img[:, :, 2].astype(np.int16)
    cr = 128 + ((128 * r - 107 * g - 21 * b) >> 8)
    cb = 128 + ((-43 * r - 85 * g + 128 * b) >> 8)
    m = ((cr >= CR_LO) & (cr <= CR_HI) & (cb >= CB_LO) & (cb <= CB_HI))
    return (m * 255).astype(np.uint8)


def pl_morph(mask, is_erode):
    """逐像素复现 morph_stage 的行缓冲 + 窗口 + 输出时机。"""
    rows, cols = mask.shape
    PAD = 255 if is_erode else 0
    # 4 个行缓冲，索引到 cols+6
    lb = [np.zeros(cols + 6, np.uint8) for _ in range(4)]
    w = np.zeros((5, 5), np.uint8)
    out = np.zeros(rows * cols, np.uint8)
    oi = 0
    for py in range(rows + 6):
        for px in range(cols + 6):
            v0 = lb[0][px]
            v1 = lb[1][px]
            v2 = lb[2][px]
            v3 = lb[3][px]
            sy, sx = py - 4, px - 4
            if 0 <= sy < rows and 0 <= sx < cols:
                cur = mask[sy, sx]
            else:
                cur = PAD
            lb[0][px] = cur
            lb[1][px] = v0
            lb[2][px] = v1
            lb[3][px] = v2
            w[:, 0:4] = w[:, 1:5]
            w[0, 4] = v3
            w[1, 4] = v2
            w[2, 4] = v1
            w[3, 4] = v0
            w[4, 4] = cur
            if py >= 6 and px >= 6:
                vals = w[KMASK]
                out[oi] = vals.min() if is_erode else vals.max()
                oi += 1
    return out.reshape(rows, cols)


def main():
    W, H = 128, 96
    here = os.path.dirname(os.path.abspath(__file__))
    ds = os.path.join(here, "..", "dataset", "dataset", "raw_static_aug_v1")
    import glob
    files = sorted(glob.glob(os.path.join(ds, "number_*", "*.jpg")))[:2]
    if len(files) < 2:
        print("[ERR] 找不到测试图")
        return 1

    allok = True
    for fp in files:
        img = cv2.resize(cv2.imread(fp), (W, H))
        # 白平衡（与 PS 端一致）
        sm = img[::4, ::4].reshape(-1, 3).astype(np.float32)
        gain = sm.mean(axis=0)
        gain = gain.mean() / (gain + 1e-6)
        lut = [np.clip(np.arange(256, dtype=np.float32) * g, 0, 255).astype(np.uint8)
               for g in gain]
        wb = cv2.merge([cv2.LUT(c, l) for c, l in zip(cv2.split(img), lut)])

        # --- PS 参考 ---
        ycc = cv2.cvtColor(wb, cv2.COLOR_BGR2YCrCb)
        ref = cv2.inRange(ycc, (0, CR_LO, CB_LO), (255, CR_HI, CB_HI))
        ref = cv2.morphologyEx(ref, cv2.MORPH_OPEN, K)
        ref = cv2.morphologyEx(ref, cv2.MORPH_CLOSE, K)

        # --- PL 仿真 ---
        m = pl_bgr_to_mask(wb)
        m = pl_morph(m, True)
        m = pl_morph(m, False)
        m = pl_morph(m, False)
        m = pl_morph(m, True)

        # 分阶段对比（定位是哪一级错）
        ycc2 = cv2.cvtColor(wb, cv2.COLOR_BGR2YCrCb)
        r0 = cv2.inRange(ycc2, (0, CR_LO, CB_LO), (255, CR_HI, CB_HI))
        p0 = pl_bgr_to_mask(wb)
        r1 = cv2.erode(r0, K)
        p1 = pl_morph(p0, True)
        r2 = cv2.dilate(r1, K)
        p2 = pl_morph(p1, False)

        name = os.path.basename(fp)
        d0 = int((p0 != r0).sum())
        d1 = int((p1 != r1).sum())
        d2 = int((p2 != r2).sum())
        df = int((m != ref).sum())
        tot = ref.size
        print("%s" % name)
        print("  阈值级   差异 %5d / %d  (%.3f%%)" % (d0, tot, 100.0 * d0 / tot))
        print("  erode级  差异 %5d / %d  (%.3f%%)" % (d1, tot, 100.0 * d1 / tot))
        print("  dilate级 差异 %5d / %d  (%.3f%%)" % (d2, tot, 100.0 * d2 / tot))
        print("  全链路   差异 %5d / %d  (%.3f%%)" % (df, tot, 100.0 * df / tot))
        if df > tot * 0.02:
            allok = False
            # 打印窗口错位诊断：若整体平移，说明输出时机错
            ys, xs = np.where(m != ref)
            if len(ys):
                print("    差异位置 y[%d,%d] x[%d,%d]" % (ys.min(), ys.max(), xs.min(), xs.max()))

    print("\n%s" % ("逻辑推导正确：与 OpenCV 逐像素一致"
                    if allok else "逻辑与 OpenCV 不一致，需修正时延/窗口方向"))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
