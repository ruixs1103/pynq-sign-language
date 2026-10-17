# PYNQ-Z2 手语识别系统

本项目是 FPGA 创新赛作品，目标是在 PYNQ-Z2 平台上实现手语识别系统。系统包含 PC 端算法原型、静态手势数据处理、板端实时推理、JSON 结果输出、电脑端中文语音播报，以及后续 FPGA/HLS 加速工程。

## 当前进度

- 已完成静态手势图像预处理流程
- 已完成 NumPy 轻量静态模型训练
- 已完成板端单张图片推理
- 已完成板端摄像头实时识别并输出 `latest_static_result.json`
- 已完成电脑端读取板端识别结果并进行中文语音播报
- 已建立 PYNQ-Z2 Vivado 基础工程和部分 Overlay 文件
- 待完善动态手势识别、数据集清洗、模型评估、FPGA 加速验证和答辩材料

## 识别类别

当前静态识别主流程面向数字手势与未知类别：

| 标签 | 含义 |
|---|---|
| `number_1` | 数字 1 |
| `number_2` | 数字 2 |
| `number_3` | 数字 3 |
| `number_4` | 数字 4 |
| `number_5` | 数字 5 |
| `unknown` | 其他动作或无有效手势 |

项目中仍保留早期 palm、fist、victory、ok、thumbs_up 等实验代码和归档内容，主要用于历史参考。

## 系统流程

```text
USB 摄像头
    ↓
图像采集
    ↓
肤色分割与形态学处理
    ↓
最大轮廓与手部 ROI 提取
    ↓
标准化二值图
    ↓
静态手势分类
    ↓
板端写出 JSON 结果
    ↓
电脑端读取结果并语音播报
```

计划由 PS 负责摄像头输入、系统控制和分类，由 PL 加速适合并行计算的图像处理模块。

## 主要脚本

- `labels.py`：统一标签、中文文本、结果格式
- `preprocess.py`：图像预处理，包含肤色分割、轮廓提取和二值图生成
- `batch_preprocess_signs.py`：批量处理静态手势图片
- `train_static_numpy_model.py`：训练板端可用的轻量 NumPy 静态模型
- `board_static_infer.py`：板端或本地单张静态手势推理
- `board_static_live_json.py`：板端摄像头实时识别并写出 JSON
- `pc_speak_static.py`：电脑端读取板端 JSON 并语音播报
- `audit_static_images.py`：筛查静态图片数据质量
- `dataset_manifest.py` / `dataset_audit.py`：生成和检查数据集清单
- `evaluate_dynamic_model.py` / `train_dynamic_model.py`：动态手势相关训练和评估脚本

## 开发环境

- 操作系统：Windows
- Python：建议 3.10 或 3.11
- OpenCV
- NumPy
- scikit-learn / joblib
- FPGA 工具：Vivado / Vitis
- 目标板卡：PYNQ-Z2

## PC 端运行方法

### 创建并激活虚拟环境

```powershell
python -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
.\.venv\Scripts\Activate.ps1
```

### 安装依赖

```powershell
python -m pip install -r requirements.txt
```

### 批量预处理静态数据

```powershell
python batch_preprocess_signs.py --input dataset\raw_static_v1 --output dataset\processed_static_v1
```

### 训练静态 NumPy 模型

```powershell
python train_static_numpy_model.py --input dataset\processed_static_v1 --model models\static_numpy_model.npz --summary report\static_numpy_model.json
```

### 板端实时识别

在 PYNQ-Z2 上运行：

```bash
cd /home/xilinx/sign-language-pynq
python3 board_static_live_json.py --model models/static_numpy_model.npz --interval 0.8
```

### 电脑端语音播报

在电脑 PowerShell 中运行：

```powershell
python .\pc_speak_static.py
```

### 动态产品演示（推荐）

板端在 Jupyter 中运行，摄像头、动态推理、JSON 和带结果画面由同一个进程完成：

```python
%cd /home/xilinx/sign-language-pynq
%run board_dynamic_live_json.py --product --model models/dynamic_model_numpy.npz --camera /dev/video0 --seq-len 16 --stride 4
```

电脑端另开 PowerShell 播报板端结果：

```powershell
cd D:\PYNQ\projects\sign-language-pynq
.\.venv\Scripts\Activate.ps1
python pc_speak_dynamic.py
```

动态语音默认置信度阈值为 `0.30`。板端 Linux 摄像头优先使用 V4L2；如 `/dev/video0` 不可用，可改用 `/dev/video1`。

## 当前验证边界

动态和静态 NumPy 模型可在板端运行，电脑端可读取 JSON 并播报。当前 Overlay 已完成加载、GPIO 和基础接口验证，但 DMA 全帧传输仍需分块传输设计和实测数据，暂不能将完整 FPGA 加速写成已完成。真实摄像头静态准确率需使用独立采集集重新确认。

项目审计记录见 `report/project_audit_20261017.md`。

## FPGA 工程

`fpga/` 目录包含 Vivado/HLS 相关工程文件。仓库会保留关键源文件、工程文件和必要 Overlay，忽略 `.cache`、`.gen`、`.runs`、HLS `solution*/syn`、`solution*/impl` 等自动生成目录。

## GitHub 协作建议

- `main` 分支只放稳定版本
- 每个任务建立一个 Issue
- 每个功能使用独立分支开发
- 合并前通过 Pull Request 检查
- 数据集、虚拟环境、运行缓存、SSH 密钥不要上传

## 后续计划

- 继续清洗静态手势数据集
- 完善动态手势识别流程
- 在板卡上验证实时识别稳定性
- 对比 CPU 与 FPGA 的延迟、帧率和资源占用
- 整理比赛报告、演示视频和答辩材料

## 数据与结果说明

- 不将训练集回测结果作为最终准确率
- 最终性能数据应来自实际板卡和独立测试集
- 使用网络图片时应确认授权，不提交无权再分发的数据
- 建议正式数据由参赛者自行采集，并记录采集条件

## AI 协作说明

本项目使用 AI 辅助项目规划、示例代码编写、错误分析和文档整理。所有 AI 输出均需经过参赛者运行或审核。

## 许可证

本项目源代码计划使用 MIT License，详情见 `LICENSE`。
