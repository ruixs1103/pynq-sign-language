#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PYNQ-Z2 + Logitech C270 手语识别 demo
  静态：1 / 2 / 3 / 4 / 5 / 未知
  动态：你好 / 谢谢 / 再见 / 帮助 / 未知

算法流程沿用参考作品（ZYNQ 手势识别）的逻辑，在 PS 端用 OpenCV 等价实现：
  YCrCb 肤色分割(Cb-Cr 双阈值) -> 形态学开/闭运算 -> 最大连通域 -> 轮廓特征
  -> 特征向量 + 最小二范数(最近邻)匹配 -> 距离超阈值判"未知"
动态部分是把静态的"特征向量 L2"扩展到时序：轨迹 + DTW(时序上的对齐 L2)。

用法:
  # 0) 先锁定摄像头自动曝光/白平衡（关键！否则肤色阈值逐帧漂移）
  v4l2-ctl -d /dev/video0 -c exposure_auto=1 -c exposure_absolute=150
  v4l2-ctl -d /dev/video0 -c white_balance_temperature_auto=0 -c white_balance_temperature=4000

  # 先查清摄像头真正支持哪些分辨率/帧率组合（决定后面参数怎么填）
  v4l2-ctl -d /dev/video0 --list-formats-ext

  # 1) 模板都在 PC 上离线生成（evaluate_features.py -> sign_templates.json），
  #    与本脚本放同一目录即可，无需在板上标定。
  #    新增手势：在数据集下建 number_X 目录(如 number_6=点赞)后重跑 evaluate_features.py

  # 2) 运行识别
  python3 pynq_sign_language.py --mode static
  python3 pynq_sign_language.py --mode transition

改采集参数（都会打印"请求 -> 实际"，以实际值为准）:
  # 分辨率 + 目标帧率
  python3 pynq_sign_language.py --mode static --width 640 --height 480 --fps 30
  # 卡顿时降分辨率或换未压缩格式
  python3 pynq_sign_language.py --mode static --width 320 --height 240 --fps 60
  python3 pynq_sign_language.py --mode static --width 640 --height 480 --fourcc YUYV
  # 降低处理量（每 2 帧算 1 帧），采集帧率不变、处理帧率减半
  python3 pynq_sign_language.py --mode static --skip 1

依赖: python3 + opencv(python) + numpy，PYNQ 2.6/3.0 镜像自带。
"""
import argparse
import json
import os
import sys
import time

import cv2
import numpy as np

TPL_PATH = "sign_templates.json"

# 静态手势标签。evaluate_features.py 会从数据集目录 number_X 自动发现类别，
# 因此新增第 6/7 类只需在数据集下建 number_6 / number_7 并重训模板，无需改代码。
STATIC_LABELS = ["1", "2", "3", "4", "5", "6", "7"]
UNKNOWN = "未知"

# 显示名：6=点赞(竖起拇指)，7=停止(一手食指顶住另一手掌心)
GESTURE_NAMES = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
                 "6": "点赞", "7": "停止"}


def gname(lab):
    """模板标签 -> 中文显示名。"""
    if lab is None:
        return "无"
    if lab == UNKNOWN:
        return UNKNOWN
    return GESTURE_NAMES.get(lab, lab)


# ----------------------------------------------------------------------------
# 1. 采集与分割：对应 PL 的 YCbCr 肤色阈值 + 形态学 + 最大连通域
# ----------------------------------------------------------------------------
class HandSeg(object):
    def __init__(self, min_area_ratio=0.02, max_area_ratio=0.55, k=5, use_wb=True):
        self.kern = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        self.min_ratio = min_area_ratio
        self.max_ratio = max_area_ratio
        self.use_wb = use_wb      # 已在 v4l2 层锁定白平衡时可关掉，省一整步
        # 参考作品原始阈值(Cb 77-127/Cr 133-173)过窄：实测对不同白平衡域
        # (静态图 Cb≈110-128 / 动态视频 Cb≈126-142) 会在其中一个域失效。
        # 加宽到 Cr 130-185 / Cb 75-145，两个域均验证可完整分割手部，
        # 灰白背景(Cr<130)仍被排除。板端若漂移可经 AXI-Lite/参数再调。
        self.lo = np.array([0, 130, 75], np.uint8)
        self.hi = np.array([255, 185, 145], np.uint8)
        # ROI 模式下的面积占 ROI 的上下限（ROI 里手占比会很高，不能用全图的比例）
        self.roi_min, self.roi_max = 0.04, 0.95
        self._gain = None            # 缓存的白平衡增益

    @staticmethod
    def calc_gain(frame):
        """灰度世界增益：按 1/4 采样估算（增益是整幅图的全局量）。"""
        sm = frame[::4, ::4].reshape(-1, 3).astype(np.float32)
        means = sm.mean(axis=0)
        return means.mean() / (means + 1e-6)

    @staticmethod
    def gray_world(frame):
        """灰度世界白平衡，抑制自动白平衡带来的肤色漂移。

        两处针对 ARM 的优化（原实现在 A9 上是单帧最贵的一步）：
        1) 通道均值按 1/4 采样估算——增益是整幅图的全局量，不需要逐像素精度
        2) 用 256 项 LUT 做 8bit 查表，代替全图 float32 乘法
        """
        sm = frame[::4, ::4].reshape(-1, 3).astype(np.float32)
        means = sm.mean(axis=0)
        gain = HandSeg.calc_gain(frame)
        lut = [np.clip(np.arange(256, dtype=np.float32) * g, 0, 255).astype(np.uint8)
               for g in gain]
        return cv2.merge([cv2.LUT(c, l) for c, l in zip(cv2.split(frame), lut)])

    def _wb(self, sub, is_roi):
        """白平衡。ROI 帧复用缓存的全图增益：ROI 内几乎只有手，
        在其上统计均值会把肤色当成"灰色基准"，反而把肤色拉向灰、破坏分割。"""
        if not self.use_wb:
            return sub
        if not is_roi:
            self._gain = self.calc_gain(sub)
        if self._gain is None:
            return sub
        lut = [np.clip(np.arange(256, dtype=np.float32) * g, 0, 255).astype(np.uint8)
               for g in self._gain]
        return cv2.merge([cv2.LUT(c, l) for c, l in zip(cv2.split(sub), lut)])

    def __call__(self, frame, roi=None):
        """roi=(x0,y0,x1,y1) 时只处理该区域；轮廓坐标自动偏移回全图坐标。"""
        h, w = frame.shape[:2]
        if roi is None:
            x0, y0, x1, y1 = 0, 0, w, h
        else:
            x0, y0, x1, y1 = roi
        sub = frame[y0:y1, x0:x1]
        base = float((x1 - x0) * (y1 - y0))

        f = self._wb(sub, roi is not None)
        ycc = cv2.cvtColor(f, cv2.COLOR_BGR2YCrCb)
        mask = cv2.inRange(ycc, self.lo, self.hi)
        # 开运算：腐蚀->膨胀，去孤立噪点；闭运算：膨胀->腐蚀，补手部空洞
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self.kern)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self.kern)

        res = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = res[0] if len(res) == 2 else res[1]
        if roi is not None:                 # 贴回全尺寸，便于直接可视化
            full = np.zeros((h, w), np.uint8)
            full[y0:y1, x0:x1] = mask
            mask = full
        if not cnts:
            return None, mask
        cnt = max(cnts, key=cv2.contourArea)
        area = cv2.contourArea(cnt)
        # 面积过滤：太小是噪声，太大通常是脸/背景。
        # 比例必须按"全图面积"算而不是 ROI 面积——按 ROI 算会过松，
        # 实测会让约 10% 的帧把整条手臂当成手（质心跳变 200+ 像素）。
        if area < self.min_ratio * w * h or area > self.max_ratio * w * h:
            return None, mask
        if roi is not None:
            cnt = (cnt + np.array([x0, y0], np.int32)).astype(np.int32)
        return cnt, mask


def make_seg(args, rows, cols):
    """按参数创建分割器：--use-pl 时用 PL 加速版，否则纯 PS（PC 上也能跑）。"""
    if not getattr(args, "use_pl", False):
        return HandSeg(k=args.morph, use_wb=not args.no_wb)
    import pynq                              # 只在板上可用
    from pl_hand_seg import PlHandSeg
    print("[PL] 加载 overlay: %s" % args.bit)
    ol = pynq.Overlay(args.bit)
    print("[PL] IP: %s  DMA: %s" % (
        [k for k in ol.ip_dict if "skin_morph" in k],
        [k for k in ol.ip_dict if "axi_dma" in k]))
    return PlHandSeg(ol, rows=rows, cols=cols, use_wb=not args.no_wb)


class RoiTracker(object):
    """ROI 跟踪：相邻帧之间手只移动一小段，因此只需处理上一帧手部附近的区域。

    ROI 通常只占全图的 1/4 ~ 1/9，分割+形态学的耗时近似同步下降。
    连续跟丢 miss_max 帧或每 refresh 帧会强制做一次全图，用来刷新
    白平衡增益并防止手移出 ROI 后永久跟丢。
    """
    def __init__(self, margin=60, min_side=200, miss_max=4, refresh=20):
        self.margin, self.min_side = margin, min_side
        self.miss_max, self.refresh = miss_max, refresh
        self.roi = None
        self.miss = 0
        self.age = 0

    def next(self, cnt, shape):
        """帧处理完后调用，返回下一帧应使用的 ROI（None = 全图）。"""
        h, w = shape[:2]
        self.age += 1
        if cnt is None:
            self.miss += 1
            if self.miss >= self.miss_max:
                self.roi, self.miss, self.age = None, 0, 0
            return self.roi
        self.miss = 0
        x, y, bw, bh = cv2.boundingRect(cnt)
        x0, y0 = max(0, x - self.margin), max(0, y - self.margin)
        x1, y1 = min(w, x + bw + self.margin), min(h, y + bh + self.margin)
        if x1 - x0 < self.min_side:          # ROI 太小容易把手贴边截断
            pad = (self.min_side - (x1 - x0)) // 2
            x0, x1 = max(0, x0 - pad), min(w, x1 + pad)
        if y1 - y0 < self.min_side:
            pad = (self.min_side - (y1 - y0)) // 2
            y0, y1 = max(0, y0 - pad), min(h, y1 + pad)
        if self.age >= self.refresh:         # 定期全图：刷新增益 + 防跟丢
            self.roi, self.age = None, 0
        else:
            self.roi = (x0, y0, x1, y1)
        return self.roi


# ----------------------------------------------------------------------------
# 2. 特征提取：Hu 不变矩(log) + 指尖数 + 紧凑度 + 质心/面积
# ----------------------------------------------------------------------------
def hu_log(cnt):
    """Hu 矩必须 log10 后再用：原始量级 1e-3 ~ 1e-7，直接算 L2 会被第一项主导。"""
    m = cv2.moments(cnt)
    if m["m00"] <= 0:
        return None
    hu = cv2.HuMoments(m).flatten()
    return -np.sign(hu) * np.log10(np.abs(hu) + 1e-9)


def resample_cnt(cnt, n=64):
    """按弧长把轮廓均匀重采样到固定点数，指尖检测才稳定。"""
    pts = cnt[:, 0, :].astype(np.float32)
    # 弧长参数化：闭合环，xp 与 fp 必须同为 n+1（首尾点重复）
    d = np.linalg.norm(np.diff(np.vstack([pts, pts[:1]]), axis=0), axis=1)
    xp = np.concatenate([[0.0], np.cumsum(d)])
    fpx = np.append(pts[:, 0], pts[0, 0])
    fpy = np.append(pts[:, 1], pts[0, 1])
    if xp[-1] <= 0:
        return None
    ts = np.linspace(0.0, xp[-1], n, endpoint=False)
    x = np.interp(ts, xp, fpx)
    y = np.interp(ts, xp, fpy)
    return np.stack([x, y], axis=1)


def count_fingertips(cnt, cos_thr=0.55, min_dist_ratio=0.55):
    # cos_thr/min_dist_ratio 由 tune_fingertips.py 网格搜索确定：
    # 默认 0.25 会让 2/3/5 的中位指尖数各多算 1 个（实测 median=3/4/6），
    # 0.55 时 1-5 的中位数恰好为 1/2/3/4/5。
    """k-circumference 指尖检测（向量化，禁止 Python for 循环扫点）。"""
    p = resample_cnt(cnt, 64)
    if p is None:
        return 0, []
    n = len(p)
    k = max(4, n // 12)
    centroid = p.mean(axis=0)
    d_c = np.linalg.norm(p - centroid, axis=1)
    dmax = d_c.max() + 1e-6

    p_prev = np.roll(p, k, axis=0)
    p_next = np.roll(p, -k, axis=0)
    v1, v2 = p_prev - p, p_next - p
    n1 = np.linalg.norm(v1, axis=1) + 1e-6
    n2 = np.linalg.norm(v2, axis=1) + 1e-6
    cos = np.sum(v1 * v2, axis=1) / (n1 * n2)

    # 夹角小(cos 大) 且 离质心足够远(排除手腕处的伪指尖)
    cand = np.where((cos > cos_thr) & (d_c > min_dist_ratio * dmax))[0]
    if len(cand) == 0:
        return 0, []

    # 环形非极大抑制：相邻(环距 < k)候选只保留 cos 最大的
    cand = cand[np.argsort(-cos[cand])]
    keep = []
    for i in cand:
        ok = True
        for j in keep:
            dist = abs(i - j)
            dist = min(dist, n - dist)
            if dist < k:
                ok = False
                break
        if ok:
            keep.append(i)
    return len(keep), [tuple(p[i].astype(int)) for i in keep]


def geo_features(cnt):
    """量纲相近的几何特征（比 Hu 矩稳定得多，旋转不敏感、尺度归一化）。
    返回 [fingers, solidity, compactness, aspect, extent, n_defects]"""
    area = float(cv2.contourArea(cnt))
    perim = float(cv2.arcLength(cnt, True))
    if area <= 0 or perim <= 0:
        return None
    hull = cv2.convexHull(cnt)
    hull_area = float(cv2.contourArea(hull))
    x, y, w, h = cv2.boundingRect(cnt)
    bbox_area = float(w * h)

    solidity = area / (hull_area + 1e-6)                  # 凹凸程度
    compactness = perim * perim / (4.0 * np.pi * area)    # 圆=1，越复杂越大
    aspect = float(w) / float(h + 1e-6)
    extent = area / (bbox_area + 1e-6)

    # 凸包缺陷数（指缝数），深度+角度双过滤
    n_def = 0
    try:
        hi = cv2.convexHull(cnt, returnPoints=False)
        if len(hi) > 3:
            defs = cv2.convexityDefects(cnt, hi)
            if defs is not None:
                # OpenCV 版本间返回形状可能为 (N,1,4) / (N,4)，统一整形
                defs = np.asarray(defs).reshape(-1, 4)
                depth_thr = 0.015 * np.sqrt(area)
                for s, e, f, depth in defs:
                    if float(depth) / 256.0 > depth_thr:
                        n_def += 1
    except cv2.error:
        pass

    fingers = count_fingertips(cnt)[0]
    return np.array([fingers, solidity, compactness, aspect, extent, n_def], np.float32)


def fourier_descriptors(cnt, n=128, k=8):
    """傅立叶描述子：对平移/尺度/旋转/起点均不变，形状区分度远高于 Hu 矩。"""
    p = resample_cnt(cnt, n)
    if p is None:
        return None
    z = p[:, 0] + 1j * p[:, 1]
    Z = np.fft.fft(z)
    mag = np.abs(Z[1:k + 1])
    if mag[0] < 1e-9:
        return None
    return (mag / mag[0]).astype(np.float32)   # 除以基波 -> 尺度不变；幅值 -> 旋转不变


def centroid_profile(cnt, n=128, k=16):
    """质心距离剖面：轮廓点到质心的径向距离序列的 FFT 幅值。
    对指尖数量/凹凸极其敏感，且平移(去中心)/尺度(除均值)/旋转与起点(取幅值)均不变。"""
    p = resample_cnt(cnt, n)
    if p is None:
        return None
    c = p.mean(axis=0)
    d = np.linalg.norm(p - c, axis=1)
    m = float(d.mean())
    if m < 1e-6:
        return None
    d = d / m
    D = np.abs(np.fft.fft(d))[1:k + 1]
    if D[0] < 1e-9:
        return None
    return (D / D[0]).astype(np.float32)


def feature_vec(cnt, mode="combo"):
    """mode: hu(原视频逻辑) / geo / fd / fd16 / cdf / combo / combo2"""
    if mode == "hu":
        return hu_log(cnt)
    if mode == "geo":
        return geo_features(cnt)
    if mode == "fd":
        return fourier_descriptors(cnt, k=8)
    if mode == "fd16":
        return fourier_descriptors(cnt, k=16)
    if mode == "cdf":
        return centroid_profile(cnt, k=16)
    if mode == "cdf24":
        return centroid_profile(cnt, k=24)
    if mode == "fdcdf":
        f, c = fourier_descriptors(cnt, k=8), centroid_profile(cnt, k=16)
        if f is None or c is None:
            return None
        return np.concatenate([f, c])
    if mode == "cdf24f":                      # cdf24 + 指尖数（重复 3 次以提高权重）
        c = centroid_profile(cnt, k=24)
        if c is None:
            return None
        fg = np.array([count_fingertips(cnt)[0]], np.float32)
        return np.concatenate([np.repeat(fg, 3), c])
    if mode == "geocdf":
        g, c = geo_features(cnt), centroid_profile(cnt, k=16)
        if g is None or c is None:
            return None
        return np.concatenate([g, c])
    if mode == "combo":
        g, f = geo_features(cnt), fourier_descriptors(cnt, k=8)
        if g is None or f is None:
            return None
        return np.concatenate([g, f])
    if mode == "combo2":
        g, f, c = geo_features(cnt), fourier_descriptors(cnt, k=8), centroid_profile(cnt)
        if g is None or f is None or c is None:
            return None
        return np.concatenate([g, f, c])
    raise ValueError("unknown mode " + mode)


def centroid_xy(cnt):
    m = cv2.moments(cnt)
    if m["m00"] <= 0:
        return None, 0.0
    return (m["m10"] / m["m00"], m["m01"] / m["m00"]), m["m00"]


# ---- 动态轨迹的每帧特征 -----------------------------------------------------
# 早期版本只用 (cx, cy, area)：丢弃了手的形状，导致四类手势归一化后轨迹
# 高度重合（类间最小距离 0.072 < 类内平均 0.126~0.296），离线准确率仅 18.5%。
# 加上指尖数通道后，"手随时间怎样变形"被保留下来，与静态路径一样有判别力。
NF_SCALE = 2.5        # 指尖数 0~5 -> (nf-2.5)/2.5 ∈ [-1,1]，与 xy/z 同一量级
DYN_FD_MODE = "fdcdf"  # 动态逐帧形状特征，与静态模板的 meta.mode 保持一致


def traj_feat(cnt, mode=DYN_FD_MODE, with_fd=True):
    """动态轨迹的一帧原始特征：[cx, cy, area, 指尖数] (+ FD...)。

    with_fd=True 时逐帧拼上 FD/CDF 形状特征。实测该通道在本数据集上没有
    带来判别力（留出准确率 28.4%，低于不带形状通道的 33.3%），默认仍在，
    可通过 meta['dyn_fd_w'] = 0 关闭以省掉每帧 FFT 开销。
    """
    c, area = centroid_xy(cnt)
    if c is None:
        return None
    nf = float(count_fingertips(cnt)[0])
    row = [c[0], c[1], area, nf]
    if not with_fd:
        return row
    f = feature_vec(cnt, mode)
    if f is None:
        return None
    return row + list(np.asarray(f, np.float32))


def active_mask(dots, act_ratio=0.25):
    """返回"在动"的帧掩码（速度 >= 25% 最大速度 的首尾之间）。
    用于把视频裁到真正的动作段，再交给归一化。"""
    dots = np.asarray(dots, np.float32)
    if len(dots) < 6:
        return np.ones(len(dots), bool)
    sp = np.linalg.norm(np.diff(dots, axis=0), axis=1)
    if sp.max() < 1e-3:
        return np.ones(len(dots), bool)
    idx = np.where(sp > act_ratio * sp.max())[0]
    if len(idx) == 0:
        return np.ones(len(dots), bool)
    m = np.zeros(len(dots), bool)
    m[int(idx[0]):int(idx[-1]) + 1] = True
    return m


def _median_smooth(a, win):
    """沿时间轴做中值滤波，抑制质心抖动。小幅手势的信噪比提升明显。"""
    if win is None or win <= 1 or len(a) < win:
        return a
    pad = win // 2
    b = np.pad(a, ((pad, pad), (0, 0)), mode="edge")
    return np.asarray([np.median(b[i:i + win], axis=0) for i in range(len(a))],
                      np.float32)


def dist_to_protos(q, protos, cyclic=True):
    """到一组原型轨迹的最小 DTW。

    cyclic=True 时对查询轨迹做循环移位对齐，消除往复动作的起点相位差
    （从左挥和从右挥等价）。离线标定、评估与板端必须共用这一实现，
    否则阈值和判决距离不同源，板上表现会和离线评估对不上。
    """
    q = np.asarray(q, np.float32)
    protos = np.asarray(protos, np.float32)
    shifts = range(0, len(q), 2) if cyclic else [0]
    best = 1e9
    for s in shifts:
        qs = np.roll(q, s, axis=0)
        for p in protos:
            d = dtw(qs, p)
            if d < best:
                best = d
    return float(best)


def norm_seq_dyn(seq, L=16, act_ratio=0.25, mu=None, sd=None, fd_w=1.0,
                 smooth=0):
    """traj_feat 序列 -> (L, 4+D) 归一化：
    前 3 通道做 segmentation 级的平移/尺度/面积归一化，
    第 4 通道是指尖数，其后 FD 特征用静态的 mu/sd 做 z-score。"""
    a = _median_smooth(np.asarray(seq, np.float32), smooth)
    if len(a) < 4:
        return None
    sp = np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1)
    if sp.max() < 1e-3:
        return None
    act = sp > act_ratio * sp.max()
    idx = np.where(act)[0]
    i0 = max(0, int(idx[0]) - 2)
    i1 = min(len(a) - 1, int(idx[-1]) + 3)
    if i1 - i0 < 4:
        return None
    s = a[i0:i1 + 1]

    xy = s[:, :2].copy()
    xy -= xy.mean(axis=0)
    diag = np.linalg.norm(xy.max(axis=0) - xy.min(axis=0))
    if diag < 1e-3:
        return None
    xy /= diag
    ar = s[:, 2] / (float(np.median(s[:, 2])) + 1e-6)
    nf = (s[:, 3] - NF_SCALE) / NF_SCALE

    ts = np.linspace(0, len(s) - 1, L)
    idx2 = np.arange(len(s))
    cols = [np.interp(ts, idx2, xy[:, 0]),
            np.interp(ts, idx2, xy[:, 1]),
            np.interp(ts, idx2, ar),
            np.interp(ts, idx2, nf)]
    if a.shape[1] > 4:
        F = s[:, 4:]
        if mu is not None and sd is not None:
            F = (F - np.asarray(mu, np.float32)) / np.asarray(sd, np.float32)
        F = F * float(fd_w)
        for j in range(F.shape[1]):
            cols.append(np.interp(ts, idx2, F[:, j]))
    return np.stack(cols, axis=1)


# ----------------------------------------------------------------------------
# 3. 静态识别：特征向量 + 最小二范数最近邻
# ----------------------------------------------------------------------------
class StaticRecognizer(object):
    """静态识别：特征向量 + 最小二范数最近邻 + 每类自适应拒绝阈值。

    templates: {label: 特征向量(list)}
    meta     : 由 evaluate_features.py 生成，含
               mode(特征类型) / mu,sd(z-score 参数) / cls_thr(每类拒绝阈值)
    没有模板时退回"指尖数规则"，仍可演示 1-5。
    """
    def __init__(self, templates, meta=None):
        meta = meta or {}
        self.mode = meta.get("mode", "cdf24")
        # v 可以是单个向量(D,) 或多个原型(P,D)；统一成 (P,D)
        self.tpl = {}
        for k, v in (templates or {}).items():
            a = np.asarray(v, np.float32)
            self.tpl[k] = a.reshape(1, -1) if a.ndim == 1 else a
        self.cls_thr = meta.get("cls_thr", {})
        self.default_thr = float(meta.get("thresh", 1.5))
        self.mu = np.asarray(meta["mu"], np.float32) if "mu" in meta else None
        self.sd = np.asarray(meta["sd"], np.float32) if "sd" in meta else None

    def predict(self, cnt):
        nf, tips = count_fingertips(cnt)
        # 停止(7=握拳)用"0 指尖"判定：握拳与 1/6(拳头+手指)形状太接近，
        # 形状模板分不开，但指尖数 0 与所有数字(1~5 指尖)天然区分。
        if nf == 0 and "7" in self.tpl:
            return "7", 0.0, nf, tips
        if not self.tpl:
            return (str(nf) if 1 <= nf <= 5 else UNKNOWN), 0.0, nf, tips

        v = feature_vec(cnt, self.mode)
        if v is None:
            return UNKNOWN, 9.9, nf, tips
        z = (v - self.mu) / self.sd if self.mu is not None else v

        best, bd = None, 1e9
        for lab, t in self.tpl.items():          # 多原型时取到该类最近原型的距离
            if lab == "7":
                continue                          # 7 只由"0 指尖"判定，不参与形状最近邻
            d = float(np.linalg.norm(t - z[None, :], axis=1).min())
            if d < bd:
                bd, best = d, lab
        thr = float(self.cls_thr.get(best, self.default_thr))
        if bd > thr:
            return UNKNOWN, bd, nf, tips
        return best, bd, nf, tips


# ----------------------------------------------------------------------------
# 3b. 手势跃迁识别：静态识别 + 滑动窗口投票 + 状态机
# ----------------------------------------------------------------------------
class TransitionRecognizer(object):
    """识别"从一个静态手势切换到另一个"，例如 1 -> 2。

    思路：动态我们不比运动轨迹，而是复用已经很稳的静态识别，
    只在时间维上做两层稳定化，把可靠的 AO 变化抽出来：

      1) 滑动窗口多数投票 —— 滤掉单帧抖动和误判
      2) 状态机 —— 新手势必须连续保持 hold 帧才被确认，
         确认时才与上一个已确认状态比较，相同则不算跃迁

    与类别数无关：静态模板扩到几类，它就支持几类之间的任意跃迁。

    feed() 返回 (event, state)：
      event: 本次产生的跃迁，形如 ("1", "2")；没有则为 None
      state: 当前处于的稳定手势（None 表示还没有）
    """
    def __init__(self, static_rec, win=7, need=5, hold=4, max_miss=30):
        self.rec = static_rec
        self.win = win          # 投票窗口长度(帧)
        self.need = need        # 窗口内至少多少票才算数
        self.hold = hold        # 新候选需连续保持的帧数
        self.max_miss = max_miss  # 连续多少帧看不见手才复位到"无手势"
        self.buf = []
        self.state = None       # 已确认手势
        self.cand = None        # 候选新状态
        self.cand_n = 0
        self.miss = 0
        self.history = []       # 全部跃迁记录

    def reset(self):
        self.buf, self.state, self.cand = [], None, None
        self.cand_n, self.miss = 0, 0

    def _vote(self):
        """窗口多数投票，票数不足则返回 None。"""
        vals = [x for x in self.buf if x is not None]
        if not vals:
            return None
        best, bn = None, 0
        for v in set(vals):
            c = vals.count(v)
            if c > bn:
                bn, best = c, v
        return best if bn >= self.need else None

    def feed(self, cnt):
        if cnt is None:
            lab = None
        else:
            lab = self.rec.predict(cnt)[0]
            if lab == UNKNOWN:
                lab = None

        self.buf.append(lab)
        if len(self.buf) > self.win:
            self.buf.pop(0)

        if lab is None:
            self.miss += 1
            if self.miss >= self.max_miss:
                self.state, self.cand, self.cand_n = None, None, 0
        else:
            self.miss = 0

        m = self._vote()
        if m is None:
            return None, self.state

        if m == self.state:                 # 状态没变，清掉候选
            self.cand, self.cand_n = None, 0
            return None, self.state

        if m == self.cand:
            self.cand_n += 1
        else:
            self.cand, self.cand_n = m, 1

        if self.cand_n < self.hold:         # 还没稳定够，先不认
            return None, self.state

        old = self.state
        self.state, self.cand, self.cand_n = self.cand, None, 0
        evt = None
        if old is not None and old != self.state:
            evt = (old, self.state)
            self.history.append(evt)
        return evt, self.state


# ----------------------------------------------------------------------------
# 4. 轨迹工具（动态识别已下线，仅供离线分析脚本使用）
# ----------------------------------------------------------------------------
def norm_traj(traj, L=16):
    """traj: list of (cx, cy, area[, 指尖数]) -> (L, 3) 或 (L, 4) 归一化。"""
    a = np.asarray(traj, np.float32)
    if len(a) < 2:
        return None
    xy = a[:, :2].copy()
    xy -= xy[0]
    diag = np.linalg.norm(xy.max(axis=0) - xy.min(axis=0))
    if diag < 8.0:          # 几乎没动：避免除零爆炸，同时这类动作本身不可判别
        diag = 8.0
    xy /= diag
    ar = a[:, 2] / (a[0, 2] + 1e-6)     # 面积比：反映手靠近/远离摄像头
    ts = np.linspace(0, len(a) - 1, L)
    idx = np.arange(len(a))
    x = np.interp(ts, idx, xy[:, 0])
    y = np.interp(ts, idx, xy[:, 1])
    z = np.interp(ts, idx, ar)
    if a.shape[1] >= 4:                 # 指尖数通道：已量纲归一，直接插值
        nf = np.interp(ts, idx, (a[:, 3] - NF_SCALE) / NF_SCALE)
        return np.stack([x, y, z, nf], axis=1)
    return np.stack([x, y, z], axis=1)


def norm_traj_active(traj, L=16, act_ratio=0.25):
    """动作段版轨迹归一化：
    1) 能量检测裁掉首尾静止段（不同录制时长/静止占比不再影响形状）
    2) 去均值代替去起点（起点相位不稳定）
    3) 面积以段内中位数为基准（比首帧稳）
    """
    a = np.asarray(traj, np.float32)
    if len(a) < 4:
        return None
    sp = np.linalg.norm(np.diff(a[:, :2], axis=0), axis=1)
    if sp.max() < 1e-3:
        return None
    act = sp > act_ratio * sp.max()
    idx = np.where(act)[0]
    i0 = max(0, int(idx[0]) - 2)
    i1 = min(len(a) - 1, int(idx[-1]) + 3)
    if i1 - i0 < 4:
        return None
    s = a[i0:i1 + 1]

    xy = s[:, :2].copy()
    xy -= xy.mean(axis=0)
    diag = np.linalg.norm(xy.max(axis=0) - xy.min(axis=0))
    if diag < 1e-3:
        return None
    xy /= diag
    ar = s[:, 2] / (float(np.median(s[:, 2])) + 1e-6)
    ts = np.linspace(0, len(s) - 1, L)
    idx2 = np.arange(len(s))
    x = np.interp(ts, idx2, xy[:, 0])
    y = np.interp(ts, idx2, xy[:, 1])
    z = np.interp(ts, idx2, ar)
    if a.shape[1] >= 4:                 # 指尖数通道（见 traj_feat）
        nf = np.interp(ts, idx2, (s[:, 3] - NF_SCALE) / NF_SCALE)
        return np.stack([x, y, z, nf], axis=1)
    return np.stack([x, y, z], axis=1)


def dtw(a, b):
    """返回归一化后的平均步代价（除以路径长度，消除长度差异）。"""
    n, m = len(a), len(b)
    D = np.full((n + 1, m + 1), np.inf, np.float32)
    D[0, 0] = 0.0
    for i in range(1, n + 1):
        ai = a[i - 1]
        for j in range(1, m + 1):
            cost = np.linalg.norm(ai - b[j - 1])
            D[i, j] = cost + min(D[i - 1, j], D[i, j - 1], D[i - 1, j - 1])
    return float(D[n, m] / (n + m))


class DynRecognizer(object):
    def __init__(self, templates, thresh=0.55, thr_map=None, meta=None):
        self.tpl = templates or {}
        self.thresh = thresh
        self.thr_map = thr_map or {}      # 每类自适应阈值，来自离线整定
        meta = meta or {}
        # FD 通道与静态路径共用一套 z-score 参数，保证两侧量纲一致
        self.mu = np.asarray(meta["mu"], np.float32) if "mu" in meta else None
        self.sd = np.asarray(meta["sd"], np.float32) if "sd" in meta else None
        self.fd_w = float(meta.get("dyn_fd_w", 1.0))
        self.smooth = int(meta.get("dyn_smooth", 0))
        self.cyclic = bool(meta.get("dyn_cyclic", True))

    def predict(self, traj):
        q = norm_seq_dyn(traj, mu=self.mu, sd=self.sd, fd_w=self.fd_w,
                         smooth=self.smooth)
        if q is None:
            return UNKNOWN, 9.9
        best, bd = UNKNOWN, 1e9
        for lab, tpls in self.tpl.items():
            d = dist_to_protos(q, tpls, cyclic=self.cyclic)
            if d < bd:
                bd, best = d, lab
        if bd > float(self.thr_map.get(best, self.thresh)):
            return UNKNOWN, bd
        return best, bd


class MotionRecorder(object):
    """自动触发：手稳定出现 STABLE 帧后录 REC_LEN 帧，无需按键。"""
    def __init__(self, stable=5, rec_len=40, lose=8):
        self.stable, self.rec_len, self.lose = stable, rec_len, lose
        self.seen = 0
        self.miss = 0
        self.buf = []
        self.recording = False

    def feed(self, feat):
        """feat: traj_feat() 的一帧 (cx, cy, area, 指尖数) 或 None。返回完整轨迹或 None。"""
        if feat is None:
            self.seen = 0
            if self.recording:
                self.miss += 1
                if self.miss >= self.lose:
                    return self._finish()
            return None

        self.miss = 0
        if not self.recording:
            self.seen += 1
            if self.seen >= self.stable:
                self.recording = True
                self.buf = []
        if self.recording:
            self.buf.append(feat)
            if len(self.buf) >= self.rec_len:
                return self._finish()
        return None

    def _finish(self):
        traj = self.buf if len(self.buf) >= 8 else None
        self.recording, self.buf, self.seen, self.miss = False, [], 0, 0
        return traj


# ----------------------------------------------------------------------------
# 5. 模板存取
# ----------------------------------------------------------------------------
def load_tpl():
    if os.path.exists(TPL_PATH):
        with open(TPL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"static": {}, "dynamic": {}}


def save_tpl(t):
    with open(TPL_PATH, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False, indent=2)


def open_cam(idx, w, h, fps=30, fourcc="MJPG"):
    """打开摄像头，并回读实际生效的分辨率/帧率/编码。

    顺序很关键：V4L2 后端必须**先设 FOURCC 再设分辨率和帧率**，反过来的话
    格式切换会被驱动忽略——表现为"明明设了 MJPEG，却还是拿到 YUYV，
    于是 640x480 只有 10fps"。这是 OpenCV 采 USB 摄像头最常见的坑。
    """
    cap = cv2.VideoCapture(idx)
    if fourcc:                       # 必须先设，否则不生效
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*fourcc))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    cap.set(cv2.CAP_PROP_FPS, fps)
    if not cap.isOpened():
        print("[ERR] 打不开摄像头 /dev/video%d" % idx)
        sys.exit(1)

    # 回读：摄像头经常静默返回一个"它支持的"组合，不打印就永远不知道
    aw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    ah = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    afps = cap.get(cv2.CAP_PROP_FPS)
    acc = int(cap.get(cv2.CAP_PROP_FOURCC))
    name = "".join(chr((acc >> (8 * i)) & 0xFF) for i in range(4)) if acc else "N/A"
    print("[cam] 请求 %dx%d@%d %s  ->  实际 %dx%d@%.1f %s"
          % (w, h, fps, fourcc or "-", aw, ah, afps, name))
    if (aw, ah) != (w, h):
        print("[warn] 该摄像头不支持 %dx%d，实际输出 %dx%d" % (w, h, aw, ah))
    if afps + 0.5 < fps:
        print("[warn] 帧率只到 %.1f（低于请求的 %d）：USB2.0 带宽不够或格式没切到 MJPEG"
              % (afps, fps))
    return cap


class FpsMeter(object):
    """实测帧率与分阶段耗时——上板卡顿时先靠它定位瓶颈在采集、分割还是特征。"""
    def __init__(self, n=30, tag="处理"):
        self.n, self.tag = n, tag
        self.t0 = time.time()
        self.cnt = 0
        self.acc = {}

    def tick(self, **ms):
        for k, v in ms.items():
            self.acc[k] = self.acc.get(k, 0.0) + v
        self.cnt += 1
        if self.cnt >= self.n:
            dt = time.time() - self.t0
            parts = " ".join("%s %.0fms" % (k, 1e3 * v / self.cnt)
                             for k, v in sorted(self.acc.items()))
            print("\n[%s] 实测 %.1f fps | 单帧: %s | 合计 %.0fms"
                  % (self.tag, self.cnt / max(dt, 1e-6), parts,
                     1e3 * sum(self.acc.values()) / self.cnt))
            self.t0, self.cnt, self.acc = time.time(), 0, {}


def poll_quit():
    """无 GUI(headless/Jupyter)环境下 waitKey 可能不可用，做保护。"""
    try:
        return (cv2.waitKey(1) & 0xFF) == ord("q")
    except Exception:
        return False


def draw(frame, cnt, mask, tips, text):
    vis = frame.copy()
    if cnt is not None:
        cv2.drawContours(vis, [cnt], -1, (0, 255, 0), 2)
        for t in tips:
            cv2.circle(vis, t, 5, (0, 0, 255), -1)
    cv2.putText(vis, text, (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    return np.hstack([vis, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)])


# ----------------------------------------------------------------------------
# 6. 主流程
# ----------------------------------------------------------------------------
def run_static(args):
    t = load_tpl()
    meta = dict(t.get("meta") or {})
    if args.thresh is not None:          # 显式指定阈值时覆盖每类阈值
        meta.pop("cls_thr", None)
        meta["thresh"] = args.thresh
    rec = StaticRecognizer(t["static"], meta)
    seg = make_seg(args, args.height, args.width)
    cap = open_cam(args.camera, args.width, args.height, args.fps, args.fourcc)
    print("[静态识别] mode=%s 模板=%s 阈值=%s"
          % (rec.mode, list(t["static"].keys()) or "无(使用指尖数规则)",
             rec.cls_thr or round(rec.default_thr, 3)))
    print("[静态识别] 白平衡校正=%s 形态学核=%d 每 %d 帧处理 1 帧 ROI跟踪=%s"
          % ("关" if args.no_wb else "开", args.morph, args.skip + 1,
             "关" if args.no_roi else "开"))
    tracker = None if args.no_roi else RoiTracker()
    meter = FpsMeter(tag="静态")
    n, roi = 0, None
    while True:
        t0 = time.time()
        ok, frame = cap.read()
        t1 = time.time()
        if not ok:
            continue
        n += 1
        if n % (args.skip + 1):
            continue
        cnt, mask = seg(frame, roi)
        t2 = time.time()
        if tracker is not None:
            roi = tracker.next(cnt, frame.shape)
        if cnt is None:
            txt = "%s (未检测到手)" % UNKNOWN
            tips = []
            lab, d, nf = UNKNOWN, 0.0, 0
        else:
            lab, d, nf, tips = rec.predict(cnt)
            txt = "%s  d=%.2f  fingers=%d" % (lab, d, nf)
        t3 = time.time()
        print("\r%s   " % txt, end="", flush=True)
        if args.out:
            cv2.imwrite(args.out, draw(frame, cnt, mask, tips, txt))
        t4 = time.time()
        meter.tick(cap=t1 - t0, seg=t2 - t1, feat=t3 - t2, out=t4 - t3)
        if poll_quit():
            break
    cap.release()


def run_transition(args):
    """手势跃迁识别：展示一个静态手势并保持 ~1 秒，再切到另一个，输出 A -> B。"""
    t = load_tpl()
    meta = dict(t.get("meta") or {})
    if args.thresh is not None:          # 显式指定阈值时覆盖每类阈值
        meta.pop("cls_thr", None)
        meta["thresh"] = args.thresh
    rec = StaticRecognizer(t["static"], meta)
    tr = TransitionRecognizer(rec, win=args.win, need=args.need,
                              hold=args.hold)
    seg = make_seg(args, args.height, args.width)
    cap = open_cam(args.camera, args.width, args.height, args.fps, args.fourcc)
    print("[跃迁识别] 模板=%s  投票=%d/%d  稳定保持=%d 帧"
          % (list(rec.tpl.keys()) or "无(使用指尖数规则)", args.need, args.win,
             args.hold))
    print("[跃迁识别] 展示一个手势保持约 1 秒，再切换到另一个，即输出 A -> B")
    tracker = None if args.no_roi else RoiTracker()
    meter = FpsMeter(tag="跃迁")
    n, roi = 0, None
    last = "无"
    while True:
        t0 = time.time()
        ok, frame = cap.read()
        t1 = time.time()
        if not ok:
            continue
        n += 1
        if n % (args.skip + 1):
            continue
        cnt, mask = seg(frame, roi)
        t2 = time.time()
        if tracker is not None:
            roi = tracker.next(cnt, frame.shape)
        evt, state = tr.feed(cnt)
        t3 = time.time()
        tips = []
        if evt:
            last = "%s -> %s" % (gname(evt[0]), gname(evt[1]))
            print("\n[跃迁] %s" % last)
        txt = "当前:%s  上次跃迁:%s" % (gname(state), last)
        print("\r%s   " % txt, end="", flush=True)
        if args.out:
            if cnt is not None:
                tips = count_fingertips(cnt)[1]
            cv2.imwrite(args.out, draw(frame, cnt, mask, tips, txt))
        t4 = time.time()
        meter.tick(cap=t1 - t0, seg=t2 - t1, feat=t3 - t2, out=t4 - t3)
        if poll_quit():
            break
    cap.release()
    if tr.history:
        print("\n本次跃迁序列: %s" % "  ".join(
            "%s -> %s" % (gname(a), gname(b)) for a, b in tr.history))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="static", choices=["static", "transition"],
                    help="static=单帧静态识别；transition=手势跃迁识别(A -> B)")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--fps", type=int, default=30, help="请求采集帧率(实际值会回读打印)")
    ap.add_argument("--fourcc", default="MJPG",
                    help="像素格式: MJPG(默认,压缩后省USB2.0带宽) / YUYV(原始,更清晰但帧率低)")
    ap.add_argument("--no-wb", action="store_true",
                    help="关掉灰度世界白平衡(已在 v4l2 层锁定时可省掉单帧最贵的一步)")
    ap.add_argument("--morph", type=int, default=5, help="形态学核边长(奇数)，调小可提速")
    ap.add_argument("--no-roi", action="store_true",
                    help="静态模式关闭 ROI 跟踪（默认开启，实测 1.7x 提速且不改变识别结果）")
    ap.add_argument("--use-pl", action="store_true",
                    help="用 PL(FPGA) 加速肤色分割与形态学，需 --bit 指定 overlay")
    ap.add_argument("--bit", default="skin_morph.bit", help="overlay bitstream 路径")
    ap.add_argument("--skip", type=int, default=1, help="每 skip+1 帧处理 1 帧")
    ap.add_argument("--thresh", type=float, default=None,
                    help="未知判定阈值；不指定则用模板里每类的 cls_thr")
    ap.add_argument("--win", type=int, default=7, help="跃迁投票窗口帧数")
    ap.add_argument("--need", type=int, default=5, help="窗口内至少多少票才认")
    ap.add_argument("--hold", type=int, default=4, help="新手势需连续保持的帧数")
    ap.add_argument("--out", default="", help="标注结果输出图片路径(可选)")
    args = ap.parse_args()

    if args.mode == "static":
        run_static(args)              # 静态阈值来自 sign_templates.json 的 meta.cls_thr
    else:
        run_transition(args)


if __name__ == "__main__":
    main()
