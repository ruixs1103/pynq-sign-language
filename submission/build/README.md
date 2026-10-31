# Build entry points

## Toolchain

- Vivado 2026.1
- Vitis HLS 2026.1
- Target: `xc7z020clg400-1`
- HLS target clock: 10 ns

## Existing sources

- HLS top: `hls/skin_morph.cpp`
- HLS testbench: `hls/tb_skin_morph.cpp`
- Vivado project: `vivado_proj/sign_pl.xpr`
- Runtime driver: `pl_hand_seg.py`

## Final reproducible commands

```text
本次提交使用仓库中已验证的 HLS/Vivado 工程和 bit/hwh 配对；未在提交前重新执行批处理构建。
```

The final submission must run these commands in a clean output directory and archive logs plus resource/timing reports.
