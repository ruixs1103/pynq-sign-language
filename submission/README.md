# Competition submission package

本目录汇总 2026 年竞赛提交材料。正文允许中文，目录名和文件名全部使用英文。

## Contents

- `report/design_report.md`：设计报告初稿，所有待实测字段均标记为 `TBD-TEST`。
- `report/implementation_report.md`：综合、实现、资源及时序报告。
- `report/verification_report.md`：仿真、软件验证和板级验证证据。
- `report/reproduction_guide.md`：从零复现步骤。
- `report/ai_collaboration_record.md`：大模型协作与自我纠错记录模板。
- `data/reference_results.json`：已确认指标与待测字段的机器可读版本。
- `data/test_record_template.csv`：板级重复测试记录表。
- `build/README.md`：构建入口和工具版本。
- `sim/README.md`：验证入口与通过标准。
- `scripts/validate_submission.py`：提交前静态检查。
- `scripts/collect_test_results.py`：汇总测试 CSV，生成 JSON 摘要。

## TBD convention

`TBD-TEST` 表示必须由真实板卡、正式数据集或最终 Vivado 实现报告确认，提交前不得保留。运行：

```powershell
python submission/scripts/validate_submission.py --root .
```

默认允许 `TBD-TEST` 并列出清单；最终提交检查使用：

```powershell
python submission/scripts/validate_submission.py --root . --final
```

## Source mapping

本项目未强制搬迁现有源码，避免破坏已跑通工程。目录映射如下：

| 推荐目录 | 当前来源 |
|---|---|
| `src/` | 根目录 Python 源码、`hls/skin_morph.cpp`、`vivado_proj/` |
| `board/` | `board/`、`skin_morph.bit/.hwh`、静态产品 Notebook |
| `sim/` | `hls/tb_skin_morph.cpp`、`test_pl_preprocess.py`、`tests/` |
| `data/` | `dataset/`、`sign_templates.json`、`report/metrics_*.json` |
| `skill/` | `skill/pynq-overlay-validation/` |
| `report/` | `report/` 与 `submission/report/` |

正式开源前应排除 `.venv/`、缓存、临时 Notebook、私密凭据和体积过大的可再生数据。
