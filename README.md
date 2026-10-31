# PYNQ-Z2 手势识别与语音播报

当前正式作品使用 PYNQ-Z2、Logitech C270 USB 摄像头和 PS/PL 协同实现静态手势识别。PL 完成 YCrCb 肤色分割及 5×5 开闭运算，PS 完成轮廓特征、模板分类、稳定确认、产品界面和中文语音播报。

## 正式演示链路

```text
Logitech C270 USB camera
  -> AXI DMA
  -> PL: BGR/YCrCb + skin threshold + morphology
  -> PS: contour + fingertip/geometric features
  -> sign_templates.json classification
  -> stable confirmation
  -> Voilà live image + binary mask + text + browser WAV
```

正式识别类别：数字 1–5、点赞、停止。动态手势和旧模型路线已移入外部归档，不属于当前正式展示。

## 核心文件

- `hls/skin_morph.cpp`：PL 图像预处理 HLS 顶层
- `vivado_proj/`：当前 Vivado 工程
- `skin_morph.bit/.hwh`：正式 Overlay 配对
- `pl_hand_seg.py`：PYNQ Overlay 与 DMA 驱动
- `pynq_sign_language.py`：轮廓特征和静态模板分类核心
- `sign_templates.json`：静态模板与拒识阈值
- `board_static_demo.py`：低延迟静态产品入口
- `product_display.py`：真实图、二值图和文字布局
- `board_voice.py`：浏览器 WAV 播放支持
- `static_product.ipynb`：Voilà 独立产品页面
- `board/voice/`：数字、点赞和停止语音素材
- `submission/`：竞赛提交报告、测试模板和打包工具
- `skill/`：通用 PYNQ Overlay/DMA 验证 Skill

## PC 环境

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python verify_templates.py
```

重新生成模板：

```powershell
python evaluate_features.py --dataset dataset\raw_static_aug_v1 --out sign_templates.json
```

## 板端部署

默认部署到独立目录 `/home/xilinx/jupyter_notebooks/sign_demo_v2`，不覆盖旧项目。

```powershell
$env:PYNQ_HOST = "192.168.2.99"
$env:PYNQ_USER = "xilinx"
$env:PYNQ_PASSWORD = "你的板卡密码"
python deploy_board.py
```

不要把密码写入源码或提交到 Git。也可设置 `PYNQ_SSH_KEY` 使用密钥。

## 启动产品页

浏览器访问 `http://192.168.2.99:9090`，打开 `sign_demo_v2/static_product.ipynb`，点击 Voilà。

手动启动：

```python
import board_static_demo
board_static_demo.launch(
    width=640, height=480,
    stable=4, release=3,
    display_fps=8, jpeg_quality=65,
    wb_strength=0.2,
)
```

## 验证

```powershell
python verify_templates.py
python submission\scripts\validate_submission.py --root .
python skill\pynq-overlay-validation\scripts\verify_overlay_pair.py skin_morph.bit skin_morph.hwh
```

真实板端性能、最终 Vivado 资源和独立准确率按 `submission/TBD_CHECKLIST.md` 补测。

## 归档

2026-10-31 清理出的动态实验、旧 HOG/RandomForest 路线、OV5640 路线、历史板端报告和旧 FPGA 工程位于：

```text
D:\PYNQ\projects\sign-language-pynq-archive-20261031
```

归档目录中的 `archive_manifest.json` 记录移动与删除范围，可用于恢复历史实验。

## 许可证

源代码采用 MIT License，详见 `LICENSE`。
