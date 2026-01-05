#!/usr/bin/env python3
"""
创建优化版 TBox：在 S2/S3 基础上添加通用高频关系

使用方式：
    # 创建 S2 优化版
    python scripts/create_optimized_tbox.py --version s2

    # 创建 S3 优化版
    python scripts/create_optimized_tbox.py --version s3

    # 同时创建两个版本
    python scripts/create_optimized_tbox.py --version all
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


# 需要添加的通用高频关系
UNIVERSAL_RELATIONS: List[Dict[str, Any]] = [
    {
        "name": "occurs_at",
        "cn_name": "发生于",
        "domain": "DisasterEvent",
        "range": "TemporalEntity",
        "definition": "描述事件发生的时间点或时间段",
        "functional": False,
    },
    {
        "name": "has_value",
        "cn_name": "具有数值",
        "domain": "HydrologicalStation",
        "range": "NumericValue",
        "definition": "描述水文站、设施或区域的测量数值，如水位、流量、损失金额等",
        "functional": False,
    },
    {
        "name": "part_of",
        "cn_name": "属于",
        "domain": "GeographicRegion",
        "range": "GeographicRegion",
        "definition": "描述地理区域、组织或设施之间的层级隶属关系",
        "functional": False,
    },
    {
        "name": "has_duration",
        "cn_name": "持续时间",
        "domain": "DisasterEvent",
        "range": "TemporalEntity",
        "definition": "描述事件或过程的持续时间长度",
        "functional": True,
    },
    {
        "name": "operated_by",
        "cn_name": "由...运营",
        "domain": "FloodControlProject",
        "range": "Organization",
        "definition": "描述工程设施的管理运营机构",
        "functional": True,
    },
    {
        "name": "constructed_in",
        "cn_name": "建成于",
        "domain": "FloodControlProject",
        "range": "TemporalEntity",
        "definition": "描述工程设施的建成时间",
        "functional": True,
    },
]

# 添加时间实体类
TEMPORAL_CLASS: Dict[str, Any] = {
    "name": "TemporalEntity",
    "cn_name": "时间实体",
    "definition": "表示时间点或时间段的实体，包括年份、日期、时间范围等",
    "examples": ["1998年", "2022年8月", "7月至9月", "45天"],
    "parent": None,
}

# 添加数值实体类
NUMERIC_CLASS: Dict[str, Any] = {
    "name": "NumericValue",
    "cn_name": "数值",
    "definition": "表示测量值、统计数据或定量指标的实体",
    "examples": ["45.22米", "2000亿元", "2.23亿人", "680万间"],
    "parent": None,
}


def find_tbox_file(version: str, base_dir: Path) -> Path:
    """查找指定版本的 TBox 文件"""
    # 优先使用 t0p80 版本
    patterns = [
        f"p4_tbox_dedup_{version}_allow1_*_t0p80.json",
        f"p4_tbox_dedup_{version}_allow1_*_t0p75.json",
        f"p4_tbox_dedup_{version}_allow1_*_t0p70.json",
        f"p4_tbox_dedup_{version}_allow1_*.json",
    ]

    for pattern in patterns:
        matches = list(base_dir.glob(pattern))
        if matches:
            return sorted(matches)[-1]  # 取最新的

    raise FileNotFoundError(f"找不到 {version} 版本的 TBox 文件")


def optimize_tbox(input_path: Path, output_path: Path) -> Dict[str, Any]:
    """在原始 TBox 基础上添加通用关系"""

    # 加载原始 TBox
    tbox = json.loads(input_path.read_text(encoding="utf-8"))

    original_classes = len(tbox.get("classes", []))
    original_relations = len(tbox.get("relations", []))

    print(f"  原始 TBox: {original_classes} 类, {original_relations} 关系")

    # 检查并添加时间和数值类
    existing_class_names = {c["name"] for c in tbox.get("classes", [])}

    if "TemporalEntity" not in existing_class_names:
        tbox["classes"].append(TEMPORAL_CLASS)
        print(f"  + 添加类: TemporalEntity (时间实体)")

    if "NumericValue" not in existing_class_names:
        tbox["classes"].append(NUMERIC_CLASS)
        print(f"  + 添加类: NumericValue (数值)")

    # 添加通用关系
    existing_relation_names = {r["name"] for r in tbox.get("relations", [])}

    for rel in UNIVERSAL_RELATIONS:
        if rel["name"] not in existing_relation_names:
            tbox["relations"].append(rel)
            print(f"  + 添加关系: {rel['name']} ({rel['cn_name']})")

    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(tbox, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n  优化后: {len(tbox['classes'])} 类, {len(tbox['relations'])} 关系")
    print(f"  输出: {output_path}")

    return tbox


def main() -> None:
    parser = argparse.ArgumentParser(description="创建优化版 TBox")
    parser.add_argument(
        "--version",
        choices=["s2", "s3", "all"],
        default="all",
        help="TBox 版本 (s2/s3/all)",
    )
    parser.add_argument(
        "--input-dir",
        default="outputs/cq_pipeline/final",
        help="输入目录",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/cq_pipeline/final",
        help="输出目录",
    )

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    versions = ["s2", "s3"] if args.version == "all" else [args.version]

    print("=" * 60)
    print("创建优化版 TBox")
    print("=" * 60)

    for version in versions:
        print(f"\n[{version.upper()}]")

        try:
            input_path = find_tbox_file(version, input_dir)
            print(f"  输入: {input_path.name}")

            output_path = output_dir / f"tbox_{version}_optimized.json"
            optimize_tbox(input_path, output_path)

        except FileNotFoundError as e:
            print(f"  错误: {e}")
            continue

    print("\n" + "=" * 60)
    print("完成")
    print("=" * 60)


if __name__ == "__main__":
    main()
