# 手势识别项目执行计划（合并版）

> 合并来源：《PYNQ-Z2 手势识别 FPGA 作品参赛推进计划》（AMD 参赛文档）
> 与《手势识别项目任务分工与执行计划》（2026-10-01 更新版）。
> 本文档为当前唯一有效计划；如有冲突，以更新版为准并记录到 decision_log。

## 1. 项目概览

| 项 | 内容 |
|---|---|
| 开发板 | PYNQ-Z2（Xilinx Zynq-7020） |
| 输入设备 | USB 摄像头（320x240 起） |
| 工具链 | Vivado/Vitis 2025.2（或验证过的 2026.1） |
| 提交截止 | 2026-11-04 |
| 团队 | 3 人（A：采集+硬件，B：算法+接口，C：音频+板端） |

**静态类别**：`number_1` ~ `number_5` + `unknown`
**动态类别**：`hello`、`thanks`、`goodbye`、`help` + `unknown`
类别定义唯一来源：`labels.py`（B 维护，A/C 不得重新定义）。

## 2. 系统架构

```
USB 摄像头
   |
   v
PS: Python 采集与控制
   |  DMA / AXI-Stream
   v
PL: ROI -> YCrCb 分割 -> 二值化 -> 形态学          (A: HLS/Overlay)
   |
   v
PS: HOG / 序列特征 -> SVM / 随机森林 -> 投票/冷却   (B: 模型)
   |
   v
输出: 手势 + 中文文本 + 置信度 + WAV 语音播报        (C: 音频/板端)
```

- 静态流程：摄像头图片 → YCrCb 分割 → 最大连通区域 → 128x128 二值图 → HOG → SVM/原型分类器
- 动态流程：视频 → 均匀抽取 16/24 帧 → 每帧分割 → 形状+运动特征 → 线性 SVM/随机森林（不用 LSTM）
- FPGA 只处理静态和动态共用的预处理部分，分类始终在 PS

## 3. 关键指标（验收线）

| 指标 | 目标 | 主责 | 证据位置 |
|---|---|---|---|
| 静态类别数 | 5 类 + unknown | C(数据)/B(模型) | data/, report/ |
| Python 基线速度 | >= 15 FPS | C | report/ |
| FPGA 预处理速度 | >= 15 FPS | A+B | report/ |
| 端到端延迟 | < 300 ms | B | report/ |
| 静态/动态测试准确率 | >= 85% | B | report/ |
| 连续运行 30 分钟 | 无严重错误 | B | board/, report/ |
| DMA 连续测试 | >= 1000 帧 | A | board/ |
| 仿真输出误差 | < 1% 像素，可解释 | A | sim/, report/ |

## 4. 角色边界

### A：采集 + 硬件
- `capture_dataset.py`（静态采集）、`capture_sequences.py`（动态采集）、
  `dataset_manifest.py`（清单）、`dataset_audit.py`（审计）
- `board/camera_board_test.py`、`board/run_sign_inference.py`、
  `board/board_environment_check.py`、`board/benchmark_cpu_fpga.py`
- `fpga/hls/`：HLS 顶层、AXI-Stream/AXI-Lite、YCrCb 阈值、二值化、形态学、
  流水线、C 仿真、Python 对比、综合脚本
- Overlay 构建配置，产物输出到 `board/overlays/sign_preprocess_2026_1/`
- A 不负责模型判断逻辑（由 B 的 predictor 提供）

### B：算法 + 接口（本轮已交付初版代码）
- `labels.py`：类别、中文映射、统一结果结构
- 静态链路：`preprocess.py`、`batch_preprocess_signs.py`、`batch_hog_features.py`、
  `train_static_model.py`、`evaluate_static_model.py`
- 动态链路：`sequence_features.py`、`train_dynamic_model.py`、`evaluate_dynamic_model.py`
- 统一接口：`predictor.py`（静态/动态/实时状态机）
- PC 实时程序：`realtime_sign_pc.py`（图片/视频/帧目录回放）
- 测试：`tests/test_preprocess.py`、`tests/test_predictor.py`

### C：音频 + 板端
- `audio/prepare_audio.py`、`audio/speech_map.py`、`audio/play_audio.py`、`audio/test_audio.py`
- `board/load_overlay.py`、`board/overlay_register_test.py`、`board/audio_board_test.py`
- Overlay 加载、寄存器、DMA、Cache 一致性、超时复位、板端联调日志

### 三人共同
动作规范确认、必要时的补采、板卡集中测试、最终演示、版本冻结和提交。

## 5. 数据集要求

| 项 | 静态 | 动态 |
|---|---|---|
| 最小样本 | 每类 10 张测试图 | 每类 3 段测试视频 |
| 正式训练 | 每类 100~150 张 | 每类 40~60 段视频 |
| 独立测试 | 每类 >= 20 张 | 每类 >= 10 段视频 |
| 单位 | 图片 | 完整视频（约 2~4 秒） |

红线：
- 训练集和测试集不得来自同一段视频/同一批次
- 覆盖不同距离、角度、位置、背景、光照
- unknown 必须确实包含非目标动作
- 数据清单与审计报告必须生成（A 的 manifest/audit 脚本）

## 6. 六阶段执行顺序

1. **接口和最小样本**（当前阶段）
   - A：采集脚本 + 最小样本 + HLS 接口草案和 C 仿真最小版
   - B：labels.py、预处理接口、序列特征接口、统一结果结构测试（已交付）
   - C：PC 端音频播放、音频映射测试、Overlay 加载假实现、PS/DMA 草案
   - 通过条件：样本可读取、目录正确、标签一致、结果结构测试通过、HLS 测试可运行
2. **PC 静态模型和 HLS 设计**
   - A：正式采集、HLS 核心、C 仿真、Python/HLS 对比、IP 初版
   - B：静态预处理/HOG/训练/评估
   - C：检查 IP 接口、准备 Overlay 加载、寄存器和 DMA 测试、音频 PC 测试
3. **动态模型和 Overlay 初版**
   - A：补采动态样本、Overlay 构建、帧缓存和板端摄像头测试
   - B：动态序列特征、分类器、起止检测、冷却和防重复
   - C：加载 Overlay、寄存器/DMA/复位/超时/音频触发测试
4. **第一次板卡集中测试**
   - A：连续取帧、静态输入、动态帧缓存、run_sign_inference.py
   - B：固定图片/视频、假预测器、板端与 PC 结果对比
   - C：Overlay/寄存器/DMA/LED/音频、连续 >= 100 帧
5. **真实模型联调**
   - A：最终测试数据、板端适配、硬件日志、HLS 延迟
   - B：固化模型、调阈值/投票/unknown、错误样本分析
   - C：真实 Overlay、DMA+音频联调、端到端延迟、FPGA FPS、长时间稳定性
6. **最终提交**
   - A：原始数据、manifest、采集规范、HLS/Overlay 构建文件、演示视频
   - B：模型、准确率、混淆矩阵、测试脚本、接口说明
   - C：板卡日志、音频测试、DMA/Overlay 测试、延迟/FPS/资源报告

## 7. 性能与验收测量清单

必须记录：Python FPS、FPGA 预处理 FPS、单帧延迟、端到端延迟、
HLS 资源（LUT/FF/BRAM/DSP）、连续 100 帧、连续 1000 帧、
连续 30 分钟错误数、静态/动态准确率。
必须生成优化前后对比表，不能只展示优化后数据。

## 8. 降级策略

- 10 类/动态不稳定 → 退回稳定的 5 类静态版本（C 决策，A+B 配合）
- 复杂形态学无法上 PL → PL 只做 YCrCb 分割和二值化，特征和分类留 PS
- 摄像头驱动异常 → 先用固定图片验证 DMA/Overlay，最终报告仍需真实板卡输出
- Vivado 版本不兼容 → 锁定已验证组合
- 任何降级决策须三人确认并记入 report/decision_log.md

## 9. 协作机制

- 每周日 30 分钟站会：各自汇报完成/计划/阻塞
- 每周日 B 汇总更新 report/weekly_log.md
- 所有提交写明模块归属（A/B/C）
- 交叉支援：A 高峰期 B 协助仿真脚本；C 高峰期 B 协助数据整理；B 高峰期 A/C 提供图表数据
- AI 协作记录从第一次使用模型开始，持续记入 report/ai_collaboration.md

## 10. 时间表（对齐原始截止日）

| 周期 | 内容 |
|---|---|
| 09-15 ~ 09-20 | 需求、仓库、版本冻结 |
| 09-21 ~ 09-27 | 上板和摄像头测试 |
| 09-28 ~ 10-04 | 电脑端算法基线（当前：10-01） |
| 10-05 ~ 10-11 | HLS/RTL 和仿真 |
| 10-12 ~ 10-18 | Overlay 和端到端集成 |
| 10-19 ~ 10-25 | 性能、资源和稳定性测试 |
| 10-26 ~ 10-29 | 通用 PYNQ Skill |
| 10-30 ~ 11-02 | 工程包、报告和复现 |
| 11-03 | 冻结版本（干净环境重建、复现、打标签） |
| 11-04 | 提交 |
