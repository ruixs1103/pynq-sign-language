import cv2
import numpy as np

FEATURE_VERSION = "shape_v2"
FEATURE_SIZE = 128


def _resize_binary(binary, size=FEATURE_SIZE):
    img = np.asarray(binary)
    if img.ndim == 3:
        img = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
    img = cv2.resize((img > 0).astype(np.float32), (size, size),
                     interpolation=cv2.INTER_NEAREST)
    return img


def _binned_mean(values, bins):
    chunks = np.array_split(values.astype(np.float32), bins)
    return np.array([float(chunk.mean()) for chunk in chunks], dtype=np.float32)


def _safe_ratio(num, den):
    return float(num) / float(den + 1e-8)


def extract_static_feature(binary):
    """Extract a lightweight shape feature for the NumPy static classifier.

    The old model used a full 128x128 flattened mask. That is sensitive to
    wrist size and global pose. This feature keeps coarse silhouette detail but
    adds projections and shape statistics that separate similar digit gestures
    better while staying cheap enough for PYNQ-Z2 PS-side inference.
    """
    img = _resize_binary(binary)
    ys, xs = np.nonzero(img > 0)
    if len(xs) == 0:
        return np.zeros(1166, dtype=np.float32)

    down = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA).reshape(-1)
    grid = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA).reshape(-1)

    hproj = _binned_mean(img.mean(axis=1), 32)
    vproj = _binned_mean(img.mean(axis=0), 32)

    h, w = img.shape
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bbox_w = x1 - x0 + 1
    bbox_h = y1 - y0 + 1
    area = float((img > 0).mean())
    cx = float(xs.mean()) / float(w)
    cy = float(ys.mean()) / float(h)

    upper = img[:h // 2, :].mean()
    lower = img[h // 2:, :].mean()
    left = img[:, :w // 2].mean()
    right = img[:, w // 2:].mean()
    q1 = img[:h // 2, :w // 2].mean()
    q2 = img[:h // 2, w // 2:].mean()
    q3 = img[h // 2:, :w // 2].mean()
    q4 = img[h // 2:, w // 2:].mean()

    stats = np.array([
        area,
        bbox_w / float(w),
        bbox_h / float(h),
        _safe_ratio(bbox_w, bbox_h),
        _safe_ratio(bbox_h, bbox_w),
        cx,
        cy,
        upper,
        lower,
        left,
        right,
        _safe_ratio(upper, lower),
        _safe_ratio(left, right),
        q1,
        q2,
        q3,
        q4,
    ], dtype=np.float32)

    moments = cv2.moments((img > 0).astype(np.uint8))
    hu = cv2.HuMoments(moments).reshape(-1).astype(np.float32)
    hu = -np.sign(hu) * np.log10(np.abs(hu) + 1e-12)
    hu = np.clip(hu / 20.0, -1.0, 1.0).astype(np.float32)

    feature = np.concatenate([
        down * 1.0,
        grid * 1.5,
        hproj * 1.2,
        vproj * 1.2,
        stats * 2.0,
        hu * 0.5,
    ]).astype(np.float32)
    norm = np.linalg.norm(feature)
    return feature / (norm + 1e-8)


def extract_static_feature_from_path(path):
    img = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return extract_static_feature(img)
