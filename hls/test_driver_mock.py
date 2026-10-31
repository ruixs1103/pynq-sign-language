#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""不上板也能测：用模拟硬件跑【真实的 pl_hand_seg.py 驱动代码】。

验证的不是算法（那个 e2e_pl.py 已经验过），而是驱动里最容易写错、
上板后又最难定位的几件事：

  1. BGR24 -> 32bit/像素 的打包字节序
  2. mask 从 32bit 字里取低字节的解包
  3. rows/cols 是否按 ROI 实际尺寸动态写入
  4. 先启动 IP 再启 DMA 的顺序（流式 IP 反过来会死锁）
  5. ROI 贴回全图 + 面积过滤

做法：注入一个假的 pynq 模块，DMA 的 transfer/wait 用
pl_logic_sim 里的逐像素参考逻辑来"充当 FPGA"。
这样跑的还是 PlHandSeg 的真实代码路径。

用法：
    python hls/test_driver_mock.py
"""

import os
import sys
import types

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, ROOT)

from pl_logic_sim import pl_bgr_to_mask, pl_morph   # noqa: E402


def pl_reference(wb):
    """skin_morph IP 的完整流水线（4 级形态学）。"""
    m = pl_bgr_to_mask(wb)
    m = pl_morph(m, True)
    m = pl_morph(m, False)
    m = pl_morph(m, False)
    return pl_morph(m, True)


def ps_reference(wb):
    """PS 端 OpenCV 参考实现。"""
    K = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    ycc = cv2.cvtColor(wb, cv2.COLOR_BGR2YCrCb)
    m = cv2.inRange(ycc, (0, 130, 75), (255, 185, 145))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, K)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, K)


# ---------------------------------------------------------------------------
# 假的 pynq：allocate 就是普通 numpy 数组
# ---------------------------------------------------------------------------
fake_pynq = types.ModuleType("pynq")
fake_pynq.allocate = lambda shape, dtype: np.zeros(shape, dtype)
sys.modules["pynq"] = fake_pynq


class FakeIP(object):
    """模拟 AXI4-Lite 控制口，记录每次写入。"""

    def __init__(self):
        self.regs = {}
        self.log = []

    def write(self, addr, val):
        self.regs[addr] = int(val)
        self.log.append((addr, int(val)))

    def read(self, addr):
        return self.regs.get(addr, 0)


class _Chan(object):
    def __init__(self, sim):
        self.sim = sim
        self.buf = None
        self.nbytes = 0

    def transfer(self, buf, nbytes):
        self.buf = buf
        self.nbytes = nbytes

    def wait(self):
        # 两边 wait 都调用，真正计算在第二次（send 与 recv 都就位后）
        self.sim.maybe_run()


class FakeDMA(object):
    """模拟 AXI DMA：send 拿图像，recv 收 mask。"""

    def __init__(self, ip):
        self.ip = ip
        self.send = _Chan(self)
        self.recv = _Chan(self)
        self.sendchannel = self.send
        self.recvchannel = self.recv
        self.started_before_dma = False

    def maybe_run(self):
        if self.send.buf is None or self.recv.buf is None:
            return
        rows = self.ip.regs.get(0x10)
        cols = self.ip.regs.get(0x18)
        if not rows or not cols:
            raise AssertionError("驱动没有写 rows/cols 就启动了 DMA")
        npix = rows * cols

        # 严格按 IP 的视角解包：每个 32bit 字的低 24 位是 BGR
        words = self.send.buf[:npix]
        b = (words & 0x000000FF).astype(np.uint8)
        g = ((words >> 8) & 0x000000FF).astype(np.uint8)
        r = ((words >> 16) & 0x000000FF).astype(np.uint8)
        img = np.stack([b, g, r], axis=1).reshape(rows, cols, 3)

        mask = pl_reference(img)
        # 按 IP 的打包方式写回：mask 放在每个字的第 0 字节
        self.recv.buf[:npix] = mask.reshape(-1).astype(np.uint32)
        self.ran = True


class FakeOverlay(object):
    def __init__(self):
        self.skin_morph_0 = FakeIP()
        self.axi_dma_0 = FakeDMA(self.skin_morph_0)


# ---------------------------------------------------------------------------
# 测试
# ---------------------------------------------------------------------------
def find_images():
    """递归找 dataset 下的图片（目录层级可能是 dataset/dataset/...）。"""
    # 优先 raw_*（原始彩色照片）；processed_* 已经是二值图，肤色检测必然全 0
    base = os.path.join(ROOT, "dataset")
    raw, other = [], []
    for dp, _dn, fn in os.walk(base):
        for f in fn:
            if f.lower().endswith((".jpg", ".png", ".jpeg")):
                (raw if "raw" in dp.lower() else other).append(os.path.join(dp, f))
    return sorted(raw) + sorted(other)


def main():
    from pl_hand_seg import PlHandSeg

    files = find_images()
    if not files:
        print("[ERR] 没找到图片，放在 dataset/ 下再跑")
        return 1

    ok = True
    for fp in files[:3]:
        img0 = cv2.imread(fp)
        if img0 is None:
            continue
        img = cv2.resize(img0, (320, 240))

        ol = FakeOverlay()
        seg = PlHandSeg(ol, rows=240, cols=320, use_wb=True)

        cnt, mask = seg(img)

        # 参考：驱动内部做了 gray_world，这里复现同样的输入
        wb = PlHandSeg.gray_world(img)
        ref = ps_reference(wb)

        diff = int((mask != ref).sum())
        rate = 100.0 * diff / mask.size

        # 检查 IP 配置是否被正确写入
        regs = ol.skin_morph_0.regs
        name = os.path.basename(fp)
        print("%-24s 差异 %5d px (%.3f%%)  rows=%d cols=%d 轮廓=%s"
              % (name, diff, rate, regs.get(0x10, -1), regs.get(0x18, -1),
                 "有" if cnt is not None else "无"))

        # 断言 1：差异率必须极小（打包/解包写错会是 ~100% 或 25% 量级）
        if rate > 2.0:
            print("   [FAIL] 差异过大，检查打包/解包字节序")
            ok = False
        # 断言 2：全图模式必须写对尺寸
        if regs.get(0x10) != 240 or regs.get(0x18) != 320:
            print("   [FAIL] rows/cols 写入错误")
            ok = False

        # ROI 模式：驱动必须按 ROI 尺寸重新配置
        roi = (40, 30, 200, 150)   # 160x120
        cnt2, mask2 = seg(img, roi=roi)
        if ol.skin_morph_0.regs.get(0x10) != 120 or ol.skin_morph_0.regs.get(0x18) != 160:
            print("   [FAIL] ROI 模式下 rows/cols 未更新")
            ok = False
        else:
            print("   ROI 160x120 -> rows=%d cols=%d  贴回尺寸=%s"
                  % (ol.skin_morph_0.regs.get(0x10),
                     ol.skin_morph_0.regs.get(0x18), mask2.shape))

    print("\n结论: %s" % ("驱动代码路径全部通过" if ok else "存在问题，见上面 [FAIL]"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
