#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""板端拍照测试台：实时预览 + 手动拍照 + PL 分割 + PS 识别。

把之前粘贴在 notebook 单元格里的一大段代码收成一个可复用文件，状态（overlay、
识别器、摄像头）在模块内缓存，重复启动不会重复下载 bitstream。

Jupyter notebook 里两行启动：
    %cd /home/xilinx/jupyter_notebooks/sign_demo
    %run board_shoot.py

或作为模块调用（更灵活）：
    import sys; sys.path.insert(0, '/home/xilinx/jupyter_notebooks/sign_demo')
    from board_shoot import launch, stop
    launch(width=640, height=480)      # 启动
    stop()                             # 停止并释放摄像头

管线分工：
    PL  skin_morph_0 + AXI DMA：BGR->YCrCb 转换、肤色阈值、5x5 椭圆核开/闭运算
    PS  灰世界白平衡、findContours 取最大连通域、特征提取(FD+CDF)、最近邻识别
"""
import os
import threading
import time

import cv2
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BIT_NAME = "skin_morph.bit"

# 模块级状态：overlay / 识别器 / 摄像头 / 最新帧 / 运行标志 / 历史
_state = {"seg": None, "rec": None, "cap": None, "latest": None,
          "on": False, "preview": None, "history": []}


def _init_pl(rows=480, cols=640, use_wb=True):
    """加载 PL overlay，返回 PlHandSeg（PL 做分割，PS 只留白平衡与连通域）。"""
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
    """加载模板并构造识别器。"""
    from pynq_sign_language import StaticRecognizer, load_tpl
    t = load_tpl()
    rec = StaticRecognizer(t.get("static") or {}, t.get("meta") or {})
    print("[PS] 类别: %s" % list(rec.tpl.keys()))
    return rec


def _open_cam(w=640, h=480):
    cap = cv2.VideoCapture(0)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, w)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, h)
    return cap


def _preview_loop():
    """后台线程：持续读帧刷新预览，并缓存最新帧供拍照使用。"""
    while _state["on"]:
        ok, frame = _state["cap"].read()
        if not ok or frame is None:
            time.sleep(0.05)
            continue
        _state["latest"] = frame.copy()
        ok2, buf = cv2.imencode(".jpg", frame)
        if ok2 and _state.get("preview") is not None:
            _state["preview"].value = buf.tobytes()      # 原地刷新，不堆积输出
        time.sleep(0.03)
    try:
        _state["cap"].release()
    except Exception:
        pass


def _annotate(frame, mask, lab, dist, nf, tips):
    """左：原图 + 红色指尖点（不画轮廓线）；右：PL 输出的 mask。"""
    from pynq_sign_language import gname
    vis = frame.copy()
    for pt in tips:
        cv2.circle(vis, pt, 5, (0, 0, 255), -1)
    txt = "%s  d=%.2f  fingers=%d" % (gname(lab), dist, nf)
    cv2.putText(vis, txt, (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)

    mb = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    cv2.putText(mb, "PL mask", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
    return np.hstack([vis, mb]), txt


def launch(width=640, height=480):
    """启动拍照测试台（需在 Jupyter 环境）。"""
    import ipywidgets as widgets
    from IPython.display import display, Image, clear_output

    if _state["on"]:                     # 已在跑就先停掉旧的，避免抢摄像头
        stop()
        time.sleep(0.4)

    os.chdir(HERE)                       # load_tpl() 用相对路径找 sign_templates.json
    if _state["seg"] is None:
        _state["seg"] = _init_pl(rows=height, cols=width)
    if _state["rec"] is None:
        _state["rec"] = _init_ps()

    _state["cap"] = _open_cam(width, height)
    _state["on"] = True
    _state["history"] = []

    preview = widgets.Image(format="jpeg", width=width)
    _state["preview"] = preview
    out = widgets.Output()
    btn_shot = widgets.Button(description="拍照识别", button_style="primary", icon="camera")
    btn_stop = widgets.Button(description="停止预览", button_style="danger")

    def shoot(_):
        with out:
            clear_output(wait=True)
            frame = _state["latest"]
            if frame is None:
                print("还没拿到画面，等预览出现再点")
                return
            cnt, mask = _state["seg"](frame)                    # PL 分割
            if cnt is None:
                lab, dist, nf, tips = None, -1.0, 0, []
            else:
                lab, dist, nf, tips = _state["rec"].predict(cnt)  # PS 识别
            panel, txt = _annotate(frame, mask, lab, dist, nf, tips)
            ok2, buf = cv2.imencode(".jpg", panel)
            if ok2:
                display(Image(data=buf.tobytes()))
            _state["history"].append(txt)
            print("本次: %s" % txt)
            print("历史: %s" % _state["history"])

    def _stop(_=None):
        _state["on"] = False

    btn_shot.on_click(shoot)
    btn_stop.on_click(_stop)

    threading.Thread(target=_preview_loop, daemon=True).start()
    display(widgets.VBox([
        widgets.Label("实时预览 —— 摆好手势后点「拍照识别」"),
        preview,
        widgets.HBox([btn_shot, btn_stop]),
        out,
    ]))
    print("已启动：握拳应为『停止 fingers=0』，数字1应为『1 fingers=1』")


def stop():
    """停止预览并释放摄像头（overlay 保持加载，下次 launch 直接复用）。"""
    _state["on"] = False


if __name__ == "__main__":
    launch()
