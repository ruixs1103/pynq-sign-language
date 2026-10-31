# PYNQ-Z2 上板验收清单

当前主路线为 `pynq_sign_language.py + skin_morph/design_2 Overlay + board_voice.py`。以下项目必须在真实 PYNQ-Z2 上完成；未验证前不能在报告中写成已完成。

## 文件与环境

- [ ] 记录 PYNQ 镜像、Python、OpenCV、PYNQ 包和 Linux 内核版本。
- [ ] 确认 `skin_morph.bit/.hwh` 与 `design_2.bit/.hwh` 各自成对且能加载。
- [ ] 将 `board/` 同步到板端，确认 `sign_templates.json` 和 `voice/*.wav` 完整。
- [ ] 运行 `python3 demo_transition.py --selftest`。

## 摄像头与 PL

- [ ] USB 摄像头路线能稳定打开并达到目标分辨率/FPS。
- [ ] OV5640、AXI IIC、动态时钟、VTC、VDMA 均能初始化并连续取帧。
- [ ] 对同一批固定图片比较 CPU 分割和 `skin_morph` PL 分割，记录像素差异。
- [ ] 检查 BGR/RGB 顺序、YCbCr 阈值、形态学核和不同光照下的肤色范围。
- [ ] 连续运行 1000 帧无 VDMA/DMA 超时、TLAST、缓存一致性或内存泄漏错误。

## 识别与状态机

- [ ] 数字 1~5 每类至少独立测试 20 次，记录混淆矩阵和 unknown 拒识率。
- [ ] 优先修复当前离线 unknown 召回仅 25.0%（3/12）的问题，再冻结模板。
- [ ] 点赞只负责唤醒，停止手势只负责结束，不会误计入数字序列。
- [ ] `stable` 连续确认有效，手保持不动不会重复录入。
- [ ] 手离开达到 `release` 后，同一个数字可以再次录入。
- [ ] 调整后的阈值写回 `sign_templates.json`，并重新运行 `verify_templates.py`。

## 语音与产品演示

- [ ] `board_voice.check_voice()` 返回空列表。
- [ ] 浏览器允许隐藏 audio 自动播放，`wake/result/empty/stop/d1~d5` 均可听清。
- [ ] 完整演示“点赞唤醒 -> 多位数字 -> 停止 -> 播报结果”。
- [ ] 断开/恢复摄像头或重启 Notebook 后可以重新启动，不残留后台线程。

## 最终量化

- [ ] 记录 CPU 与 PL 两条路线的采集、分割、特征、识别和端到端延迟。
- [ ] 记录 FPS、准确率、macro-F1、误触发率和 30 分钟稳定性。
- [ ] 导出 HLS/Vivado 的 LUT、FF、BRAM、DSP、时钟和时序裕量。
- [ ] 将命令、参数、日志和最终 bit/hwh 哈希保存到 `report/board_final/`。

旧版 HOG/RandomForest/JSON 管线只用于回退与对照，不与当前模板、标签或 Overlay 混用。
