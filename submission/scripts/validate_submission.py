#!/usr/bin/env python3
"""Static preflight checks for the competition repository."""
import argparse
import json
from pathlib import Path


REQUIRED = [
    "README.md", "LICENSE", "hls/skin_morph.cpp", "pl_hand_seg.py",
    "board_static_demo.py", "product_display.py", "skin_morph.bit",
    "skin_morph.hwh", "submission/report/design_report.md",
    "submission/report/implementation_report.md",
    "submission/report/verification_report.md",
    "submission/report/reproduction_guide.md",
    "submission/report/ai_collaboration_record.md",
    "skill/pynq-overlay-validation/SKILL.md",
    "skill/pynq-overlay-validation/README.md",
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--final", action="store_true",
                        help="fail if TBD-TEST remains")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    errors = []
    for rel in REQUIRED:
        if not (root / rel).is_file():
            errors.append("missing: " + rel)

    pair = [root / "skin_morph.bit", root / "skin_morph.hwh"]
    if pair[0].exists() != pair[1].exists():
        errors.append("skin_morph bit/hwh pair is incomplete")

    result_file = root / "submission/data/reference_results.json"
    try:
        json.loads(result_file.read_text(encoding="utf-8"))
    except Exception as exc:
        errors.append("invalid reference_results.json: %s" % exc)

    tbd = []
    for base in (root / "submission", root / "skill"):
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".md", ".json", ".csv"}:
                try:
                    count = path.read_text(encoding="utf-8").count("TBD-TEST")
                except UnicodeDecodeError:
                    continue
                if count:
                    tbd.append((path.relative_to(root).as_posix(), count))

    print("TBD-TEST locations:")
    for path, count in tbd:
        print("  %-65s %d" % (path, count))
    if args.final and tbd:
        errors.append("final mode: TBD-TEST remains")
    if errors:
        print("FAILED")
        for item in errors:
            print("  " + item)
        raise SystemExit(1)
    print("PASS%s" % (" (draft with placeholders)" if tbd else ""))


if __name__ == "__main__":
    main()
