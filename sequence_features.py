"""动态序列特征提取（B 负责）。

流程：帧序列 -> 均匀抽取 16/24 帧 -> 每帧分割 ->
      形状特征（面积/中心/外接框/方向）+ 运动特征（位移/帧差）+
      HOG 统计（均值/标准差/变化量）-> 固定长度向量。
"""

import numpy as np

from feature_utils import hog_feature
from preprocess import preprocess_frame

DEFAULT_SEQ_LEN = 16
HOG_DIM = 1764                       # 128x128, 16x16 cell, 2x2 block, 9 方向
SCALAR_DIM = 21
FEATURE_DIM = SCALAR_DIM + 3 * HOG_DIM


def sample_frames(frames, seq_len=DEFAULT_SEQ_LEN):
    """均匀抽取 seq_len 帧；帧数不足时按索引重复补齐。"""
    frames = list(frames)
    if not frames:
        raise ValueError("帧序列为空")
    if seq_len <= 0:
        raise ValueError("seq_len 必须为正整数")
    if len(frames) == seq_len:
        return frames
    idx = np.linspace(0, len(frames) - 1, seq_len).round().astype(int)
    return [frames[int(i)] for i in idx]


def _zero_features():
    return {
        "area": 0.0, "cx": 0.5, "cy": 0.5, "w": 0.0, "h": 0.0,
        "angle": 0.0,
        "hog": np.zeros(HOG_DIM, np.float32),
        "binary": np.zeros((128, 128), np.uint8),
    }


def _frame_features(frame_bgr, preprocess_fn=preprocess_frame):
    if isinstance(frame_bgr, tuple) and len(frame_bgr) == 2:
        binary, info = frame_bgr
    else:
        binary, info = preprocess_fn(frame_bgr)
    if binary is None:
        return None
    h_img, w_img = info["frame_h"], info["frame_w"]
    return {
        "area": info["area"] / float(h_img * w_img),
        "cx": info["centroid"][0] / w_img,
        "cy": info["centroid"][1] / h_img,
        "w": info["bbox"][2] / w_img,
        "h": info["bbox"][3] / h_img,
        "angle": np.deg2rad(info["angle"]),
        "hog": hog_feature(binary),
        "binary": binary,
    }


def extract_sequence_features(frames, seq_len=DEFAULT_SEQ_LEN,
                              preprocess_fn=preprocess_frame):
    """提取固定长度序列特征，返回 float32 一维向量。

    至少需要 2 帧，否则抛出 ValueError。
    某帧未检测到手时使用前一有效帧的特征前向填充（首帧缺失则填零）。
    """
    frames = list(frames)
    if len(frames) < 2:
        raise ValueError("动态序列帧数不足：至少需要 2 帧")
    sampled = sample_frames(frames, seq_len)

    feats, missing, prev = [], 0, None
    for frame in sampled:
        d = _frame_features(frame, preprocess_fn=preprocess_fn)
        if d is None:
            missing += 1
            d = prev if prev is not None else _zero_features()
        feats.append(d)
        prev = d

    area = np.array([d["area"] for d in feats])
    cx = np.array([d["cx"] for d in feats])
    cy = np.array([d["cy"] for d in feats])
    w = np.array([d["w"] for d in feats])
    h = np.array([d["h"] for d in feats])
    ang = np.array([d["angle"] for d in feats])
    hog_mat = np.stack([d["hog"] for d in feats])
    bins = [d["binary"].astype(np.float32) / 255.0 for d in feats]

    speed = np.hypot(np.diff(cx), np.diff(cy))
    diffs = np.array([np.mean(np.abs(bins[i] - bins[i + 1]))
                      for i in range(len(bins) - 1)])
    if len(hog_mat) > 1:
        hog_delta = np.abs(np.diff(hog_mat, axis=0)).mean(axis=0)
    else:
        hog_delta = np.zeros(HOG_DIM, np.float32)

    scalars = np.array([
        area.mean(), area.std(), area.max() - area.min(),
        cx.mean(), cx.std(), cy.mean(), cy.std(),
        speed.mean() if len(speed) else 0.0,
        speed.std() if len(speed) else 0.0,
        speed.max() if len(speed) else 0.0,
        w.mean(), w.std(), h.mean(), h.std(),
        np.sin(ang).mean(), np.cos(ang).mean(),
        np.sin(ang).std(), np.cos(ang).std(),
        diffs.mean(), diffs.max(),
        missing / float(seq_len),
    ], np.float32)

    return np.concatenate([
        scalars,
        hog_mat.mean(axis=0),
        hog_mat.std(axis=0),
        hog_delta,
    ]).astype(np.float32)
