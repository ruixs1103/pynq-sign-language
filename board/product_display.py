#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Product-style display compositor for the sign-language demo."""
import argparse

import cv2
import numpy as np


CANVAS_W = 1280
CANVAS_H = 720


def _fit(image, width, height, interpolation=cv2.INTER_AREA):
    """Letterbox an image into a fixed-size BGR panel."""
    if image is None or image.size == 0:
        return np.zeros((height, width, 3), dtype=np.uint8)
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    ih, iw = image.shape[:2]
    scale = min(float(width) / iw, float(height) / ih)
    nw, nh = max(1, int(iw * scale)), max(1, int(ih * scale))
    resized = cv2.resize(image, (nw, nh), interpolation=interpolation)
    panel = np.full((height, width, 3), (18, 21, 25), dtype=np.uint8)
    x, y = (width - nw) // 2, (height - nh) // 2
    panel[y:y + nh, x:x + nw] = resized
    return panel


def _text(image, value, xy, scale=0.65, color=(225, 230, 235), thickness=1):
    cv2.putText(image, str(value), xy, cv2.FONT_HERSHEY_SIMPLEX, scale, color,
                thickness, cv2.LINE_AA)


def compose_display(frame, mask, gesture="NONE", distance=None, fingers=0,
                    mode="WAIT", sequence=None, backend="CPU", tips=None):
    """Return a stable 1280x720 BGR dashboard.

    ``gesture`` uses an ASCII display value because a minimal PYNQ image does
    not necessarily contain a Chinese font. Chinese status remains visible in
    the notebook HTML widget below the image.
    """
    sequence = list(sequence or [])
    tips = list(tips or [])
    live = frame.copy()
    for point in tips:
        cv2.circle(live, tuple(map(int, point)), 6, (20, 40, 255), -1,
                   lineType=cv2.LINE_AA)

    binary = np.zeros(frame.shape[:2], np.uint8) if mask is None else mask
    if binary.ndim == 3:
        binary = cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY)
    binary = np.where(binary > 0, 255, 0).astype(np.uint8)

    canvas = np.full((CANVAS_H, CANVAS_W, 3), (12, 15, 18), dtype=np.uint8)
    canvas[:70] = (28, 33, 39)
    _text(canvas, "SIGN LANGUAGE RECOGNITION", (28, 45), 0.92,
          (242, 245, 247), 2)
    state_color = (70, 220, 110) if mode == "REC" else (80, 190, 255)
    _text(canvas, "MODE  %s" % mode, (1045, 44), 0.64, state_color, 2)

    panel_w, panel_h = 610, 458
    left_x, right_x, top = 20, 650, 105
    canvas[top:top + panel_h, left_x:left_x + panel_w] = _fit(
        live, panel_w, panel_h)
    canvas[top:top + panel_h, right_x:right_x + panel_w] = _fit(
        binary, panel_w, panel_h, cv2.INTER_NEAREST)

    cv2.rectangle(canvas, (left_x, 76), (left_x + 190, 105), (45, 52, 60), -1)
    cv2.rectangle(canvas, (right_x, 76), (right_x + 210, 105), (45, 52, 60), -1)
    _text(canvas, "LIVE HAND", (left_x + 10, 98), 0.58, (238, 240, 242), 1)
    _text(canvas, "BINARY MASK", (right_x + 10, 98), 0.58, (238, 240, 242), 1)

    cv2.rectangle(canvas, (20, 585), (1260, 700), (28, 33, 39), -1)
    cv2.line(canvas, (20, 585), (1260, 585), (72, 82, 92), 1)
    _text(canvas, "GESTURE", (42, 619), 0.48, (145, 158, 170), 1)
    _text(canvas, gesture, (42, 669), 1.22, state_color, 2)
    _text(canvas, "MATCH DATA", (315, 619), 0.48, (145, 158, 170), 1)
    dist_text = "--" if distance is None or distance < 0 else "%.3f" % distance
    _text(canvas, "distance %s   fingers %d" % (dist_text, fingers),
          (315, 662), 0.67, (225, 230, 235), 1)
    _text(canvas, "CONFIRMED SEQUENCE", (725, 619), 0.48, (145, 158, 170), 1)
    _text(canvas, " ".join(sequence) if sequence else "--", (725, 669), 0.88,
          (242, 245, 247), 2)
    _text(canvas, "%s SEGMENTATION / ARM PS CLASSIFIER" % backend.upper(),
          (720, 46), 0.42, (150, 164, 176), 1)
    return canvas


def compose_compact(frame, mask, gesture="NONE", distance=None, fingers=0,
                    backend="PL", tips=None):
    """Build an 800x380 low-latency view for the PYNQ notebook."""
    tips = list(tips or [])
    live = frame.copy()
    for point in tips:
        cv2.circle(live, tuple(map(int, point)), 5, (20, 40, 255), -1,
                   lineType=cv2.LINE_AA)
    live = cv2.resize(live, (400, 300), interpolation=cv2.INTER_AREA)

    binary = np.zeros(frame.shape[:2], np.uint8) if mask is None else mask
    if binary.ndim == 3:
        binary = cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY)
    binary = np.where(binary > 0, 255, 0).astype(np.uint8)
    binary = cv2.resize(binary, (400, 300), interpolation=cv2.INTER_NEAREST)
    binary = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    canvas = np.full((380, 800, 3), (18, 21, 25), dtype=np.uint8)
    canvas[:300, :400] = live
    canvas[:300, 400:] = binary
    cv2.rectangle(canvas, (0, 0), (125, 30), (45, 52, 60), -1)
    cv2.rectangle(canvas, (400, 0), (565, 30), (45, 52, 60), -1)
    _text(canvas, "LIVE HAND", (9, 22), 0.52, (240, 242, 245), 1)
    _text(canvas, "BINARY MASK", (409, 22), 0.52, (240, 242, 245), 1)

    cv2.line(canvas, (0, 300), (800, 300), (75, 85, 95), 1)
    color = (70, 220, 110) if gesture not in ("NONE", "UNKNOWN") else (80, 190, 255)
    _text(canvas, "GESTURE", (18, 328), 0.40, (145, 158, 170), 1)
    _text(canvas, gesture, (18, 366), 0.92, color, 2)
    dist_text = "--" if distance is None or distance < 0 else "%.3f" % distance
    _text(canvas, "distance %s   fingers %d" % (dist_text, fingers),
          (285, 354), 0.56, (225, 230, 235), 1)
    _text(canvas, "%s / ARM PS" % backend.upper(), (640, 354), 0.43,
          (150, 164, 176), 1)
    return canvas


def compose_static_large(frame, mask, gesture="NONE", distance=None, fingers=0,
                         backend="PL", tips=None):
    """Build a larger 1040x490 view dedicated to the static demo."""
    tips = list(tips or [])
    live = frame.copy()
    for point in tips:
        cv2.circle(live, tuple(map(int, point)), 6, (20, 40, 255), -1,
                   lineType=cv2.LINE_AA)
    live = cv2.resize(live, (520, 390), interpolation=cv2.INTER_AREA)

    binary = np.zeros(frame.shape[:2], np.uint8) if mask is None else mask
    if binary.ndim == 3:
        binary = cv2.cvtColor(binary, cv2.COLOR_BGR2GRAY)
    binary = np.where(binary > 0, 255, 0).astype(np.uint8)
    binary = cv2.resize(binary, (520, 390), interpolation=cv2.INTER_NEAREST)
    binary = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    canvas = np.full((490, 1040, 3), (18, 21, 25), dtype=np.uint8)
    canvas[:390, :520] = live
    canvas[:390, 520:] = binary
    cv2.rectangle(canvas, (0, 0), (155, 36), (45, 52, 60), -1)
    cv2.rectangle(canvas, (520, 0), (720, 36), (45, 52, 60), -1)
    _text(canvas, "LIVE HAND", (12, 27), 0.65, (240, 242, 245), 1)
    _text(canvas, "BINARY MASK", (532, 27), 0.65, (240, 242, 245), 1)

    cv2.line(canvas, (0, 390), (1040, 390), (75, 85, 95), 1)
    color = (70, 220, 110) if gesture not in ("NONE", "UNKNOWN") else (80, 190, 255)
    _text(canvas, "GESTURE", (24, 423), 0.46, (145, 158, 170), 1)
    _text(canvas, gesture, (24, 472), 1.15, color, 2)
    dist_text = "--" if distance is None or distance < 0 else "%.3f" % distance
    _text(canvas, "distance %s   fingers %d" % (dist_text, fingers),
          (385, 455), 0.68, (225, 230, 235), 1)
    _text(canvas, "%s SEGMENTATION / ARM PS" % backend.upper(),
          (775, 455), 0.48, (150, 164, 176), 1)
    return canvas


def _demo_frame():
    frame = np.full((480, 640, 3), (54, 60, 66), np.uint8)
    cv2.ellipse(frame, (320, 310), (95, 125), 0, 0, 360, (80, 150, 210), -1)
    for x in (260, 300, 340, 380):
        cv2.rectangle(frame, (x, 90), (x + 28, 300), (80, 150, 210), -1)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    mask = np.where(gray > 100, 255, 0).astype(np.uint8)
    return frame, mask


def main():
    parser = argparse.ArgumentParser(description="Generate a display preview without a board")
    parser.add_argument("--out", default="report/display_preview.jpg")
    args = parser.parse_args()
    frame, mask = _demo_frame()
    image = compose_display(frame, mask, gesture="4", distance=0.184,
                            fingers=4, mode="REC", sequence=["1", "4"],
                            backend="PL")
    if not cv2.imwrite(args.out, image):
        raise SystemExit("cannot write %s" % args.out)
    print(args.out)


if __name__ == "__main__":
    main()
