"""Read dynamic results from PYNQ and speak them with Windows Speech."""

import json
import subprocess
import time
from pathlib import Path

REMOTE = "xilinx@192.168.2.99:/home/xilinx/sign-language-pynq/report/latest_dynamic_result.json"
LOCAL = Path("report/latest_dynamic_result.json")
KEY = Path.home() / ".ssh" / "pynq_nopass_ed25519"
MIN_CONFIDENCE = 0.30
LOCAL.parent.mkdir(parents=True, exist_ok=True)


def speak(text):
    # Text comes from the project's fixed label map, not arbitrary user input.
    safe = str(text).replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; "
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$s.Rate=0; $s.Volume=100; "
        f"$s.Speak('{safe}')"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


last_label = None
last_time = 0.0
print(f"动态语音监听已启动，置信度阈值={MIN_CONFIDENCE:.2f}，按 Ctrl+C 退出。")

while True:
    try:
        scp_cmd = ["scp", "-q"]
        if KEY.exists():
            scp_cmd.extend(["-i", str(KEY)])
        scp_cmd.extend([REMOTE, str(LOCAL)])
        subprocess.run(
            scp_cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=True,
        )
        data = json.loads(LOCAL.read_text(encoding="utf-8"))
        result = data["result"]
        label = result["label"]
        text = result["text"]
        confidence = float(result["confidence"])
        print(f"label={label} text={text} confidence={confidence:.3f}")

        now = time.time()
        if label != "unknown" and confidence >= MIN_CONFIDENCE:
            if label != last_label or now - last_time >= 3.0:
                print(f"播报: {text}")
                speak(text)
                last_label = label
                last_time = now
    except Exception as exc:
        print(f"等待板卡结果: {exc}")
    time.sleep(0.25)
