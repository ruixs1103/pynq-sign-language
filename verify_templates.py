#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端验证：用板上完全相同的代码路径（load json -> HandSeg -> StaticRecognizer）
跑一遍测试集，确认 sign_templates.json 与 pynq_sign_language.py 兼容且效果一致。

用法: python verify_templates.py
"""
import glob
import json
import os
import re
from fnmatch import fnmatch

import cv2
import numpy as np

from pynq_sign_language import HandSeg, StaticRecognizer, UNKNOWN
from evaluate_features import split_keys          # 与训练端用同一套切分逻辑

def discover_classes(ds):
    """number_X -> 标签 X；unknown -> unknown。新增类别无需改代码。"""
    m = {}
    for d in sorted(os.listdir(ds)):
        if not os.path.isdir(os.path.join(ds, d)):
            continue
        mo = re.match(r"^number_(\d+)$", d)
        if mo:
            m[d] = mo.group(1)
        elif d.lower() in ("unknown", "other", "none"):
            m[d] = "unknown"
    return m


CLASS_MAP = {}
LABELS = []


def gkey(fp):
    return re.sub(r"_aug_\d+", "", os.path.basename(fp))


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset",
                    default=os.path.join("dataset", "raw_static_aug_v1"))
    ap.add_argument("--subset", default=None,
                    help="只测文件名匹配该 glob 的样本(如 'wechat_*')，用于分域评估")
    ap.add_argument("--all", action="store_true", help="测全量(含训练集样本，会高估)")
    args = ap.parse_args()

    global CLASS_MAP, LABELS
    CLASS_MAP = discover_classes(args.dataset)
    LABELS = sorted([v for v in CLASS_MAP.values() if v != "unknown"], key=lambda s: int(s))

    with open("sign_templates.json", "r", encoding="utf-8") as f:
        t = json.load(f)
    pred_labels = sorted(
        set(LABELS) | set(t.get("static", {}).keys()),
        key=lambda s: int(s),
    )
    meta = t.get("meta", {})
    print("[模板] mode=%s dim=%s 每类阈值=%s"
          % (meta.get("mode"), meta.get("dim"), meta.get("cls_thr")))
    print("[模板] 留出评估: 总%.1f%% 已知%.1f%% 未知召回%.1f%%"
          % (meta.get("acc_holdout", 0), meta.get("known_acc", 0), meta.get("unk_recall", 0)))

    rec = StaticRecognizer(t["static"], meta)
    seg = HandSeg()
    seg.max_ratio, seg.min_ratio = 0.97, 0.005

    conf = {k: {c: 0 for c in pred_labels + ["未知"]}
            for k in LABELS + ["unknown"]}
    total = correct = 0
    for d, lab in CLASS_MAP.items():
        folder = os.path.join(args.dataset, d)
        if not os.path.isdir(folder):
            continue
        files = sorted(glob.glob(os.path.join(folder, "*.jpg")))
        keys = split_keys(files, 0.7, 0)
        n_tr = max(1, int(len(keys) * 0.7))
        te_keys = set(keys[n_tr:])          # 只测留出组，与 evaluate 一致
        for fp in files:
            if not args.all and gkey(fp) not in te_keys:
                continue
            if args.subset and not fnmatch(os.path.basename(fp), args.subset):
                continue
            img = cv2.imread(fp)
            if img is None:
                continue
            cnt, _ = seg(img)
            if cnt is None:
                conf[lab]["未知"] += 1
                total += 1
                continue
            pred, dist, nf, _tips = rec.predict(cnt)
            conf[lab][pred] += 1
            total += 1
            gold = "未知" if lab == "unknown" else lab
            correct += (pred == gold)

    print("\n=== 板端代码路径复现（留出测试集）===")
    print("        " + "".join("%8s" % c for c in pred_labels + ["未知"]))
    for k in LABELS + ["unknown"]:
        print("%-8s%s" % (k, "".join("%8d" % conf[k][c]
                                      for c in pred_labels + ["未知"])))
    print("准确率: %.1f%% (%d/%d)" % (100.0 * correct / max(total, 1), correct, total))
    n_unk = sum(conf["unknown"].values())
    print("未知召回: %.1f%% (%d/%d)"
          % (100.0 * conf["unknown"]["未知"] / max(n_unk, 1), conf["unknown"]["未知"], n_unk))


if __name__ == "__main__":
    main()
