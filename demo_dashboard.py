"""Single-window product demo for the PYNQ-Z2 sign-language pipeline."""

import json
import subprocess
import time
from pathlib import Path

import cv2

REMOTE_BASE = "xilinx@192.168.2.99:/home/xilinx/sign-language-pynq/report/"
KEY = Path.home() / ".ssh" / "pynq_nopass_ed25519"
LOCAL = Path("report/dashboard")
LOCAL.mkdir(parents=True, exist_ok=True)
MIN_CONFIDENCE = 0.30


def scp(name):
    cmd = ["scp", "-q"]
    if KEY.exists():
        cmd += ["-i", str(KEY)]
    cmd += [REMOTE_BASE + name, str(LOCAL / name)]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                   timeout=3, check=True)


def speak(text):
    safe = str(text).replace("'", "''")
    ps = ("Add-Type -AssemblyName System.Speech; "
          "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          "$s.Volume=100; "
          f"$s.Speak('{safe}')")
    subprocess.Popen(["powershell.exe", "-NoProfile", "-Command", ps],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


last_label = None
last_spoken = 0.0
last_count = None
last_tick = time.time()
fps = 0.0
print("产品展示已启动，按 q 退出。")

while True:
    try:
        scp("latest_dynamic_result.json")
        scp("latest_dynamic_frame.jpg")
        try:
            data = json.loads((LOCAL / "latest_dynamic_result.json").read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            time.sleep(0.05)
            continue
        frame = cv2.imread(str(LOCAL / "latest_dynamic_frame.jpg"))
        if frame is None:
            raise RuntimeError("latest_dynamic_frame.jpg 无法读取")

        result = data.get("result", {})
        label = result.get("label", "unknown")
        text = result.get("text", "未知")
        confidence = float(result.get("confidence", 0.0))
        count = data.get("count")
        backend = str(data.get("backend", "cpu")).upper()
        error_text = str(data.get("scores", {}).get("error", ""))
        now = time.time()
        if last_count is not None and count != last_count:
            dt = now - last_tick
            if dt > 0:
                fps = 1.0 / dt
            last_tick = now
        last_count = count

        color = (0, 220, 0) if label != "unknown" and confidence >= MIN_CONFIDENCE else (0, 180, 255)
        cv2.rectangle(frame, (0, 0), (frame.shape[1], 118), (20, 20, 20), -1)
        cv2.putText(frame, f"Gesture: {text} ({label})", (16, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.72, color, 2, cv2.LINE_AA)
        cv2.putText(frame, f"Confidence: {confidence:.2f}   FPS: {fps:.1f}", (16, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, f"Preprocess: {backend}   Classifier: ARM PS   Audio: PC", (16, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.48, (180, 220, 255), 1, cv2.LINE_AA)
        if error_text:
            cv2.putText(frame, "Inference error: " + error_text[:70], (16, 112),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 80, 255), 1, cv2.LINE_AA)
        cv2.putText(frame, "q: quit", (16, 132), cv2.FONT_HERSHEY_SIMPLEX, 0.42,
                    (180, 180, 180), 1, cv2.LINE_AA)
        cv2.imshow("PYNQ-Z2 Sign Language Product Demo", frame)

        if label != "unknown" and confidence >= MIN_CONFIDENCE:
            if label != last_label or now - last_spoken >= 3.0:
                speak(text)
                last_label, last_spoken = label, now
    except Exception as exc:
        print(f"等待板卡结果: {exc}")

    if cv2.waitKey(1) & 0xFF in (ord("q"), ord("Q"), 27):
        break
    time.sleep(0.25)

cv2.destroyAllWindows()
