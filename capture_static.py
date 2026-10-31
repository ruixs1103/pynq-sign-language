# -*- coding: utf-8 -*-
"""静态手势采集：给 number_6(点赞) / number_7(停止) 补训练图。

流程（手动触发式）：
    按空格 -> 等待 WAIT 秒(摆好姿势) -> 连续拍 SHOT 秒 -> 自动停 -> 等下一次触发

    python capture_static.py                 # 默认采第 7 类(停止)
    python capture_static.py --wait 2 --shot 2
    python capture_static.py --count 80      # 每类目标张数

按键： 空格=触发一次采集  6/7=切换类别  d=删最后一张  D=删最后一组  q=退出
存盘： dataset/dataset/raw_static_aug_v1/number_X/number_X_<时间戳>_<序号>.jpg
"""
import argparse
import os
import queue
import sys
import threading
import time

import cv2

from pynq_sign_language import HandSeg, count_fingertips

OUT_ROOT = os.path.join("dataset", "dataset", "raw_static_aug_v1")
NAME = {"6": "thumbs-up", "7": "stop"}
CN = {"6": "点赞(竖拇指)", "7": "停止(食指顶掌心)"}
TIP = {"6": "拇指明显外撇，与拳头拉开空隙",
       "7": "食指指尖压紧另一手掌心，两手要连成一块"}
WIN = "capture static - [SPACE]trigger [6/7]class [d]del [D]del-group [q]quit"

IDLE, WAIT, SHOT = 0, 1, 2


def ansi_view(frame, cols, rows, cnt=None):
    """把一帧画成终端里的彩色半块字符画（truecolor ANSI，无需图形界面）。

    用 '▀' 上半块：前景色=上一行像素，背景色=下一行像素，
    一个字符塞 2 行像素，所以 rows 行字符 = 2*rows 行图像。
    """
    vis = frame.copy()
    if cnt is not None:
        cv2.drawContours(vis, [cnt], -1, (0, 255, 0), 2)
    small = cv2.resize(vis, (cols, rows * 2), interpolation=cv2.INTER_AREA)
    out = []
    for y in range(rows):
        top, bot = small[2 * y], small[2 * y + 1]
        pf = pb = None
        line = []
        for x in range(cols):
            tr, tg, tb = int(top[x][2]), int(top[x][1]), int(top[x][0])
            br, bg, bb = int(bot[x][2]), int(bot[x][1]), int(bot[x][0])
            if (tr, tg, tb) != pf:
                line.append("\x1b[38;2;%d;%d;%dm" % (tr, tg, tb))
                pf = (tr, tg, tb)
            if (br, bg, bb) != pb:
                line.append("\x1b[48;2;%d;%d;%dm" % (br, bg, bb))
                pb = (br, bg, bb)
            line.append("\u2580")
        line.append("\x1b[0m")
        out.append("".join(line))
    return "\n".join(out)


def overlay(frame, cnt, tips, label, saved, target, ratio, st, left, nbatch):
    vis = frame.copy()
    if cnt is not None:
        cv2.drawContours(vis, [cnt], -1, (0, 255, 0), 2)
        for t in tips:
            cv2.circle(vis, t, 5, (0, 0, 255), -1)

    cv2.putText(vis, "[%s] %s" % (label, CN[label]), (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 255), 2)
    cv2.putText(vis, TIP[label], (10, 56), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (180, 255, 180), 1)

    col = (0, 255, 0) if 0.15 <= ratio <= 0.60 else (0, 60, 255)
    cv2.putText(vis, "area %.0f%%  (want 15-60%%)" % (100 * ratio), (10, 82),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)

    if st == IDLE:
        msg, mcol = "READY  - press SPACE to capture", (200, 200, 200)
    elif st == WAIT:
        msg, mcol = "GET READY  %.1f s" % left, (0, 255, 255)
    else:
        msg, mcol = "RECORDING  %.1f s" % left, (0, 60, 255)
    cv2.putText(vis, msg, (10, 112), cv2.FONT_HERSHEY_SIMPLEX, 0.8, mcol, 2)

    cv2.putText(vis, "saved %d/%d   (last group %d)" % (saved, target, nbatch),
                (10, 140), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
    cv2.putText(vis, "SPACE trigger  6/7 class  d del  D del-group  q quit",
                (10, vis.shape[0] - 12), cv2.FONT_HERSHEY_SIMPLEX,
                0.5, (200, 200, 200), 1)
    return vis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=60, help="每类目标张数")
    ap.add_argument("--wait", type=float, default=2.0, help="触发后等待摆姿势秒数")
    ap.add_argument("--shot", type=float, default=2.0, help="连续拍照秒数")
    ap.add_argument("--save-fps", type=float, default=10.0,
                    help="拍照期间每秒存几张(避免存到几乎一样的帧)")
    ap.add_argument("--camera", type=int, default=0)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--min-area", type=float, default=0.10,
                    help="手部占比下限，低于则丢弃该帧")
    ap.add_argument("--max-area", type=float, default=0.60)
    ap.add_argument("--headless", action="store_true",
                    help="不开窗口，用终端按键控制(板端/SSH 用这个)")
    ap.add_argument("--ascii", action="store_true",
                    help="终端里直接显示摄像头画面(彩色字符画，无需图形界面)")
    ap.add_argument("--ascii-cols", type=int, default=56)
    ap.add_argument("--ascii-rows", type=int, default=16)
    ap.add_argument("--ascii-fps", type=float, default=12.0)
    args = ap.parse_args()
    if args.ascii:
        args.headless = True

    # 无界面模式：后台线程读键盘，主线程继续取帧
    keyq = queue.Queue()
    if args.headless:
        def _reader():
            try:
                import msvcrt                      # Windows
                while True:
                    if msvcrt.kbhit():
                        keyq.put(msvcrt.getwch())
                    time.sleep(0.05)
            except ImportError:                    # Linux / 板端
                import select
                import tty
                import termios
                fd = sys.stdin.fileno()
                old = termios.tcgetattr(fd)
                tty.setcbreak(fd)
                try:
                    while True:
                        r, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if r:
                            keyq.put(sys.stdin.read(1))
                finally:
                    termios.tcsetattr(fd, termios.TCSADRAIN, old)
        threading.Thread(target=_reader, daemon=True).start()
        print("无界面模式：回车=采集  d=删最后一张  D=删最后一组  q=退出")

    seg = HandSeg()
    cap = cv2.VideoCapture(args.camera)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    if not cap.isOpened():
        print("摄像头打不开")
        return 1

    def n_exist(lab):
        d = os.path.join(OUT_ROOT, "number_" + lab)
        return len([f for f in os.listdir(d)
                    if f.lower().endswith((".jpg", ".png"))]) \
            if os.path.isdir(d) else 0

    saved = {"6": n_exist("6"), "7": n_exist("7")}
    label = "7"
    st, t_end = IDLE, 0.0
    t_next_save = 0.0
    last_print = 0.0
    all_saved = []          # 本次运行存下的所有文件(按时间顺序)
    last_batch = []         # 最近一次触发存下的那组

    print("目标目录: %s" % OUT_ROOT)
    print("当前类别: 【%s】 %s" % (label, CN[label]))
    print("  要领: %s" % TIP[label])
    print("流程: 空格 -> 等 %.1f 秒摆姿势 -> 拍 %.1f 秒 -> 自动停\n"
          % (args.wait, args.shot))

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        # 居中裁正方形，对齐现有 360x360 方形裁剪的构图风格
        fh, fw = frame.shape[:2]
        s = min(fh, fw)
        frame = frame[(fh - s) // 2:(fh + s) // 2, (fw - s) // 2:(fw + s) // 2]
        cnt, mask = seg(frame)
        tips = count_fingertips(cnt)[1] if cnt is not None else []
        area = float(cv2.contourArea(cnt)) if cnt is not None else 0.0
        ratio = area / float(frame.shape[0] * frame.shape[1])

        now = time.time()

        if st == WAIT and now >= t_end:
            st, t_end = SHOT, now + args.shot
            t_next_save, last_batch = 0.0, []
            print("  >>> 开始拍 %.1f 秒，轻微变换角度/位置" % args.shot)

        # 必须在状态切换之后才算剩余时间，否则开拍那一帧会被当成"已拍完"
        left = max(0.0, t_end - now) if st != IDLE else 0.0

        if st == SHOT:
            good = cnt is not None and args.min_area <= ratio <= args.max_area
            if good and now >= t_next_save:
                d = os.path.join(OUT_ROOT, "number_" + label)
                os.makedirs(d, exist_ok=True)
                fn = "number_%s_%s_%03d.jpg" % (
                    label, time.strftime("%Y%m%d_%H%M%S"), saved[label])
                cv2.imwrite(os.path.join(d, fn), frame)
                saved[label] += 1
                all_saved.append(os.path.join(d, fn))
                last_batch.append(os.path.join(d, fn))
                t_next_save = now + 1.0 / max(0.5, args.save_fps)
                if not args.ascii:      # 字符画模式下不打逐帧日志，免得冲掉画面
                    print("  [%s] %s  area=%.0f%%"
                          % (label, fn, 100 * ratio))
            if left <= 0:
                print("  <<< 本次拍完：%d 张（%s 累计 %d）"
                      % (len(last_batch), CN[label], saved[label]))
                st = IDLE

        if args.headless:
            # 无界面：状态打终端（可选彩色字符画），按键从 stdin 读
            if args.ascii:
                if now - last_print >= 1.0 / max(1.0, args.ascii_fps):
                    last_print = now
                    if st == IDLE:
                        msg = ("待命 | %s 已存 %d/%d | 回车=采集 d=删1张 "
                               "D=删整组 q=退出"
                               % (CN[label], saved[label], args.count))
                    elif st == WAIT:
                        msg = ">>> 摆好姿势 %.1f s ..." % left
                    else:
                        msg = "*** 拍摄中 %.1f s ...（轻微变换角度）" % left
                    sys.stdout.write(
                        "\x1b[H" + ansi_view(frame, args.ascii_cols,
                                             args.ascii_rows, cnt)
                        + "\n\x1b[0m" + msg + "\x1b[0J\n")
                    sys.stdout.flush()
            else:
                if st == IDLE:
                    if now - last_print > 0.5:
                        last_print = now
                        print("  待命 | %s 已存 %d/%d | 回车=采集 d=删1张 D=删整组 "
                              "q=退出" % (CN[label], saved[label], args.count))
                elif now - last_print > 0.5:
                    last_print = now
                    print("  %s %.1fs ..."
                          % ("摆好姿势" if st == WAIT else "拍摄中", left))
            try:
                k = ord(keyq.get_nowait())
            except Exception:
                k = -1
            if k in (13, 10):          # 回车
                k = ord(" ")
        else:
            cv2.imshow(WIN, overlay(frame, cnt, tips, label, saved[label],
                                    args.count, ratio, st, left,
                                    len(last_batch)))
            k = cv2.waitKey(1) & 0xFF
        if k == ord("q"):
            break
        if k in (ord("6"), ord("7")):
            label = chr(k)
            st = IDLE
            print(">>> 切换到【%s】 %s" % (CN[label], TIP[label]))
        elif k == ord(" "):
            if st == IDLE:
                if saved[label] >= args.count:
                    print("  %s 已达 %d 张，不再采集" % (CN[label], args.count))
                else:
                    st, t_end = WAIT, time.time() + args.wait
                    print(">>> 触发：%.1f 秒后开拍，摆好姿势" % args.wait)
            else:
                st = IDLE
                print(">>> 已取消本次采集")
        elif k == ord("d"):
            if all_saved:
                p = all_saved.pop()
                try:
                    os.remove(p)
                except OSError:
                    pass
                if p in last_batch:
                    last_batch.remove(p)
                lab = os.path.basename(p).split("_")[1]
                saved[lab] = max(0, saved[lab] - 1)
                print("  已删最后一张 %s（%s 剩 %d）"
                      % (os.path.basename(p), CN.get(lab, lab), saved[lab]))
        elif k == ord("D"):
            if last_batch:
                n = len(last_batch)
                for p in last_batch:
                    try:
                        os.remove(p)
                    except OSError:
                        pass
                    if p in all_saved:
                        all_saved.remove(p)
                lab = os.path.basename(last_batch[0]).split("_")[1]
                saved[lab] = max(0, saved[lab] - n)
                last_batch = []
                print("  已删最后一组 %d 张（%s 剩 %d）"
                      % (n, CN.get(lab, lab), saved[lab]))

    cap.release()
    cv2.destroyAllWindows()
    print("\n采集汇总:")
    for k in ("6", "7"):
        print("  number_%s  %d 张   (%s)" % (k, n_exist(k), CN[k]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
