# Final test checklist

提交前逐项替换所有 `TBD-TEST`，并保留原始日志或报告。

- [ ] 最终公开仓库 URL、release URL、commit SHA。
- [ ] 最终 HLS batch 命令和干净目录重建日志。
- [ ] 最终 Vivado batch 命令和 bit/hwh 哈希。
- [ ] Vivado post-route LUT、LUTRAM、FF、BRAM、DSP。
- [ ] WNS、TNS、总片上功耗。
- [ ] CPU 与 PL 同输入预处理：均值、P50、P95、标准差、失败数。
- [ ] CPU/PL mask：IoU、像素一致率、差异像素数。
- [ ] 端到端 FPS 和延迟，分别注明是否包含浏览器显示。
- [ ] 数字 1–5、点赞、停止逐类准确率和混淆矩阵。
- [ ] 未知动作召回率，测试集来源与数量。
- [ ] 1000 帧 DMA/Overlay 稳定性测试。
- [x] 7 类静态手势逐一功能验收：文字和语音正确（2026-10-31）。
- [x] 正式产品页连续运行 5 分钟，无明显卡顿、崩溃或功能异常（2026-10-31）。
- [x] 正式入口确认显示 `PL SEGMENTATION / ARM PS`（2026-10-31）。
- [ ] 从新目录或新 SD 卡完整复现一次。
- [ ] 导出完整大模型协作记录，补模型版本、时间戳和关联 commit。
- [ ] 运行 `validate_submission.py --final`，结果必须 PASS。
