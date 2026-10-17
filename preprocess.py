"""共享图像预处理：YCrCb 分割 -> 最大连通区域 -> 128x128 二值图（B 负责）。

静态模型、动态序列特征以及 HLS Python 参考实现共用本模块，
保证 PC 端输出与后续 FPGA 输出可逐像素对比。
"""

import cv2
import numpy as np

IMG_SIZE = 128

# 常用 YCrCb 肤色范围（可被调用方覆盖，用于个性化肤色校准）
YCRCB_MIN = (0, 138, 82)
YCRCB_MAX = (255, 170, 122)

MIN_HAND_AREA = 60  # 小于该像素面积视为无手
MARGIN = 4          # 归一化裁剪边距
SEVERE_EDGE_RATIO = 0.03  # 边界前景占手部面积超过此值才视为严重截断


def segment_hand_ycrcb(frame_bgr, ycrcb_min=None, ycrcb_max=None):
    """YCrCb 颜色分割 + 开闭运算，返回 0/255 二值 mask。"""
    if frame_bgr is None:
        raise ValueError("输入图像为空")
    frame = np.asarray(frame_bgr)
    if frame.size == 0 or frame.ndim != 3 or frame.shape[2] < 3:
        raise ValueError(
            f"输入必须是有效的 BGR 图像，当前 shape={getattr(frame, 'shape', None)}")
    frame = np.ascontiguousarray(frame[:, :, :3])
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    lo = np.array(YCRCB_MIN if ycrcb_min is None else ycrcb_min, dtype=np.uint8)
    hi = np.array(YCRCB_MAX if ycrcb_max is None else ycrcb_max, dtype=np.uint8)
    mask = cv2.inRange(ycrcb, lo, hi)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    return mask


def largest_component(mask):
    """保留最大连通区域；面积过小或没有前景时返回 None。"""
    num, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    if num <= 1:
        return None
    idx = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
    if stats[idx, cv2.CC_STAT_AREA] < MIN_HAND_AREA:
        return None
    return (labels == idx).astype(np.uint8) * 255


def normalize_binary(component, size=IMG_SIZE, margin=MARGIN):
    """裁剪手部包围盒（含边距），保持长宽比填充为正方形后缩放到 size x size。"""
    ys, xs = np.nonzero(component)
    if len(ys) == 0:
        raise ValueError("连通区域为空")
    h_img, w_img = component.shape
    x0 = max(0, int(xs.min()) - margin)
    x1 = min(w_img - 1, int(xs.max()) + margin)
    y0 = max(0, int(ys.min()) - margin)
    y1 = min(h_img - 1, int(ys.max()) + margin)
    crop = component[y0:y1 + 1, x0:x1 + 1]
    ch, cw = crop.shape
    side = max(ch, cw)
    square = np.zeros((side, side), np.uint8)
    oy, ox = (side - ch) // 2, (side - cw) // 2
    square[oy:oy + ch, ox:ox + cw] = crop
    binary = cv2.resize(square, (size, size), interpolation=cv2.INTER_NEAREST)
    return (binary > 0).astype(np.uint8) * 255


def preprocess_frame(frame_bgr, size=IMG_SIZE, ycrcb_min=None, ycrcb_max=None):
    """完整预处理一帧。

    返回 (binary, info)：
      binary: size x size 的 uint8 二值图；未检测到手时为 None。
      info:   dict(hand_found, area, bbox, centroid, touches_edge,
                  angle, frame_w, frame_h)
    """
    frame = np.asarray(frame_bgr)
    mask = segment_hand_ycrcb(frame, ycrcb_min, ycrcb_max)
    info = {
        "hand_found": False,
        "area": 0,
        "bbox": (0, 0, 0, 0),
        "centroid": (0.0, 0.0),
        "touches_edge": False,
        "edge_contact_ratio": 0.0,
        "severely_cropped": False,
        "angle": 0.0,
        "frame_w": int(frame.shape[1]),
        "frame_h": int(frame.shape[0]),
    }
    comp = largest_component(mask)
    if comp is None:
        return None, info
    ys, xs = np.nonzero(comp)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    h_img, w_img = comp.shape
    angle = 0.0
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        biggest = max(contours, key=cv2.contourArea)
        angle = float(cv2.minAreaRect(biggest)[2] % 180.0)
    edge_pixels = (
        int(np.count_nonzero(comp[0, :]))
        + int(np.count_nonzero(comp[-1, :]))
        + int(np.count_nonzero(comp[:, 0]))
        + int(np.count_nonzero(comp[:, -1]))
    )
    area = int((comp > 0).sum())
    edge_contact_ratio = float(edge_pixels / max(1, area))
    info.update({
        "hand_found": True,
        "area": area,
        "bbox": (x0, y0, x1 - x0 + 1, y1 - y0 + 1),
        "centroid": (float(xs.mean()), float(ys.mean())),
        "touches_edge": bool(
            x0 == 0 or y0 == 0 or x1 == w_img - 1 or y1 == h_img - 1),
        "edge_contact_ratio": edge_contact_ratio,
        "severely_cropped": bool(edge_contact_ratio >= SEVERE_EDGE_RATIO),
        "angle": angle,
    })
    binary = normalize_binary(comp, size=size)
    return binary, info


def preprocess_mask(mask, size=IMG_SIZE):
    """Use an existing 0/255 mask as the segmentation result.

    This is the bridge for PL acceleration: PL can produce the full-frame mask,
    then PS still handles largest component selection, metadata extraction and
    128x128 normalization exactly like the CPU path.
    """
    mask, mask_meta = correct_mask_polarity(mask)
    info = {
        "hand_found": False,
        "area": 0,
        "bbox": (0, 0, 0, 0),
        "centroid": (0.0, 0.0),
        "touches_edge": False,
        "edge_contact_ratio": 0.0,
        "severely_cropped": False,
        "angle": 0.0,
        "frame_w": int(mask.shape[1]),
        "frame_h": int(mask.shape[0]),
        **mask_meta,
    }
    comp = largest_component(mask)
    if comp is None:
        return None, info
    ys, xs = np.nonzero(comp)
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    h_img, w_img = comp.shape
    angle = 0.0
    contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if contours:
        biggest = max(contours, key=cv2.contourArea)
        angle = float(cv2.minAreaRect(biggest)[2] % 180.0)
    edge_pixels = (
        int(np.count_nonzero(comp[0, :]))
        + int(np.count_nonzero(comp[-1, :]))
        + int(np.count_nonzero(comp[:, 0]))
        + int(np.count_nonzero(comp[:, -1]))
    )
    area = int((comp > 0).sum())
    edge_contact_ratio = float(edge_pixels / max(1, area))
    info.update({
        "hand_found": True,
        "area": area,
        "bbox": (x0, y0, x1 - x0 + 1, y1 - y0 + 1),
        "centroid": (float(xs.mean()), float(ys.mean())),
        "touches_edge": bool(
            x0 == 0 or y0 == 0 or x1 == w_img - 1 or y1 == h_img - 1),
        "edge_contact_ratio": edge_contact_ratio,
        "severely_cropped": bool(edge_contact_ratio >= SEVERE_EDGE_RATIO),
        "angle": angle,
    })
    binary = normalize_binary(comp, size=size)
    return binary, info


def correct_mask_polarity(mask):
    """Normalize a PL mask and reverse it when the border is mostly foreground."""
    mask = np.asarray(mask)
    if mask.ndim == 3:
        mask = cv2.cvtColor(mask[:, :, :3], cv2.COLOR_BGR2GRAY)
    mask = (mask > 0).astype(np.uint8) * 255
    raw_nonzero_ratio = float(np.count_nonzero(mask) / mask.size)
    border = np.concatenate(
        [mask[0, :], mask[-1, :], mask[:, 0], mask[:, -1]]
    )
    border_nonzero_ratio = float(np.count_nonzero(border) / border.size)
    mask_inverted = bool(
        raw_nonzero_ratio > 0.5 and border_nonzero_ratio > 0.5
    )
    corrected = cv2.bitwise_not(mask) if mask_inverted else mask
    return corrected, {
        "mask_inverted": mask_inverted,
        "raw_nonzero_ratio": raw_nonzero_ratio,
        "raw_border_nonzero_ratio": border_nonzero_ratio,
        "corrected_nonzero_ratio": float(np.count_nonzero(corrected) / corrected.size),
    }
