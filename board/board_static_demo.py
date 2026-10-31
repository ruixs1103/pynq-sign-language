#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Low-latency direct static-gesture demo for PYNQ-Z2 notebooks."""
import os
import threading
import time

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
UNKNOWN = "未知"
NAMES = {"1": "1", "2": "2", "3": "3", "4": "4", "5": "5",
         "6": "THUMBS UP", "7": "STOP", None: "NONE", UNKNOWN: "UNKNOWN"}

_state = {"on": False, "cap": None, "seg": None, "rec": None,
          "img": None, "label": None, "voice": None, "wb_strength": None}

VOICE_KEYS = {"1": "d1", "2": "d2", "3": "d3", "4": "d4", "5": "d5",
              "6": "thumbs_up", "7": "static_stop"}


def _init(width, height, wb_strength):
    from pynq import Overlay
    from pl_hand_seg import PlHandSeg
    from pynq_sign_language import StaticRecognizer, load_tpl

    overlay = Overlay(os.path.join(HERE, "skin_morph.bit"))
    seg = PlHandSeg(overlay, rows=height, cols=width, use_wb=wb_strength > 0,
                    wb_strength=wb_strength)
    templates = load_tpl()
    rec = StaticRecognizer(templates.get("static") or {}, templates.get("meta") or {})
    return seg, rec


def _loop(stable, release, display_fps, jpeg_quality):
    import board_voice
    from product_display import compose_static_large

    last_raw, same = None, 0
    confirmed = None
    missing = 0
    next_display = 0.0

    while _state["on"]:
        ok, frame = _state["cap"].read()
        if not ok or frame is None:
            time.sleep(0.01)
            continue

        cnt, mask = _state["seg"](frame)
        if cnt is None:
            label, distance, fingers, tips = None, -1.0, 0, []
        else:
            label, distance, fingers, tips = _state["rec"].predict(cnt)
        valid = None if label == UNKNOWN else label

        if valid is not None and valid == last_raw:
            same += 1
        else:
            last_raw, same = valid, (1 if valid is not None else 0)

        if valid is None:
            missing += 1
            if missing >= release:
                confirmed = None
        else:
            missing = 0

        if valid is not None and same >= stable and valid != confirmed:
            confirmed = valid
            box = _state.get("label")
            if box is not None:
                box.value = "<b>识别结果：</b>%s" % NAMES.get(valid, valid)
            voice_key = VOICE_KEYS.get(valid)
            if voice_key:
                board_voice.speak([voice_key], gap=0.0)
            same = 0

        now = time.monotonic()
        if now < next_display:
            continue
        next_display = now + 1.0 / max(1.0, float(display_fps))
        shown = NAMES.get(label, str(label))
        screen = compose_static_large(frame, mask, gesture=shown, distance=distance,
                                      fingers=fingers, backend="PL", tips=tips)
        ok_jpg, buf = cv2.imencode(
            ".jpg", screen, [int(cv2.IMWRITE_JPEG_QUALITY), int(jpeg_quality)])
        if ok_jpg and _state.get("img") is not None:
            _state["img"].value = buf.tobytes()


def launch(width=640, height=480, stable=4, release=3,
           display_fps=8, jpeg_quality=65, wb_strength=0.2):
    import ipywidgets as widgets
    from IPython.display import display

    stop()
    os.chdir(HERE)
    if (_state["seg"] is None or _state["rec"] is None
            or _state["wb_strength"] != float(wb_strength)):
        _state["seg"], _state["rec"] = _init(width, height, wb_strength)
        _state["wb_strength"] = float(wb_strength)

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    if not cap.isOpened():
        raise RuntimeError("USB camera 0 cannot be opened")
    _state["cap"], _state["on"] = cap, True

    label = widgets.HTML("<b>识别结果：</b>等待手势")
    image = widgets.Image(format="jpeg", width=1040,
                          layout=widgets.Layout(width="100%", max_width="1040px"))
    button = widgets.Button(description="停止识别", button_style="danger")
    voice = widgets.HTML(value="")
    _state["label"], _state["img"], _state["voice"] = label, image, voice
    # Reuse the proven browser WAV player without loading its recognition loop.
    import board_voice
    board_voice._state["voice"] = voice

    def _stop(_=None):
        stop()
        label.value = "<b>状态：</b>已停止（摄像头已释放）"

    button.on_click(_stop)
    display(widgets.VBox([label, image, button, voice]))
    threading.Thread(target=_loop,
                     args=(stable, release, display_fps, jpeg_quality),
                     daemon=True).start()
    print("静态手势直接识别：1-5 / THUMBS UP / STOP")
    print("PL分割，显示 %.1f FPS，JPEG质量 %d" % (display_fps, jpeg_quality))
    print("软件白平衡强度 %.2f (0=关闭, 1=完整校正)" % wb_strength)


def stop():
    _state["on"] = False
    cap = _state.get("cap")
    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass
    _state["cap"] = None
