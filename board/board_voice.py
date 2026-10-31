#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点赞唤醒 -> 逐位读数字 -> 停止结束 -> 中文语音播报。

状态机（每一帧都走完整 PL+PS 管线）：
    WAIT  等待「点赞」(6) 连续稳定 STABLE 帧 -> 播报"请比出数字"，进入 REC
    REC   出现数字 1~5 且稳定 STABLE 帧 -> 记一位并立刻念出来
          同一位要重复输入，需先「释放」(手离开镜头 RELEASE 帧) 或直接换成别的手势
          出现「停止」(7) 稳定 STABLE 帧 -> 播报完整结果，回到 WAIT

语音：预存在 voice/*.wav（PC 端离线合成），用隐藏 <audio autoplay> 在浏览器里播放。
      声音实际从 PC 音箱出来 —— 板端没有声卡也没有播放器。

Jupyter notebook 两行启动：
    %cd /home/xilinx/jupyter_notebooks/sign_demo
    %run board_voice.py

或作为模块调用：
    from board_voice import launch, stop
    launch()      # 可调 launch(stable=5, release=3)
    stop()
"""
import base64
import io
import os
import threading
import time
import wave

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if not os.path.exists(os.path.join(HERE, "sign_templates.json")):
    HERE = "/home/xilinx/jupyter_notebooks/sign_demo"   # %run/__file__ 缺失时兜底

BIT_NAME = "skin_morph.bit"
VOICE_DIR = os.path.join(HERE, "voice")

WAKE, STOP_G = "6", "7"                    # 6=点赞(唤醒)  7=停止(握拳)
DIGITS = ("1", "2", "3", "4", "5")
UNKNOWN = "未知"

_state = {"seg": None, "rec": None, "cap": None, "on": False,
          "img": None, "label": None, "voice": None, "tick": 0}


# --------------------------------------------------------------------------
# PL / PS 初始化（模块级缓存，重复启动不重复下载 bitstream）
# --------------------------------------------------------------------------
def _init_pl(rows=480, cols=640, use_wb=True):
    import pynq
    os.environ.setdefault("XILINX_XRT", "/usr")
    print("[PL] 加载 %s ..." % BIT_NAME)
    ol = pynq.Overlay(os.path.join(HERE, BIT_NAME))
    print("[PL] 已加载, IP: %s" % [k for k in ol.ip_dict if "skin_morph" in k])
    from pl_hand_seg import PlHandSeg
    seg = PlHandSeg(ol, rows=rows, cols=cols, use_wb=use_wb)
    print("[PL] PlHandSeg 就绪  (PL: YCrCb+阈值+形态学 / PS: 白平衡+连通域)")
    return seg


def _init_ps():
    from pynq_sign_language import StaticRecognizer, load_tpl
    t = load_tpl()
    rec = StaticRecognizer(t.get("static") or {}, t.get("meta") or {})
    print("[PS] 类别: %s" % list(rec.tpl.keys()))
    return rec


# --------------------------------------------------------------------------
# 语音合成结果播放
# --------------------------------------------------------------------------
def _wav_path(key):
    return os.path.join(VOICE_DIR, key + ".wav")


def _load_wav(key):
    """返回 (采样率, int16 ndarray)；文件不存在返回 None。"""
    p = _wav_path(key)
    if not os.path.exists(p):
        return None
    try:
        with wave.open(p, "rb") as w:
            if w.getsampwidth() != 2:
                return None
            sr, ch = w.getframerate(), w.getnchannels()
            a = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    except Exception:
        return None
    if ch > 1:
        a = a.reshape(-1, ch).mean(axis=1)
    return sr, a.astype(np.int16)


def speak(keys, gap=0.25):
    """按序拼接语音片段并播放。缺素材则跳过该片段。"""
    chunks, sr = [], None
    for k in keys:
        got = _load_wav(k)
        if got is None:
            continue
        s, a = got
        if sr is None:
            sr = s
        elif s != sr:                                  # 采样率不一致时做朴素重采样
            idx = (np.arange(int(len(a) * sr / s)) * s / sr).astype(np.int64)
            a = a[np.clip(idx, 0, len(a) - 1)]
        chunks.append(a)
        chunks.append(np.zeros(int(sr * gap), dtype=np.int16))   # 片段间留静音，避免粘连
    if not chunks or sr is None:
        return False

    data = np.concatenate(chunks)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(data.tobytes())
    b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    _state["tick"] += 1                                 # 保证内容每次都变，触发重渲染
    html = ('<audio autoplay="autoplay" controls style="display:none" '
            'src="data:audio/wav;base64,%s"></audio>'
            '<span style="display:none">%d</span>' % (b64, _state["tick"]))
    box = _state.get("voice")
    if box is not None:
        box.value = html
    return True


def check_voice():
    """检查语音素材是否齐全，返回缺失清单。"""
    need = ["wake", "stop", "result", "empty"] + ["d" + d for d in DIGITS]
    return [k for k in need if not os.path.exists(_wav_path(k))]


# --------------------------------------------------------------------------
# 主循环：每帧 PL 分割 + PS 识别 + 状态机
# --------------------------------------------------------------------------
def _norm(lab):
    """把 None / 未知 统一成 None（都不是有效手势）。"""
    return None if (lab is None or lab == UNKNOWN) else lab


def _loop(stable, release):
    from pynq_sign_language import gname
    from product_display import compose_display

    mode = "WAIT"          # WAIT=等点赞  REC=正在读数字
    seq = []               # 已确认的数字序列
    last_key, same = None, 0
    armed, released = True, 0
    last_committed = None

    while _state["on"]:
        ok, frame = _state["cap"].read()
        if not ok or frame is None:
            time.sleep(0.03)
            continue

        cnt, mask = _state["seg"](frame)                    # ← PL
        if cnt is None:
            lab, dist, nf, tips = None, -1.0, 0, []
        else:
            lab, dist, nf, tips = _state["rec"].predict(cnt)  # ← PS

        key = _norm(lab)

        # 稳定计数：连续 stable 帧同一手势才算数
        if key is not None and key == last_key:
            same += 1
        else:
            last_key, same = key, (1 if key is not None else 0)

        # 释放 / 换手势 -> 重新武装（允许下一位，包括重复同一位）
        if key is None:
            released += 1
            if released >= release:
                armed = True
        else:
            released = 0
            if key != last_committed:
                armed = True

        hit = (key is not None and same >= stable)

        if mode == "WAIT":
            if hit and key == WAKE:
                speak(["wake"])
                mode, seq = "REC", []
                armed, last_committed = False, WAKE
                same = 0
        else:                                                # mode == "REC"
            if hit and key == STOP_G:
                if seq:
                    speak(["stop", "result"] + ["d" + d for d in seq])
                else:
                    speak(["stop", "empty"])
                mode, seq = "WAIT", []
                armed, last_committed = True, STOP_G
                same = 0
            elif hit and armed and key in DIGITS:
                seq.append(key)
                speak(["d" + key])
                armed, last_committed = False, key
                same = 0

        # 固定尺寸产品界面：真实手部图、PL 二值图、识别文字和数字序列。
        ascii_name = {None: "NONE", UNKNOWN: "UNKNOWN", "6": "WAKE", "7": "STOP"}
        dashboard = compose_display(
            frame, mask, gesture=ascii_name.get(lab, str(lab)), distance=dist,
            fingers=nf, mode=mode, sequence=seq, backend="PL", tips=tips)
        ok2, buf = cv2.imencode(".jpg", dashboard,
                                [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        if ok2 and _state.get("img") is not None:
            _state["img"].value = buf.tobytes()

        if _state.get("label") is not None:
            shown = " ".join(seq) if seq else "（空）"
            state_txt = "等待点赞唤醒" if mode == "WAIT" else "正在读数字"
            _state["label"].value = "状态：%s     已读数字：%s" % (state_txt, shown)


# --------------------------------------------------------------------------
# 对外接口
# --------------------------------------------------------------------------
def launch(width=640, height=480, stable=5, release=3):
    """启动：实时画面 + 状态机 + 语音播报。"""
    import ipywidgets as widgets
    from IPython.display import display

    if _state["on"]:
        stop()
        time.sleep(0.4)

    os.chdir(HERE)                      # load_tpl() 用相对路径找 sign_templates.json
    if _state["seg"] is None:
        _state["seg"] = _init_pl(rows=height, cols=width)
    if _state["rec"] is None:
        _state["rec"] = _init_ps()

    missing = check_voice()
    if missing:
        print("[语音] 缺少素材 %s -> 放到 %s 下才有声音" % (missing, VOICE_DIR))

    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
    _state["cap"] = cap
    _state["on"] = True

    img = widgets.Image(format="jpeg", width=1280,
                        layout=widgets.Layout(width="100%", max_width="1280px"))
    label = widgets.HTML("<b>状态：</b>初始化…")
    voice = widgets.HTML(value="")
    _state["img"], _state["label"], _state["voice"] = img, label, voice

    btn_stop = widgets.Button(description="停止识别", button_style="danger")
    btn_clear = widgets.Button(description="清空重来", button_style="warning")

    def _stop(_=None):
        stop()
        if _state.get("label") is not None:
            _state["label"].value = "<b>状态：</b>已停止（摄像头已释放）"

    btn_stop.on_click(_stop)
    btn_clear.on_click(lambda _: speak(["wake"]))       # 复读一次提示语，兼作试音

    threading.Thread(target=_loop, args=(stable, release), daemon=True).start()

    display(widgets.VBox([
        label, img,
        widgets.HBox([btn_stop, btn_clear]),
        voice,
    ]))
    print("已启动：先比『点赞』唤醒 -> 逐个比数字 -> 比『停止』结束并播报")
    print("参数：稳定 %d 帧确认一位；手离开 %d 帧视为释放（可重复同一位）" % (stable, release))


def stop():
    """停止识别，释放摄像头（overlay 保持加载，下次 launch 直接复用）。"""
    _state["on"] = False
    cap = _state.get("cap")
    if cap is not None:
        try:
            cap.release()
        except Exception:
            pass


if __name__ == "__main__":
    launch()
