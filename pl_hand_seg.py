#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PL 加速版肤色分割（PYNQ 端驱动）。

把最贵的三步搬进 PL：BGR->YCrCb 转换、肤色阈值、5x5 椭圆核开/闭运算。
PS 端只保留灰世界白平衡（需要全图统计，不适合流处理）、打包、findContours。

接口与 HandSeg 完全一致：seg(frame, roi=None) -> (cnt, mask)

注意：本文件只在 PYNQ 上可用（依赖 pynq 包），PC 上不要 import。
"""
import cv2
import numpy as np


# ---- AXI4-Lite 地址偏移 ---------------------------------------------------
# 综合后请核对：
#   Vitis HLS 生成的 drivers/skin_morph_v1_0/src/xskin_morph_hw.h
# 里的 XSKIN_MORPH_CTRL_ADDR_ROWS_DATA / _COLS_DATA / _CR_LO_DATA ...
ADDR_CTRL = 0x00
ADDR_ROWS = 0x10
ADDR_COLS = 0x18
ADDR_CR_LO = 0x20
ADDR_CR_HI = 0x28
ADDR_CB_LO = 0x30
ADDR_CB_HI = 0x38

AP_START = 0x01
AP_DONE = 0x02
AP_IDLE = 0x04


class PlHandSeg(object):
    """参数 rows/cols 是最大尺寸（用于分配缓冲区）；ROI 更小时会动态配置 IP。"""

    def __init__(self, overlay, rows=480, cols=640,
                 cr_lo=130, cr_hi=185, cb_lo=75, cb_hi=145,
                 use_wb=True, wb_strength=None,
                 min_area_ratio=0.02, max_area_ratio=0.55):
        import pynq

        self.rows_max, self.cols_max = rows, cols
        self.npix_max = rows * cols
        self.use_wb = use_wb
        if wb_strength is None:
            wb_strength = 1.0 if use_wb else 0.0
        self.wb_strength = float(np.clip(wb_strength, 0.0, 1.0))
        self.min_ratio = min_area_ratio
        self.max_ratio = max_area_ratio

        # Vivado 中已将 AXI DMA 的 Buffer Length Register Width 设为 23bit，
        # 单次传输上限 8MB，整帧可一次发完，无需拆块（拆块会因 TLAST 冲突死锁）。
        self.ip = overlay.skin_morph_0
        self.dma = overlay.axi_dma_0
        self.in_buf = pynq.allocate(shape=(self.npix_max,), dtype=np.uint32)
        self.out_buf = pynq.allocate(shape=(self.npix_max,), dtype=np.uint32)
        # 打包用的临时视图：先整块拷贝 BGR，再按 32bit 解释，避免逐像素 strided 写
        self._in_bytes = self.in_buf.view(np.uint8).reshape(-1, 4)

        self.cur_rows = self.cur_cols = -1
        self._set_thresh(cr_lo, cr_hi, cb_lo, cb_hi)

    def _set_thresh(self, cr_lo, cr_hi, cb_lo, cb_hi):
        self.ip.write(ADDR_CR_LO, int(cr_lo))
        self.ip.write(ADDR_CR_HI, int(cr_hi))
        self.ip.write(ADDR_CB_LO, int(cb_lo))
        self.ip.write(ADDR_CB_HI, int(cb_hi))

    @staticmethod
    def gray_world(frame):
        """与 PS 端 HandSeg.gray_world 等价（1/4 采样 + LUT）。"""
        sm = frame[::4, ::4].reshape(-1, 3).astype(np.float32)
        means = sm.mean(axis=0)
        gain = means.mean() / (means + 1e-6)
        lut = [np.clip(np.arange(256, dtype=np.float32) * g, 0, 255).astype(np.uint8)
               for g in gain]
        return cv2.merge([cv2.LUT(c, l) for c, l in zip(cv2.split(frame), lut)])

    def _white_balance(self, frame):
        """Apply a bounded fraction of gray-world correction."""
        if self.wb_strength <= 0.0:
            return frame
        sm = frame[::4, ::4].reshape(-1, 3).astype(np.float32)
        means = sm.mean(axis=0)
        target = means.mean() / (means + 1e-6)
        gain = 1.0 + self.wb_strength * (target - 1.0)
        # Partial WB must not amplify a dark background into the skin range.
        gain = np.clip(gain, 0.75, 1.25)
        lut = [np.clip(np.arange(256, dtype=np.float32) * g, 0, 255).astype(np.uint8)
               for g in gain]
        return cv2.merge([cv2.LUT(c, l) for c, l in zip(cv2.split(frame), lut)])

    def _run_pl(self, bgr):
        """把一帧送进 PL，返回二值 mask (uint8)。"""
        rows, cols = bgr.shape[:2]
        npix = rows * cols

        # 1) BGR24 -> 32bit/像素（低 24 位 BGR）
        flat = bgr.reshape(-1, 3)
        self._in_bytes[:npix, 0] = flat[:, 0]
        self._in_bytes[:npix, 1] = flat[:, 1]
        self._in_bytes[:npix, 2] = flat[:, 2]
        # 第 4 字节保持 0（初始化时已清零；复用时旧的 0 不会被覆盖）

        # 2) 尺寸变化时重新配置（ROI 尺寸会变）
        if rows != self.cur_rows or cols != self.cur_cols:
            self.ip.write(ADDR_ROWS, int(rows))
            self.ip.write(ADDR_COLS, int(cols))
            self.cur_rows, self.cur_cols = rows, cols

        # 3) 先启动 IP（流式，否则 DMA 会被背压），然后整帧一次传输。
        # 注意顺序：必须先挂接收再发发送，否则 IP 输出背压会卡住发送部分。
        self.ip.write(ADDR_CTRL, AP_START)
        self.dma.recvchannel.transfer(self.out_buf, nbytes=npix * 4)
        self.dma.sendchannel.transfer(self.in_buf, nbytes=npix * 4)
        self.dma.sendchannel.wait()
        self.dma.recvchannel.wait()

        # 4) 取低字节（小端：每个 32bit 字的第 0 字节即有效 mask）
        return self.out_buf.view(np.uint8).reshape(-1, 4)[:npix, 0].reshape(rows, cols)

    def __call__(self, frame, roi=None):
        h, w = frame.shape[:2]
        if roi is None:
            x0, y0, x1, y1 = 0, 0, w, h
        else:
            x0, y0, x1, y1 = roi
        sub = frame[y0:y1, x0:x1]

        f = self._white_balance(sub)
        mask = self._run_pl(f)

        if roi is not None:                 # 贴回全尺寸，便于直接可视化
            full = np.zeros((h, w), np.uint8)
            full[y0:y1, x0:x1] = mask
            mask = full

        res = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = res[0] if len(res) == 2 else res[1]
        if not cnts:
            return None, mask
        cnt = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        # 面积比例始终按全图算（与 PS 端一致，避免把整条手臂当成手）
        if area < self.min_ratio * w * h or area > self.max_ratio * w * h:
            return None, mask
        if roi is not None:
            cnt = (cnt + np.array([x0, y0], np.int32)).astype(np.int32)
        return cnt, mask
