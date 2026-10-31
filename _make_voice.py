# -*- coding: utf-8 -*-
"""用 PC 端离线中文 TTS(Microsoft Huihui zh-CN) 生成语音素材 -> board/voice/*.wav

板端没有任何声卡，也没有播放器，所以语音素材在 PC 上预先合成，
运行时由 notebook 单元格用隐藏的 <audio> 标签播放（声音从 PC 浏览器出来）。
"""
import os
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))
VD = os.path.join(ROOT, "board", "voice")
VOICE = "Microsoft Huihui Desktop"

# 逐位念 + 即时反馈所需的全部短语
PHRASES = {
    "wake":   "请比出数字",
    "stop":   "停止识别",
    "result": "识别结果",
    "empty":  "未识别到数字",
    "d1": "一", "d2": "二", "d3": "三", "d4": "四", "d5": "五",
    "thumbs_up": "点赞",
    "static_stop": "停止",
}


def main():
    os.makedirs(VD, exist_ok=True)
    ps1 = os.path.join(ROOT, "_gen_voice.ps1")
    lines = [
        "Add-Type -AssemblyName System.Speech",
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer",
        "$v = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture -eq 'zh-CN' }"
        " | Select-Object -First 1",
        "if ($v) { $s.SelectVoice($v.VoiceInfo.Name); Write-Host (' Using voice: ' + $v.VoiceInfo.Name) }"
        " else { Write-Host ' WARN: 未找到中文语音，将用默认语音' }",
    ]
    for name, text in PHRASES.items():
        out = os.path.join(VD, name + ".wav")
        lines.append("$s.SetOutputToWaveFile('%s')" % out)
        lines.append("$s.Speak('%s')" % text)
    lines.append("$s.Dispose()")
    with open(ps1, "w", encoding="utf-8-sig") as f:      # BOM 让 PS5.1 正确识别中文
        f.write("\n".join(lines) + "\n")

    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-File", ps1], capture_output=True, text=True, encoding="utf-8")
    if r.stdout.strip():
        print(r.stdout.strip())
    if r.returncode != 0:
        print("[err]", (r.stderr or "").strip())
        raise SystemExit(1)

    print("=== 生成结果 ===")
    ok = True
    for name in sorted(PHRASES):
        p = os.path.join(VD, name + ".wav")
        if os.path.exists(p):
            print("  %-8s %6d bytes   %r" % (name + ".wav", os.path.getsize(p), PHRASES[name]))
        else:
            print("  %-8s 缺失!" % name)
            ok = False
    os.remove(ps1)
    print("[完成] 素材目录: %s" % VD if ok else "[失败]")


if __name__ == "__main__":
    main()
