# -*- coding: utf-8 -*-
"""一键把交付文件部署到 PYNQ 板端。

    py deploy_board.py              # 上传+解压+同步到Jupyter目录+自检
    py deploy_board.py              # 部署静态产品到独立 Jupyter 目录

板端两个坑（已在本脚本里处理，不要再手工 ssh 跑）：
  1. Jupyter 服务的是 /home/xilinx/jupyter_notebooks，不是 /home/xilinx
  2. 加载 PL 需要 root，且要登录 shell 才有 XRT 环境变量
"""
import argparse
import getpass
import os
import zipfile

import paramiko

HOME = "/home/xilinx"
JUP = "/home/xilinx/jupyter_notebooks/sign_demo_v2"
PY = "/usr/local/share/pynq-venv/bin/python3"
ROOT = os.path.dirname(os.path.abspath(__file__))
ZIP = os.path.join(ROOT, "board_deploy.zip")
FILES = ["pynq_sign_language.py", "sign_templates.json", "pl_hand_seg.py",
         "skin_morph.bit", "skin_morph.hwh", "board_voice.py",
         "board_static_demo.py", "product_display.py", "static_product.ipynb"]
VOICE = "voice"          # 语音素材子目录（board/voice/*.wav -> JUP/voice/）
BD = os.path.join(ROOT, "board")
SKIP = ("sign_templates.json.bak_20261024",)


def build_zip():
    """每次部署现打现传，避免用旧 zip 把新代码覆盖回旧版。"""
    items = []                                  # (本地绝对路径, zip 内名字)
    for f in FILES:
        p = os.path.join(ROOT, f)
        if not os.path.isfile(p):
            p = os.path.join(BD, f)
        if not os.path.isfile(p):
            raise FileNotFoundError("部署文件缺失: %s" % f)
        items.append((p, f))
    vd = os.path.join(BD, VOICE)                # 语音素材在子目录里
    if os.path.isdir(vd):
        for f in sorted(os.listdir(vd)):
            p = os.path.join(vd, f)
            if os.path.isfile(p):
                items.append((p, VOICE + "/" + f))
    with zipfile.ZipFile(ZIP, "w", zipfile.ZIP_DEFLATED) as z:
        for src, arc in items:
            z.write(src, arc)
    print("打包 %d 个文件: %s" % (len(items), ", ".join(a for _, a in items)))


def sh(cli, cmd, t=120, tag=True):
    if tag:
        print("$ " + cmd[:110])
    _, out, err = cli.exec_command(cmd, timeout=t)
    o = out.read().decode("utf-8", "replace").rstrip()
    e = err.read().decode("utf-8", "replace").rstrip()
    if o:
        print(o)
    if e:
        print("[err] " + e)
    return o, e


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=os.environ.get("PYNQ_HOST", "192.168.2.99"))
    ap.add_argument("--user", default=os.environ.get("PYNQ_USER", "xilinx"))
    ap.add_argument("--key", default=os.environ.get("PYNQ_SSH_KEY", ""))
    ap.add_argument(
        "--ask-password",
        action="store_true",
        help="交互输入 SSH/sudo 密码；也可设置 PYNQ_PASSWORD",
    )
    return ap.parse_args()


def main():
    args = parse_args()
    password = os.environ.get("PYNQ_PASSWORD")
    if args.ask_password and not password:
        password = getpass.getpass("PYNQ SSH password: ")

    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect = {"hostname": args.host, "username": args.user, "timeout": 15}
    if password:
        connect["password"] = password
    if args.key:
        connect["key_filename"] = os.path.expanduser(args.key)
    cli.connect(**connect)
    build_zip()
    sftp = cli.open_sftp()

    print("\n=== 上传 ===")
    sftp.put(ZIP, HOME + "/board_deploy.zip")
    sftp.close()
    sh(cli, "ls -la %s/board_deploy.zip" % HOME)

    print("\n=== 解压到 /home/xilinx ===")
    sh(cli, "cd %s && unzip -o board_deploy.zip >/dev/null && echo '解压完成'" % HOME)

    print("\n=== 同步到 Jupyter 服务目录 ===")
    sh(cli, "mkdir -p %s && cd %s && cp -f %s . && ls -la %s" % (
        JUP, JUP, " ".join("%s/%s" % (HOME, f) for f in FILES), " ".join(FILES)),
        tag=False)
    print("  (已复制 %d 个文件到 %s)" % (len(FILES), JUP))

    print("\n=== 同步语音素材到 %s/ ===" % JUP)
    if os.path.isdir(os.path.join(BD, VOICE)):
        sh(cli, "mkdir -p %s/%s && cp -f %s/%s/*.wav %s/%s/ && ls -1 %s/%s"
           % (JUP, VOICE, HOME, VOICE, JUP, VOICE, JUP, VOICE))
    else:
        print("  (本地没有 board/%s 目录，跳过)" % VOICE)

    print("\n=== 板端静态产品自检 ===")
    sh(cli, "cd %s && %s -m py_compile pynq_sign_language.py pl_hand_seg.py "
       "board_voice.py board_static_demo.py product_display.py" % (JUP, PY))

    cli.close()
    print("\n[完成] 打开 static_product.ipynb 并点击 Voilà。")


if __name__ == "__main__":
    main()
