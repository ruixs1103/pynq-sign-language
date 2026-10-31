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
TBD-TEST: vitis-run/vitis_hls batch command
TBD-TEST: vivado -mode batch command
```

The final submission must run these commands in a clean output directory and archive logs plus resource/timing reports.
