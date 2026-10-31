# -*- coding: utf-8 -*-
"""Jupyter Notebook 专用采集界面：实时画面 + 按钮手动触发/删除。

用法（notebook 单元格里）：

    from capture_nb import CaptureUI
    ui = CaptureUI()          # 默认采第 7 类(停止)
    ui.show()

界面：
    [实时画面]
    [采集] 触发一次：等 2 秒摆姿势 -> 拍 2 秒 -> 自动停
    [删除上一张]  不满意的单张
    [删除上一组]  刚拍的整批
    [类别切换]    7=停止 / 6=点赞
    [结束]       关掉相机释放资源
"""
import os
import threading
import time

import cv2
import numpy as np

import ipywidgets as widgets
from IPython.display import display

from pynq_sign_language import HandSeg, count_fingertips

OUT_ROOT = os.path.join("dataset", "dataset", "raw_static_aug_v1")
CN = {"6": "点赞(竖拇指)", "7": "停止(食指顶掌心)"}
TIP = {"6": "拇指明显外撇，与拳头拉开空隙",
       "7": "食指指尖压紧另一手掌心，两手要连成一块"}

IDLE, WAIT, SHOT = 0, 1, 2


class CaptureUI(object):
    def __init__(self, camera=0, wait=2.0, shot=2.0, save_fps=10.0,
                 label="7", count=200, width=640, height=480,
                 min_area=0.10, max_area=0.60, out=OUT_ROOT, fps=20,
                 use_pl=False, bit="skin_morph.bit", seg_fps=4.0,
                 disp_w=480, disp_h=360):
        """use_pl=True 用 FPGA 分割(93ms)；seg_fps 限制待机时的分割频率。

        待机(非采集)时按 seg_fps 做分割，画面走纯相机帧，所以实时预览很流畅；
        一旦触发采集，自动切回逐帧分割，保证存下来的每张都过了面积校验。
        """
        self.wait, self.shot, self.save_fps = wait, shot, save_fps
        self.count, self.min_area, self.max_area = count, min_area, max_area
        self.out = out
        self.fps = fps
        self.seg_fps = seg_fps
        self.disp_w, self.disp_h = disp_w, disp_h
        self.cnt_cache = None
        self.t_last_seg = 0.0

        self.cap = cv2.VideoCapture(camera)
        if not self.cap.isOpened():
            raise RuntimeError("摄像头 %d 打不开" % camera)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        self.seg = self._make_seg(use_pl, bit)

        self.label = label
        self.st, self.t_end, self.t_next = IDLE, 0.0, 0.0
        self.all_saved, self.last_batch = [], []
        self.saved = {"6": self._n("6"), "7": self._n("7")}
        self.lock = threading.Lock()
        self.running = True
        self.msg = "就绪"

        # ---- 界面 ----
        self.img = widgets.Image(format="jpeg", width=480)
        self.html = widgets.HTML(value="<b>初始化...</b>")
        self.b_shot = widgets.Button(description="采集(等%.0f秒→拍%.0f秒)"
                                     % (wait, shot), button_style="primary")
        self.b_del1 = widgets.Button(description="删除上一张")
        self.b_delg = widgets.Button(description="删除上一组",
                                     button_style="warning")
        self.b_cls = widgets.ToggleButtons(
            options=[("停止(7)", "7"), ("点赞(6)", "6")], value=label,
            description="类别:")
        self.b_stop = widgets.Button(description="结束",
                                     button_style="danger")
        self.b_shot.on_click(self._on_shot)
        self.b_del1.on_click(self._on_del1)
        self.b_delg.on_click(self._on_delg)
        self.b_stop.on_click(self._on_stop)
        self.b_cls.observe(self._on_cls, names="value")
        self.ui = widgets.VBox([
            self.img, self.html,
            widgets.HBox([self.b_shot, self.b_del1, self.b_delg, self.b_stop]),
            self.b_cls,
        ])
        self.thread = threading.Thread(target=self._loop, daemon=True)

    @staticmethod
    def _make_seg(use_pl, bit):
        if not use_pl:
            return HandSeg()
        try:
            import pynq
            from pl_hand_seg import PlHandSeg
            ol = pynq.Overlay(bit)
            print("[PL] 已加载 %s，分割走 FPGA" % bit)
            return PlHandSeg(ol, rows=480, cols=640, use_wb=True)
        except Exception as e:
            print("[PL] 加载失败(%s)，回退到软件分割" % e)
            return HandSeg()

    # ---------------- 数据 ----------------
    def _n(self, lab):
        d = os.path.join(self.out, "number_" + lab)
        return len([f for f in os.listdir(d)
                    if f.lower().endswith((".jpg", ".png"))]) \
            if os.path.isdir(d) else 0

    def _on_cls(self, ch):
        self.label = ch["new"]
        self.st = IDLE
        self.msg = "切换到【%s】 %s" % (CN[self.label], TIP[self.label])

    def _on_shot(self, _=None):
        if self.st != IDLE:
            self.st, self.msg = IDLE, "已取消本次采集"
            return
        if self.saved[self.label] >= self.count:
            self.msg = "%s 已达 %d 张" % (CN[self.label], self.count)
            return
        self.st, self.t_end = WAIT, time.time() + self.wait
        self.last_batch = []
        self.msg = "%.0f 秒后开拍，摆好姿势" % self.wait

    def _on_del1(self, _=None):
        with self.lock:
            if not self.all_saved:
                self.msg = "没有可删的图"
                return
            p = self.all_saved.pop()
            try:
                os.remove(p)
            except OSError:
                pass
            if p in self.last_batch:
                self.last_batch.remove(p)
            lab = os.path.basename(p).split("_")[1]
            self.saved[lab] = max(0, self.saved[lab] - 1)
            self.msg = "已删最后一张 %s（%s 剩 %d）" % (
                os.path.basename(p), CN.get(lab, lab), self.saved[lab])

    def _on_delg(self, _=None):
        with self.lock:
            if not self.last_batch:
                self.msg = "没有可删的组"
                return
            n = len(self.last_batch)
            for p in self.last_batch:
                try:
                    os.remove(p)
                except OSError:
                    pass
                if p in self.all_saved:
                    self.all_saved.remove(p)
            lab = os.path.basename(self.last_batch[0]).split("_")[1]
            self.saved[lab] = max(0, self.saved[lab] - n)
            self.last_batch = []
            self.msg = "已删最后一组 %d 张（%s 剩 %d）" % (
                n, CN.get(lab, lab), self.saved[lab])

    def _on_stop(self, _=None):
        self.running = False
        self.msg = "已结束"

    # ---------------- 主循环 ----------------
    def _loop(self):
        while self.running:
            ok, frame = self.cap.read()
            if not ok or frame is None:
                time.sleep(0.05)
                continue
            fh, fw = frame.shape[:2]
            s = min(fh, fw)
            frame = frame[(fh - s) // 2:(fh + s) // 2,
                          (fw - s) // 2:(fw + s) // 2]
            now = time.time()
            # 待机按 seg_fps 节流（画面照常流畅刷新）；采集时逐帧分割
            busy = self.st != IDLE
            if busy or now - self.t_last_seg >= 1.0 / max(0.5, self.seg_fps):
                self.t_last_seg = now
                cnt, _ = self.seg(frame)
                self.cnt_cache = cnt
            else:
                cnt = self.cnt_cache
            area = float(cv2.contourArea(cnt)) if cnt is not None else 0.0
            ratio = area / float(frame.shape[0] * frame.shape[1])

            if self.st == WAIT and now >= self.t_end:
                self.st, self.t_end = SHOT, now + self.shot
                self.t_next = 0.0
                self.msg = "拍摄中，轻微变换角度/位置"
            left = max(0.0, self.t_end - now) if self.st != IDLE else 0.0

            if self.st == SHOT:
                good = cnt is not None and self.min_area <= ratio <= self.max_area
                if good and now >= self.t_next:
                    d = os.path.join(self.out, "number_" + self.label)
                    os.makedirs(d, exist_ok=True)
                    fn = "number_%s_%s_%03d.jpg" % (
                        self.label, time.strftime("%Y%m%d_%H%M%S"),
                        self.saved[self.label])
                    cv2.imwrite(os.path.join(d, fn), frame)
                    self.saved[self.label] += 1
                    self.all_saved.append(os.path.join(d, fn))
                    self.last_batch.append(os.path.join(d, fn))
                    self.t_next = now + 1.0 / max(0.5, self.save_fps)
                if left <= 0:
                    self.msg = ("本次拍完 %d 张（%s 累计 %d）"
                                % (len(self.last_batch), CN[self.label],
                                   self.saved[self.label]))
                    self.st = IDLE

            # ---- 画面 + 状态 ----
            vis = frame.copy()
            if cnt is not None:
                cv2.drawContours(vis, [cnt], -1, (0, 255, 0), 2)
            col = (0, 255, 0) if self.min_area <= ratio <= self.max_area \
                else (0, 60, 255)
            cv2.putText(vis, "[%s] %s" % (self.label, CN[self.label]),
                        (10, 26), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
            cv2.putText(vis, "area %.0f%% (want %d-%d%%)"
                        % (100 * ratio, int(self.min_area * 100),
                           int(self.max_area * 100)),
                        (10, 52), cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
            if self.st == WAIT:
                cv2.putText(vis, "GET READY %.1f" % left, (10, 84),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
            elif self.st == SHOT:
                cv2.putText(vis, "RECORDING %.1f" % left, (10, 84),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 60, 255), 2)
            disp = cv2.resize(vis, (self.disp_w, self.disp_h),
                              interpolation=cv2.INTER_AREA)
            ok2, buf = cv2.imencode(".jpg", disp,
                                    [int(cv2.IMWRITE_JPEG_QUALITY), 70])
            if ok2:
                self.img.value = buf.tobytes()
            self.html.value = (
                "<b>%s</b> ｜ 已存 <b>%d</b>/%d ｜ 本组 %d 张 ｜ %s"
                % (CN[self.label], self.saved[self.label], self.count,
                   len(self.last_batch), self.msg))
            time.sleep(1.0 / max(1.0, self.fps))
        self.cap.release()
        self.html.value = "<b>已结束</b> ｜ %s %d 张 ｜ %s %d 张" % (
            CN["6"], self._n("6"), CN["7"], self._n("7"))

    # ---------------- 启动 ----------------
    def show(self):
        display(self.ui)
        if not self.thread.is_alive():
            self.thread.start()
        return self


def start(**kw):
    return CaptureUI(**kw).show()
