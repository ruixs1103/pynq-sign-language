# 综合与实现报告

## 1. 工具与器件

| 项目 | 已确认值 |
|---|---|
| Board | PYNQ-Z2 |
| Device | xc7z020-clg400-1 |
| Vivado | 2026.1 |
| Vitis HLS | 2026.1 build 6493734 |
| PYNQ runtime | 3.1.1 |
| OpenCV on board | 4.5.4 |

证据来源：HLS csynth 报告、Vivado 日志和板端环境检查输出。

## 2. HLS 结构

`skin_morph` 使用 DATAFLOW 连接颜色转换、四级形态学和 AXI 输出。各像素循环目标 II=1。顶层 csynth 因流式运行时尺寸参数显示总延迟为 `?`，因此不得把理论帧延迟伪写为确定结果。

## 3. HLS 估算

来源：`hls/skin_morph/solution1/syn/report/skin_morph_csynth.rpt`。

| 指标 | 结果 |
|---|---:|
| Target clock | 10.000 ns / 100 MHz |
| Estimated clock | 7.396 ns |
| BRAM_18K | 26 / 280 (9%) |
| DSP | 25 / 220 (11%) |
| FF | 10656 / 106400 (10%) |
| LUT | 10805 / 53200 (20%) |

注意：以上为 HLS 估算，不等同于完整 Vivado 设计的 post-route 资源。

## 4. 工程结果

工程已生成可配套使用的 `skin_morph.bit` 与 `skin_morph.hwh`，并在 PYNQ-Z2 上完成 Overlay 加载、DMA 传输、PL 分割、PS 分类、界面显示和语音播报验证。本报告采用 HLS 综合阶段的估算资源说明硬件结构，不把估算值表述为板级资源占用。
