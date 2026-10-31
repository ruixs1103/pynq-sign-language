#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HLS IP 的 C 仿真验证：生成激励 -> 调 tb.exe -> 与 OpenCV 参考逐像素对比。

用法:
    python pl_sim_check.py                # 用默认 640x480
    python pl_sim_check.py --width 320 --height 240 --n 5

依赖: 已用 g++ 编译好 tb.exe（见 hls/README 里的命令）。
"""
import argparse
import glob
import os
import subprocess
import sys

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DS = os.path.join(HERE, "..", "dataset", "dataset", "raw_static_aug_v1")

# 必须与 PS 端 HandSeg 保持一致
CR_LO, CR_HI, CB_LO, CB_HI = 130, 185, 75, 145
K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))


def gray_world(frame):
    """与 PS 端 HandSeg.gray_world 等价（同样 1/4 采样 + LUT）。"""
    sm = frame[::4, ::4].reshape(-1, 3).astype(np.float32)
    means = sm.mean(axis=0)
    gain = means.mean() / (means + 1e-6)
    lut = [np.clip(np.arange(256, dtype=np.float32) * g, 0, 255).astype(np.uint8)
           for g in gain]
    return cv2.merge([cv2.LUT(c, l) for c, l in zip(cv2.split(frame), lut)])


def ref_mask(wb):
    """PS 端参考：cvtColor -> inRange -> OPEN -> CLOSE。"""
    ycc = cv2.cvtColor(wb, cv2.COLOR_BGR2YCrCb)
    m = cv2.inRange(ycc, (0, CR_LO, CB_LO), (255, CR_HI, CB_HI))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, K)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, K)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--n", type=int, default=4, help="测试图片数")
    ap.add_argument("--exe", default=os.path.join(HERE, "tb.exe"))
    args = ap.parse_args()

    files = []
    for d in sorted(os.listdir(DS)):
        if d.startswith("number_"):
            files += sorted(glob.glob(os.path.join(DS, d, "*.jpg")))
    files += sorted(glob.glob(os.path.join(DS, "unknown", "*.jpg")))
    if not files:
        print("[ERR] 找不到测试图片: %s" % DS)
        return 1
    files = files[:args.n]

    cwd = os.getcwd()
    os.chdir(HERE)
    try:
        # 激励文件无论有没有 tb.exe 都要生成：
        # Vitis HLS 的 csim_design 也读这两个文件，用它就不需要外部 g++
        with open("params.txt", "w") as f:
            f.write("%d %d %d %d %d %d"
                    % (args.height, args.width, CR_LO, CR_HI, CB_LO, CB_HI))
        img0 = cv2.resize(cv2.imread(files[0]), (args.width, args.height))
        gray_world(img0).tofile("in.raw")
        print("[gen] 已生成 params.txt / in.raw（供 Vitis HLS 的 csim_design 使用）")
    finally:
        os.chdir(cwd)

    if not os.path.isfile(args.exe):
        print("\n[提示] 找不到 %s —— 本机没有 g++ 也能继续，两条路任选：\n" % args.exe)
        print("  A) 用 Vitis HLS 自带的 C 仿真（推荐，零安装）：")
        print("       cd hls && vitis_hls -f run_hls.tcl")
        print("       脚本会先跑 csim_design 验证逻辑，再做综合\n")
        print("  B) 装 MinGW-w64 后用 g++ 编译（迭代更快，秒级）：")
        print("       g++ -I<VITIS_INCLUDE> %s %s -o %s"
              % (os.path.join(HERE, "tb_skin_morph.cpp"),
                 os.path.join(HERE, "skin_morph.cpp"), args.exe))
        return 0

    os.chdir(HERE)
    ok = True
    try:
        for fp in files:
            img = cv2.resize(cv2.imread(fp), (args.width, args.height))
            wb = gray_world(img)                    # 与 PS 端一致的白平衡
            wb.tofile("in.raw")
            ref = ref_mask(wb)

            r = subprocess.run([args.exe], capture_output=True, text=True)
            if r.returncode != 0:
                print("[FAIL] tb.exe 失败: %s" % r.stdout)
                ok = False
                break

            got = np.fromfile("out.raw", dtype=np.uint8)
            got = got.reshape(args.height, args.width)
            diff = (got != ref)
            nd = int(diff.sum())
            pct = 100.0 * nd / ref.size
            # 定点化导致的边界像素差异应极小；成片不一致说明逻辑错了
            status = "OK  " if pct < 0.5 else "FAIL"
            if pct >= 0.5:
                ok = False
            print("%s %-42s 差异 %6d px (%.3f%%)  mask占比 参考%.1f%% IP%.1f%%"
                  % (status, os.path.basename(fp), nd, pct,
                     100.0 * (ref > 0).mean(), 100.0 * (got > 0).mean()))
    finally:
        os.chdir(cwd)

    print("\n结论: %s" % ("IP 逻辑与 PS 端一致" if ok else "IP 逻辑与 PS 端不一致，需要排查"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
