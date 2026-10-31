# 工程包提交清单

本清单按评审要求组织，所有路径均相对于仓库根目录。工程包以“源码可查、证据可核、步骤可复现”为原则。

## 1. 完整工程文件与源码（工程包）

- `hls/skin_morph.cpp`、`hls/tb_skin_morph.cpp`、`hls/run_hls.tcl`、`hls/run_cosim.tcl`
- `vivado_proj/sign_pl.xpr`、Block Design/IP 配置和约束文件
- `board/pl_hand_seg.py`、`pynq_sign_language.py`、`board/board_static_demo.py`
- `board/product_display.py`、`board/board_voice.py`、产品 Notebook 与配置
- `board/sign_templates.json`、`board/skin_morph.bit`、`board/skin_morph.hwh`
- `board/voice/` 中的离线 WAV 语音资源

## 2. 仿真、验证与对比证据

- `hls/tb_skin_morph.cpp`、`hls/pl_sim_check.py`、`hls/pl_logic_sim.py`
- `camera_board_test.py`、`board_pl_smoke_test.py`、`submission/report/verification_report.md`
- `report/board_last_test/` 中的板端输入图、Mask、JSON 和运行记录
- `hls/skin_morph/solution1/syn/report/skin_morph_csynth.rpt` 中的 HLS 综合结果
- `submission/report/implementation_report.md` 中的结构、资源估算和性能说明

## 3. 上板工程、运行脚本与可复现构建

- 上板入口：`board/pynq_sign_language.py`、`board/board_static_demo.py`
- Overlay 加载与验证：`board/load_overlay.py`、`board/verify_role_c.py`、`skill/pynq-overlay-validation/scripts/verify_overlay_pair.py`
- HLS 构建：`hls/run_hls.tcl`
- Vivado 工程：`vivado_proj/sign_pl.xpr`
- 复现步骤：`submission/report/reproduction_guide.md`

## 4. Skill 包

- `skill/pynq-overlay-validation/README.md`
- `skill/pynq-overlay-validation/SKILL.md`
- `skill/pynq-overlay-validation/references/checklist.md`
- `skill/pynq-overlay-validation/scripts/verify_overlay_pair.py`

## 5. 设计报告

- `submission/report/design_report.md`
- `submission/report/自主选题初级赛道设计报告_手势识别与语音播报.docx`

## 6. 不纳入工程包的内容

- `.git/`, `.venv/`, `__pycache__/`, `.ipynb_checkpoints/`
- local IDE settings and credentials
- raw caches and reproducible generated intermediates
- large dataset archives unless redistribution is authorized
- historical/legacy routes not referenced by the final report

历史动态手势实验、旧分类路线、临时缓存、IDE 配置、凭据和不可再生的大型原始数据不作为本次正式工程包内容。打包脚本使用 allowlist，发布前应检查输出目录。
