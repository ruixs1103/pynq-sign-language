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

若仓库尚未推送最终提交版本，应先完成 `TBD-TEST`：记录最终 commit SHA 和公开 release URL。

## 3. 重建 HLS IP

在 Vitis HLS 2026.1 中以 `hls/skin_morph.cpp` 为顶层源码，目标器件设为 `xc7z020clg400-1`，时钟周期设为 10 ns。优先使用仓库内现有 Tcl；正式提交前记录实际命令：

```text
TBD-TEST: 最终可复现 HLS Tcl 路径与命令
```

综合后核对 AXI-Lite 地址与 `pl_hand_seg.py` 一致，并导出 IP repository。

## 4. 重建 Vivado Overlay

打开 `vivado_proj/sign_pl.xpr` 或执行最终 Tcl：

```text
TBD-TEST: 最终 Vivado batch build 命令
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

- `TBD-TEST`：从全新 SD 卡/新目录完整复现一次。
- `TBD-TEST`：记录操作者、日期、commit SHA、板卡序列或资产编号。
- `TBD-TEST`：保存终端日志、产品页截图和测试 JSON。
