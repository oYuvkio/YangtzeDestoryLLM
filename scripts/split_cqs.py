#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把 CQ 列表拆分为 train/test（对齐论文“扩展集/测试集”做法）。

设计目标：
- 支持按 category 分层抽样（尽量保持 train/test 类别分布一致）
- 输出两个文件：p1_cqs_train.json / p1_cqs_test.json（结构与现有兼容）

示例：
  python3 scripts/split_cqs.py \
    --in outputs/cq_pipeline/final/p1_cqs.json \
    --train-ratio 0.7 \
    --seed 42 \
    --out-train outputs/cq_pipeline/final/p1_cqs_train.json \
    --out-test outputs/cq_pipeline/final/p1_cqs_test.json
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _load_cqs(path: Path) -> List[Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "cqs" in data:
        cqs = data.get("cqs", [])
    elif isinstance(data, list):
        cqs = data
    else:
        raise ValueError(f"无法识别的 CQ 格式：{path}")
    if not isinstance(cqs, list):
        raise ValueError(f"cqs 必须是 list：{path}")
    # 只保留 dict
    return [c for c in cqs if isinstance(c, dict)]


def _split_stratified(
    items: List[Dict[str, Any]],
    train_ratio: float,
    seed: int,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    rng = random.Random(seed)
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for item in items:
        cat = str(item.get("category", "") or "").strip() or "__NO_CATEGORY__"
        buckets[cat].append(item)

    train: List[Dict[str, Any]] = []
    test: List[Dict[str, Any]] = []
    for _cat, bucket in buckets.items():
        rng.shuffle(bucket)
        k = int(round(len(bucket) * train_ratio))
        # 防止极小 bucket 全进同一侧：至少留 1 个到 test（当 len>=2）
        if len(bucket) >= 2:
            k = min(max(k, 1), len(bucket) - 1)
        train.extend(bucket[:k])
        test.extend(bucket[k:])
    return train, test


def _dump(path: Path, cqs: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"cqs": cqs}, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="拆分 CQ 为 train/test（按 category 分层）")
    parser.add_argument("--in", dest="in_path", required=True, help="输入 CQ 文件（含 cqs 或 list）")
    parser.add_argument("--train-ratio", type=float, default=0.7, help="训练集比例（默认 0.7）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子（默认 42）")
    parser.add_argument("--out-train", required=True, help="训练集输出路径")
    parser.add_argument("--out-test", required=True, help="测试集输出路径")
    args = parser.parse_args()

    in_path = Path(args.in_path)
    if not in_path.exists():
        raise FileNotFoundError(f"输入文件不存在：{in_path}")

    cqs = _load_cqs(in_path)
    if not cqs:
        raise ValueError("输入 CQ 为空")

    train, test = _split_stratified(cqs, train_ratio=args.train_ratio, seed=args.seed)

    out_train = Path(args.out_train)
    out_test = Path(args.out_test)
    _dump(out_train, train)
    _dump(out_test, test)

    print(f"[SPLIT] 输入 CQ: {len(cqs)}")
    print(f"[SPLIT] train: {len(train)} -> {out_train}")
    print(f"[SPLIT] test : {len(test)} -> {out_test}")


if __name__ == "__main__":
    main()

