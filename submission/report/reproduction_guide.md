# 从零复现说明

## 1. 硬件与软件

- PYNQ-Z2（XC7Z020-CLG400-1）
- Logitech C270 USB 摄像头
- PYNQ 3.1.1 镜像
- Vivado/Vitis 2026.1
- Windows PC，Python 3.10 或 3.11

## 2. PC 环境

```powershell
git clone https://github.com/ruixs1103/pynq-sign-language.git
cd pynq-sign-language
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python verify_templates.py
```

当前公开仓库提交为 `f6fed74cae54287d16771438421bd6666ccf538b`。

## 3. 重建 HLS IP

在 Vitis HLS 2026.1 中以 `hls/skin_morph.cpp` 为顶层源码，目标器件设为 `xc7z020clg400-1`，时钟周期设为 10 ns。优先使用仓库内现有 Tcl；正式提交前记录实际命令：

```text
本次提交保留已有 HLS 工程与测试台；未在本轮重新执行 HLS 批处理构建。
```

综合后核对 AXI-Lite 地址与 `pl_hand_seg.py` 一致，并导出 IP repository。

## 4. 重建 Vivado Overlay

打开 `vivado_proj/sign_pl.xpr` 或执行最终 Tcl：

```text
本次使用仓库中已验证的 bit/hwh 配对完成板端运行；未在本轮重新执行 Vivado 批处理构建。
```

生成 bitstream 后同时导出 `.bit` 与 `.hwh`，二者必须来自同一构建。运行 `skill/pynq-overlay-validation/scripts/verify_overlay_pair.py` 做静态校验。

## 5. 部署到新目录

不要覆盖板端已有项目：

```powershell
ssh xilinx@192.168.2.99 "mkdir -p /home/xilinx/jupyter_notebooks/sign_demo_v2"
scp board_deploy.zip xilinx@192.168.2.99:/home/xilinx/jupyter_notebooks/sign_demo_v2/
ssh xilinx@192.168.2.99 "cd /home/xilinx/jupyter_notebooks/sign_demo_v2 && unzip -o board_deploy.zip"
```

## 6. 环境和摄像头检查

```powershell
ssh xilinx@192.168.2.99 "lsusb && ls -l /dev/video*"
ssh xilinx@192.168.2.99 "cd /home/xilinx/jupyter_notebooks/sign_demo_v2 && /usr/local/share/pynq-venv/bin/python3 camera_board_test.py"
```

## 7. 启动正式静态产品页

浏览器打开 `http://192.168.2.99:9090`，进入 `sign_demo_v2/static_product.ipynb`，点击 Voilà。产品入口配置为 640×480、显示 8 FPS、JPEG 质量 65、白平衡强度 0.2。

## 8. 停止与关机

先点击“停止识别”释放摄像头，再关闭 Voilà/Notebook。通过交互式 SSH 执行：

```bash
sudo shutdown -h now
```

等待至少 30 秒后再断电和拔摄像头。

## 9. 最终复现验收

- 已在板端独立目录 `sign_demo_v2` 完成启动、识别、语音和安全关机流程。
- 操作日期：2026-10-31；提交 SHA：`f6fed74cae54287d16771438421bd6666ccf538b`。
- 保留板端测试记录、产品页截图和测试 JSON 作为工程证据。
