# PYNQ Overlay validation skill

## 适用范围

适用于带 AXI-Lite 控制与 AXI DMA/AXI4-Stream 数据通道的 PYNQ Overlay，包括图像预处理、滤波、变换和自定义流式计算。它不绑定手语识别、特定摄像头或特定板卡。

## 使用方法

1. 向支持 Skill 的大模型提供项目目录并要求使用 `$pynq-overlay-validation`。
2. 先运行 `scripts/verify_overlay_pair.py <bit> <hwh>`。
3. 按 `SKILL.md` 完成静态检查、单样本正确性、CPU/PL 对比、性能与稳定性测试。
4. 使用 `references/checklist.md` 判断证据是否足以支持结论。

## 失效条件

- 设计不使用 PYNQ 或不存在 Overlay/DMA 数据路径。
- 缺少同构建的 bit/hwh，或无法获得寄存器/流接口契约。
- 只有仿真环境却要求声称真实板级性能。
- 被测算法改变后仍沿用旧黄金参考或旧阈值。

## 已验证效果

在 PYNQ-Z2 图像预处理项目中，该流程定位过 bit/hwh/IP 名称、DMA 顺序、mask 极性、白平衡导致的输入漂移，以及“显示编码而非 PL”造成的性能瓶颈。具体数值属于项目证据，不写入通用规则。
