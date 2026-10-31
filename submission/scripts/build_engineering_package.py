#!/usr/bin/env python3
"""Build a reviewable engineering-package zip from an explicit allowlist."""
import argparse
import shutil
from pathlib import Path


FILES = [
    "README.md", "LICENSE", "requirements.txt", "pytest.ini",
    "pynq_sign_language.py", "pl_hand_seg.py", "board_static_demo.py",
    "product_display.py", "board_voice.py", "static_product.ipynb",
    "sign_templates.json", "skin_morph.bit", "skin_morph.hwh",
    "camera_board_test.py", "board_pl_smoke_test.py", "verify_templates.py",
    "test_pl_preprocess.py", "deploy_board.py",
]
DIRS = ["hls", "vivado_proj", "tests", "submission", "skill", "board/voice"]
IGNORE = shutil.ignore_patterns(
    "__pycache__", "*.pyc", ".ipynb_checkpoints", ".cache", ".gen",
    ".runs", "*.jou", "*.str", "*.wdb", "*.pb", "*.tmp",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="dist/sign-language-pynq-submission")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out = (root / args.out).resolve()
    if out.exists():
        raise SystemExit("output already exists; inspect/remove it first: %s" % out)
    out.mkdir(parents=True)
    missing = []
    for rel in FILES:
        src = root / rel
        if not src.is_file():
            missing.append(rel)
            continue
        dst = out / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    for rel in DIRS:
        src = root / rel
        if not src.is_dir():
            missing.append(rel + "/")
            continue
        shutil.copytree(src, out / rel, ignore=IGNORE)
    if missing:
        print("WARNING missing allowlist entries:")
        for rel in missing:
            print("  " + rel)
    archive = shutil.make_archive(str(out), "zip", root_dir=out.parent,
                                  base_dir=out.name)
    print("staging:", out)
    print("archive:", archive)
    print("Review both before publishing; no upload was performed.")


if __name__ == "__main__":
    main()
