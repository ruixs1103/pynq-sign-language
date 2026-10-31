# Verification entry points

## Software and logic

```powershell
python verify_templates.py
python -m pytest -q
```

## HLS

Use `hls/tb_skin_morph.cpp` for C simulation and co-simulation. 本次提交保留已有测试台和历史产物，不把未重跑的仿真写成新的定量结果。

## Board

```bash
python3 camera_board_test.py
python3 board_pl_smoke_test.py
```

For final evidence, run at least 1000 frames and record DMA failures, mean/P50/P95 latency, FPS and CPU/PL mask agreement.
