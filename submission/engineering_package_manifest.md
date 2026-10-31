# Engineering package manifest

## Required source

- `hls/skin_morph.cpp` and HLS testbench/Tcl files
- `vivado_proj/` project sources, constraints, block design and IP metadata
- `pl_hand_seg.py`, `pynq_sign_language.py`, `board_static_demo.py`
- `product_display.py`, `board_voice.py`, `static_product.ipynb`
- `sign_templates.json`
- `skin_morph.bit` and `skin_morph.hwh`
- board voice WAV files

## Verification and reports

- `tests/`, `test_pl_preprocess.py`, `verify_templates.py`
- `camera_board_test.py`, `board_pl_smoke_test.py`
- `submission/` and `skill/`
- final raw Vivado/HLS reports and board logs

## Excluded by design

- `.git/`, `.venv/`, `__pycache__/`, `.ipynb_checkpoints/`
- local IDE settings and credentials
- raw caches and reproducible generated intermediates
- large dataset archives unless redistribution is authorized
- historical/legacy routes not referenced by the final report

The packaging script uses an allowlist. Review its output before publishing.
