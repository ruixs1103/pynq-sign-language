#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
特征对比实验：找出在这套数据上真正可分的特征表示

对比 4 种特征集（都沿用"特征向量 + 最小二范数最近邻"的框架）：
  hu     : Hu 不变矩 log 化（原视频逻辑）
  geo    : 指尖数 + solidity + 紧凑度 + 宽高比 + extent + 凸包缺陷数
  fd     : 傅立叶描述子 8 维（平移/尺度/旋转/起点不变）
  combo  : geo + fd

切分按"原图组"划分（同一张原图的所有增广图不跨训练/测试），避免数据泄漏。
输出：各特征集准确率对比 + 最佳特征集混淆矩阵 + 自动整定的未知阈值
     并把最佳方案写入 sign_templates.json 供板上直接使用。
"""
import argparse
import glob
import json
import os
import re

import numpy as np

from pynq_sign_language import HandSeg, feature_vec, count_fingertips

def split_keys(files, ratio, seed=0):
    """按原图组随机切分（固定种子，可复现）。

    不能按文件名排序取后段：本数据集的命名 number_* / wechat_* 恰好对应两种采集域，
    字母序切分会让测试集只剩单一域，评估结果虚高（实测 99% 是假象）。
    """
    keys = np.array(sorted(set(group_key(f) for f in files)))
    idx = np.arange(len(keys))
    np.random.RandomState(seed).shuffle(idx)
    return list(keys[idx])


def discover_classes(dataset_dir):
    """自动发现类别目录：number_X -> 标签 X；unknown -> 仅用于整定未知阈值。
    数据补齐后新增类别无需改代码。"""
    m = {}
    for d in sorted(os.listdir(dataset_dir)):
        if not os.path.isdir(os.path.join(dataset_dir, d)):
            continue
        mo = re.match(r"^number_(\d+)$", d)
        if mo:
            m[d] = mo.group(1)
        elif d.lower() in ("unknown", "other", "none"):
            m[d] = None
    return m


CLASS_MAP = {}
LABELS = []
MODES = ["cdf24", "cdf24f", "fdcdf", "combo2"]


def group_key(fp):
    """去掉 _aug_XXX 后缀，保证同一原图的增广样本不被拆到训练/测试两侧。"""
    return re.sub(r"_aug_\d+", "", os.path.basename(fp))


def load(args):
    seg = HandSeg()
    seg.max_ratio, seg.min_ratio = 0.97, 0.005
    data = {}
    for d in sorted(os.listdir(args.dataset)):
        folder = os.path.join(args.dataset, d)
        if not os.path.isdir(folder) or d not in CLASS_MAP:
            continue
        files = sorted(glob.glob(os.path.join(folder, "*.jpg")) +
                       glob.glob(os.path.join(folder, "*.png")))
        keys = split_keys(files, args.train_ratio, args.seed)
        n_tr = int(len(keys) * args.train_ratio)
        tr_keys = set(keys[:n_tr])
        for fp in files:
            import cv2
            img = cv2.imread(fp)
            if img is None:
                continue
            cnt, _ = seg(img)
            if cnt is None:
                continue
            key = CLASS_MAP[d] or "unknown"
            split = "train" if group_key(fp) in tr_keys else "test"
            data.setdefault((mode_key(), split), {})
            rec = data.setdefault((key, split), {"files": [], "cnts": []})
            rec["files"].append(fp)
            rec["cnts"].append(cnt)
    return data


_mode_store = {"m": "combo"}


def mode_key():
    return _mode_store["m"]


def kmeans(X, k=3, iters=40, seed=0):
    """极简 K-means：为每类取 k 个原型，处理类内多模态（同一手势的多种摆法）。"""
    rs = np.random.RandomState(seed)
    k = min(k, len(X))
    C = X[rs.choice(len(X), k, replace=False)].copy()
    for _ in range(iters):
        d = np.linalg.norm(X[:, None, :] - C[None, :, :], axis=2)
        lab = d.argmin(axis=1)
        for j in range(k):
            if np.any(lab == j):
                C[j] = X[lab == j].mean(axis=0)
    return C


def build_and_eval(data, mode, n_proto=1):
    """返回 (acc, thresh, conf, meta)"""
    feats = {}
    nfs = {}
    for k in list(CLASS_MAP.values()):
        key = k or "unknown"
        for split in ("train", "test"):
            rec = data.get((key, split))
            if not rec:
                continue
            vecs, cnt_nfs = [], []
            for c in rec["cnts"]:
                v = feature_vec(c, mode)
                vecs.append(v if v is not None else None)
                cnt_nfs.append(count_fingertips(c)[0])
            feats[(key, split)] = vecs
            nfs[(key, split)] = cnt_nfs

    # 统一维度（丢弃 None）
    def clean(key, split):
        return [v for v in feats.get((key, split), []) if v is not None]

    def clean_nf(key, split):
        # 与 clean() 逐样本对齐：只保留 feature 非 None 样本的指尖数
        return [n for v, n in zip(feats.get((key, split), []),
                                  nfs.get((key, split), [])) if v is not None]

    dim = len(clean("1", "train")[0]) if clean("1", "train") else 0
    if dim == 0:
        return None

    # 标准化参数（仅用训练集）
    alltr = np.asarray([v for lab in LABELS + ["unknown"] for v in clean(lab, "train")],
                       np.float32)
    mu, sd = alltr.mean(axis=0), alltr.std(axis=0) + 1e-6

    def zs(v):
        return (v - mu) / sd

    tpl = {}
    for lab in LABELS:
        arr = np.asarray(clean(lab, "train"), np.float32)
        if len(arr) == 0:
            return None
        if n_proto <= 1:
            tpl[lab] = np.median(zs(arr), axis=0)[None, :]
        else:
            tpl[lab] = kmeans(zs(arr), n_proto)

    # 每类自适应阈值：类内距离的中位 + 3*MAD（各类方差差异大，全局阈值不可用）
    unk_arr = np.asarray(clean("unknown", "train"), np.float32)
    cls_thr, intra_all = {}, []
    for lab in LABELS:
        arr = np.asarray(clean(lab, "train"), np.float32)
        d = np.linalg.norm(zs(arr)[:, None, :] - tpl[lab][None, :, :], axis=2).min(axis=1)
        intra_all += list(d)
        lo = float(np.percentile(d, 95))          # 已知类：95% 应通过
        if len(unk_arr):                          # unknown：四分之三应被拒
            du = np.linalg.norm(zs(unk_arr)[:, None, :] - tpl[lab][None, :, :],
                                axis=2).min(axis=1)
            hi = float(np.percentile(du, 25))
        else:
            hi = float("inf")
        # 两类分布可分 -> 取中间；不可分(重叠) -> 只能保已知类，unknown 召回会低
        cls_thr[lab] = 0.5 * (lo + hi) if hi > lo * 1.15 else lo * 1.25
    intra = np.asarray(intra_all)
    p_in = float(np.percentile(intra, 95))

    unk = np.asarray(clean("unknown", "train"), np.float32)
    unk_d = np.min(np.stack(
        [np.linalg.norm(zs(unk)[:, None, :] - tpl[l][None, :, :], axis=2).min(axis=1)
         for l in LABELS], 1), 1) if len(unk) else np.array([np.inf])
    p_unk = float(np.percentile(unk_d, 5))

    has7 = "7" in LABELS
    conf = {k: {c: 0 for c in LABELS + ["未知"]} for k in LABELS + ["unknown"]}
    for key in LABELS + ["unknown"]:
        for v, nf in zip(clean(key, "test"), clean_nf(key, "test")):
            zv = zs(v)
            if has7 and nf == 0:            # 握拳(7)由"0 指尖"判定，与板端 predict() 一致
                pred = "7"
            else:
                best, bd = None, 1e9
                for lab in LABELS:
                    if lab == "7":
                        continue            # 7 不参与形状最近邻
                    d = float(np.linalg.norm(tpl[lab] - zv[None, :], axis=1).min())
                    if d < bd:
                        bd, best = d, lab
                pred = best if bd <= cls_thr[best] else "未知"
            conf[key][pred] += 1

    total = correct = 0
    for key in LABELS + ["unknown"]:
        total += sum(conf[key].values())
        gold = "未知" if key == "unknown" else key
        correct += conf[key].get(gold, 0)
    acc = 100.0 * correct / max(total, 1)

    n_unk = sum(conf["unknown"].values())
    unk_recall = 100.0 * conf["unknown"].get("未知", 0) / max(n_unk, 1)
    n_known = sum(sum(conf[l].values()) for l in LABELS)
    known_acc = 100.0 * sum(conf[l].get(l, 0) for l in LABELS) / max(n_known, 1)

    return {"mode": mode, "acc": acc, "thresh": float(np.mean(list(cls_thr.values()))),
            "cls_thr": cls_thr, "conf": conf, "p_in": p_in, "p_unk": p_unk, "dim": dim,
            "unk_recall": unk_recall, "known_acc": known_acc,
            "mu": mu.tolist(), "sd": sd.tolist(),
            "tpl": {k: v.tolist() for k, v in tpl.items()},
            "n_train": int(len(alltr)), "total": total}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=os.path.join("dataset", "raw_static_aug_v1"))
    ap.add_argument("--out", default="sign_templates.json")
    ap.add_argument("--train-ratio", type=float, default=0.7)
    ap.add_argument("--proto", type=int, default=1,
                    help="每类原型个数(>1 时按 K-means 聚类，处理类内多模态)")
    ap.add_argument("--mode-override", default=None,
                    help="强制使用指定特征模式(如 fdcdf)，跳过自动选择")
    ap.add_argument("--seed", type=int, default=0, help="留出切分随机种子")
    args = ap.parse_args()

    import cv2  # noqa: F401  供主流程使用

    global CLASS_MAP, LABELS
    CLASS_MAP = discover_classes(args.dataset)
    LABELS = sorted([v for v in CLASS_MAP.values() if v], key=lambda s: int(s))
    if not LABELS:
        print("[ERR] 在 %s 下没有找到 number_X 目录" % args.dataset)
        return
    print("[类别] 自动发现: %s + unknown" % LABELS)

    print("[load] 读取数据集(按原图组切分, train=%.0f%%)..." % (args.train_ratio * 100))
    # load 内部按 mode 无关方式缓存 contour，这里直接构造
    seg = HandSeg()
    seg.max_ratio, seg.min_ratio = 0.97, 0.005
    data = {}
    for d in sorted(os.listdir(args.dataset)):
        folder = os.path.join(args.dataset, d)
        if not os.path.isdir(folder) or d not in CLASS_MAP:
            continue
        files = sorted(glob.glob(os.path.join(folder, "*.jpg")) +
                       glob.glob(os.path.join(folder, "*.png")))
        keys = split_keys(files, args.train_ratio, args.seed)
        n_tr = max(1, int(len(keys) * args.train_ratio))
        tr_keys = set(keys[:n_tr])
        for fp in files:
            img = cv2.imread(fp)
            if img is None:
                continue
            cnt, _ = seg(img)
            if cnt is None:
                continue
            key = CLASS_MAP[d] or "unknown"
            split = "train" if group_key(fp) in tr_keys else "test"
            rec = data.setdefault((key, split), {"files": [], "cnts": []})
            rec["files"].append(fp)
            rec["cnts"].append(cnt)
        print("  %-9s %d 张 (train组 %d / test组 %d)" % (d, len(files), n_tr, len(keys) - n_tr))

    results = []
    print("\n=== 特征对比（留出法，L2 最近邻 + 未知阈值）===")
    print("%-8s %6s %9s %9s %9s" % ("特征", "维度", "总准确率", "已知类", "未知召回"))
    for m in MODES:
        r = build_and_eval(data, m, args.proto)
        if r is None:
            print("%-8s 特征提取失败" % m)
            continue
        results.append(r)
        print("%-8s %6d %8.1f%% %8.1f%% %8.1f%%"
              % (m, r["dim"], r["acc"], r["known_acc"], r["unk_recall"]))

    if not results:
        print("[ERR] 没有可用结果")
        return
    best = max(results, key=lambda r: r["acc"])
    if args.mode_override:
        forced = next((r for r in results if r["mode"] == args.mode_override), None)
        if forced:
            best = forced
            print("[info] 按参数强制使用 mode=%s" % args.mode_override)

    print("\n=== 最佳方案: %s  总准确率 %.1f%% (已知 %.1f%% / 未知召回 %.1f%%) ==="
          % (best["mode"], best["acc"], best["known_acc"], best["unk_recall"]))
    print("每类拒绝阈值: %s" % {k: round(v, 3) for k, v in best["cls_thr"].items()})
    print("混淆矩阵(行=真实, 列=预测)")
    print("        " + "".join("%8s" % c for c in LABELS + ["未知"]))
    for key in LABELS + ["unknown"]:
        print("%-8s%s" % (key, "".join("%8d" % best["conf"][key][c]
                                       for c in LABELS + ["未知"])))

    out = {
        "static": {lab: best["tpl"][lab] for lab in LABELS},
        "dynamic": {},
        "meta": {
            "mode": best["mode"], "dim": best["dim"],
            "cls_thr": {k: round(v, 4) for k, v in best["cls_thr"].items()},
            "thresh": round(best["thresh"], 4),
            "mu": best["mu"], "sd": best["sd"],
            "acc_holdout": round(best["acc"], 2),
            "known_acc": round(best["known_acc"], 2),
            "unk_recall": round(best["unk_recall"], 2),
            "all_modes": {r["mode"]: round(r["acc"], 2) for r in results},
        },
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("\n[OK] 最佳模板已写入 %s（mode=%s, 每类阈值如上）"
          % (args.out, best["mode"]))


if __name__ == "__main__":
    main()
