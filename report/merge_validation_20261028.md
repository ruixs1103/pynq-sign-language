# 基准路线合并验证（2026-10-28）

基准来源：`D:\PYNQ\sign`

目标项目：`D:\PYNQ\projects\sign-language-pynq`

## 已验证

- 新主路线 14 个 Python 文件通过语法编译。
- `sign_templates.json` 可解析。
- `board_deploy.zip` 结构完整，共 23 个条目。
- `board/voice/` 的 9 个 WAV 均可由标准 WAV 解析器读取。
- `skin_morph.bit/.hwh`、`design_2.bit/.hwh` 及板端副本均存在。
- 关键 Python、模板、bit/hwh、HLS 源码与基准目录 SHA-256 一致。
- `vivado_proj/sign_pl.xpr` 与基准目录 SHA-256 一致。
- `demo_transition.py --selftest`：14/14 通过。
- `verify_templates.py`：总准确率 85.6%（184/215）。

## 主要风险

- unknown 召回率只有 25.0%（3/12），当前拒识能力不足。
- 独立测试中 31 个错误里，有一部分是目标类别被拒为 unknown，也有 unknown 被误识别为数字。
- 当前电脑原 `.venv` 指向已删除的 Python 3.11，必须按 README 重建环境。
- OV5640、VDMA、PL 分割与浏览器语音仍需真实 PYNQ-Z2 验证。

## 下一步

1. 增加不同人、背景、距离和光照下的 unknown 样本。
2. 用独立采集批次重新运行 `evaluate_features.py`，重点优化 `meta.cls_thr` 和每类 `cls_thr`。
3. 重新运行 `verify_templates.py`；unknown 召回达到可接受水平后再替换板端模板。
4. 按根目录 `BOARD_TODO.md` 逐项完成上板验收。
