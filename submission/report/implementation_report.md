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

## 4. Vivado 最终实现指标

| 指标 | 结果 |
|---|---|
| LUT | TBD-TEST |
| LUTRAM | TBD-TEST |
| FF | TBD-TEST |
| BRAM | TBD-TEST |
| DSP | TBD-TEST |
| WNS | TBD-TEST |
| TNS | TBD-TEST |
| Total on-chip power | TBD-TEST |
| Bitstream generation status | 已存在可上板 bit/hwh；最终提交构建需重新留档 |

补测方法：在最终 Vivado 工程中执行 implementation，导出 `report_utilization`、`report_timing_summary` 和 `report_power`，将原始 `.rpt` 放入 `submission/data/vivado_final/`。

## 5. 性能对比

现有探索性测量：摄像头约 28.40 ms、PL 分割及 DMA 约 47.87 ms、静态分类约 0.02 ms、原始大画面合成/JPEG 约 462.78 ms。该结果用于定位显示瓶颈，不作为最终加速比。

| 场景 | CPU | PL | 加速比 |
|---|---:|---:|---:|
| 仅预处理，640×480，平均延迟 | TBD-TEST | TBD-TEST | TBD-TEST |
| 仅预处理，P95 延迟 | TBD-TEST | TBD-TEST | TBD-TEST |
| 端到端，不含浏览器显示 | TBD-TEST | TBD-TEST | TBD-TEST |
| 端到端，含产品页面 | TBD-TEST | TBD-TEST | TBD-TEST |

最终对比必须使用相同图像、相同阈值、相同分辨率、预热后至少 1000 帧，并同时报告均值、P50、P95、标准差和失败帧数。

## 6. 资源收益判断

HLS 核心使用约 20% LUT、11% DSP 和 9% BRAM 的估算资源。是否“资源合理”需结合最终 post-route 数据和 CPU/PL 加速比判断；在 `TBD-TEST` 完成前不作定量结论。
