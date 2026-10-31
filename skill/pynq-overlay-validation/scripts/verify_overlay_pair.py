#!/usr/bin/env python3
"""Verify basic integrity of a PYNQ bit/hwh pair without loading hardware."""
import argparse
import hashlib
from pathlib import Path
import xml.etree.ElementTree as ET


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bit", type=Path)
    parser.add_argument("hwh", type=Path)
    args = parser.parse_args()
    errors = []
    for path in (args.bit, args.hwh):
        if not path.is_file() or path.stat().st_size == 0:
            errors.append("missing or empty: %s" % path)
    if args.bit.stem != args.hwh.stem:
        errors.append("stem mismatch: %s != %s" % (args.bit.stem, args.hwh.stem))
    if not errors:
        try:
            root = ET.parse(args.hwh).getroot()
            tag_count = sum(1 for _ in root.iter())
            if tag_count < 2:
                errors.append("HWH contains too few XML elements")
        except Exception as exc:
            errors.append("invalid HWH XML: %s" % exc)
    if errors:
        for error in errors:
            print("ERROR:", error)
        raise SystemExit(1)
    print("bit_sha256=", sha256(args.bit))
    print("hwh_sha256=", sha256(args.hwh))
    print("hwh_xml_elements=", tag_count)
    print("PASS")


if __name__ == "__main__":
    main()
