"""
实验目标：对比 P3 基线 TBox 与 P4 增强 TBox 的结构指标（类/关系/属性数量与均值），用于论文/答辩说明“文献增强是否让模式更丰富”。

使用说明：
1) 默认读取基线 TBox：outputs/cq_pipeline/final/p3_tbox_normalized.json
2) 默认读取增强 TBox：outputs/cq_pipeline/final/p4_tbox_augmented.json（可替换为 s2_allow0/s2_allow1 等版本）
3) 无需调用 LLM，直接计算本体结构指标。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from kg.cq_pipeline import TBoxSchema, ClassDef, RelationDef, AttributeDef


@dataclass
class OntoStats:
    # 本体结构指标
    num_classes: int
    num_relations: int
    num_attributes: int
    avg_relations_per_class: float
    avg_attributes_per_class: float


def compute_onto_stats(schema: TBoxSchema) -> OntoStats:
    """
    算法原理：统计类、关系、属性数量，并计算“每类平均关联关系数”和“每类平均属性数”。
    - 关系计数：对每个类统计作为 domain 或 range 出现的次数，反映模式连通度。
    - 属性计数：对每个类统计拥有的属性数量，反映信息粒度。
    """
    num_classes = len(schema.classes)
    num_relations = len(schema.relations)
    num_attributes = len(schema.attributes)
    if num_classes == 0:
        return OntoStats(0, 0, 0, 0.0, 0.0)

    rel_counts = {c.name: 0 for c in schema.classes}
    for r in schema.relations:
        if r.domain in rel_counts:
            rel_counts[r.domain] += 1
        if r.range in rel_counts:
            rel_counts[r.range] += 1

    attr_counts = {c.name: 0 for c in schema.classes}
    for a in schema.attributes:
        if a.owner in attr_counts:
            attr_counts[a.owner] += 1

    avg_rel = sum(rel_counts.values()) / float(num_classes)
    avg_attr = sum(attr_counts.values()) / float(num_classes)
    return OntoStats(
        num_classes=num_classes,
        num_relations=num_relations,
        num_attributes=num_attributes,

        avg_relations_per_class=avg_rel,
        avg_attributes_per_class=avg_attr,
    )


def load_tbox(path: Path) -> TBoxSchema:
    """从 JSON 文件加载 TBox。要求包含 classes/relations/attributes 三个键。"""
    data = json.loads(path.read_text(encoding="utf-8"))
    return TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])],
    )


def compare_onto():
    """
    实验设计逻辑：
    1) 选择基线 TBox（仅 CQ+P3，未经文献增强），作为 TBox0。
    2) 选择增强 TBox（默认 p4_tbox_augmented.json，可替换为 s2_allow0/s2_allow1 等版本），作为 TBox1。
    3) 计算结构指标并输出，观察 P4 增强对类/关系/属性规模及均值的影响。
    """
    final_dir = Path("outputs/cq_pipeline/final")
    tbox0_path = final_dir / "p3_tbox_normalized.json"
    # 如需对比不同增强配置，可改为：
    # tbox1_path = final_dir / "p4_tbox_augmented_s2_allow0.json"  # 不允许新类，support=2
    # tbox1_path = final_dir / "p4_tbox_augmented_s2_allow1.json"  # 允许新类，support=2
    tbox1_path = final_dir / "p4_tbox_augmented_s3_allow1.json"  # 允许新类，support=3
    # tbox1_path = final_dir / "p4_tbox_augmented.json"

    if not tbox0_path.exists():
        raise FileNotFoundError(f"缺少基线 TBox：{tbox0_path}")
    if not tbox1_path.exists():
        raise FileNotFoundError(f"缺少增强后 TBox：{tbox1_path}")

    tbox0 = load_tbox(tbox0_path)
    tbox1 = load_tbox(tbox1_path)

    stats0 = compute_onto_stats(tbox0)
    stats1 = compute_onto_stats(tbox1)

    print("==== Onto 结构指标对比 (P3 基线 vs P4 增强) ====")
    print(
        f"Baseline(TBox0): 类 {stats0.num_classes}, 关系 {stats0.num_relations}, 属性 {stats0.num_attributes}, "
        f"avg_rel/class={stats0.avg_relations_per_class:.2f}, avg_attr/class={stats0.avg_attributes_per_class:.2f}"
    )
    print(
        f"Augmented(TBox1): 类 {stats1.num_classes}, 关系 {stats1.num_relations}, 属性 {stats1.num_attributes}, "
        f"avg_rel/class={stats1.avg_relations_per_class:.2f}, avg_attr/class={stats1.avg_attributes_per_class:.2f}"
    )


if __name__ == "__main__":
    compare_onto()
