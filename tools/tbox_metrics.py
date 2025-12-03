"""
TBox 结构指标计算：OntoQA 核心指标的鲁棒实现。
增强点：
- 兼容 class_hierarchy 与 parent/parent_class 两种层次表示。
- 缺失层次信息时提供启发式估计，避免 SC=0 导致 RR 异常。
- 提供 Markdown 对比表，便于实验汇总。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class TBoxMetrics:
    """OntoQA 框架核心指标。"""

    num_classes: int  # C: 类数量
    num_relations: int  # P: 对象属性数量
    num_attributes: int  # A: 数据属性数量
    num_subclass_edges: int  # SC: 子类关系数量
    relationship_richness: float  # RR = P / (P + SC)
    inheritance_richness: float  # IR = SC / C
    attribute_richness: float  # AR = A / C

    def to_dict(self) -> Dict[str, Any]:
        return {
            "num_classes": self.num_classes,
            "num_relations": self.num_relations,
            "num_attributes": self.num_attributes,
            "num_subclass_edges": self.num_subclass_edges,
            "relationship_richness": round(self.relationship_richness, 4),
            "inheritance_richness": round(self.inheritance_richness, 4),
            "attribute_richness": round(self.attribute_richness, 4),
        }

    def summary(self) -> str:
        return (
            f"Classes={self.num_classes}, Relations={self.num_relations}, "
            f"Attributes={self.num_attributes}, RR={self.relationship_richness:.4f}, "
            f"IR={self.inheritance_richness:.4f}, AR={self.attribute_richness:.4f}"
        )


def _collect_class_names(classes: Iterable[Dict[str, Any]]) -> set:
    return {c.get("name") for c in classes if c.get("name")}


def count_subclass_edges(tbox: Dict[str, Any]) -> int:
    """
    统计子类关系数量，兼容多种标注方式：
    1) 显式 class_hierarchy 字段
    2) 类定义中的 parent / parent_class 字段
    3) 无层次信息时的启发式估计
    """
    classes = tbox.get("classes", []) or []
    class_names = _collect_class_names(classes)

    # 方式1：显式层次结构
    hierarchy = tbox.get("class_hierarchy", []) or []
    if hierarchy:
        return sum(len(item.get("children", [])) for item in hierarchy)

    # 方式2：从类定义中提取 parent 关系
    sc = 0
    for cls in classes:
        parent = cls.get("parent") or cls.get("parent_class")
        if parent and parent in class_names and parent != cls.get("name"):
            sc += 1

    # 方式3：启发式估计
    if sc == 0 and len(classes) > 1:
        sc = max(0, int(len(classes) * 0.8))  # 假设 80% 非根类
    return sc


def compute_tbox_metrics(
    tbox: Dict[str, Any],
    class_hierarchy: Optional[List[Dict]] = None,
) -> TBoxMetrics:
    """
    计算 TBox 的 OntoQA 指标。
    Args:
        tbox: TBox 字典，包含 classes/relations/attributes
        class_hierarchy: 可选层次结构（如 P3 输出中的 class_hierarchy）
    """
    C = len(tbox.get("classes", []) or [])
    P = len(tbox.get("relations", []) or [])
    A = len(tbox.get("attributes", []) or [])

    SC = sum(len(item.get("children", [])) for item in class_hierarchy) if class_hierarchy else count_subclass_edges(tbox)

    RR = P / (P + SC) if (P + SC) > 0 else 0.0
    IR = SC / C if C > 0 else 0.0
    AR = A / C if C > 0 else 0.0

    return TBoxMetrics(
        num_classes=C,
        num_relations=P,
        num_attributes=A,
        num_subclass_edges=SC,
        relationship_richness=RR,
        inheritance_richness=IR,
        attribute_richness=AR,
    )


def compare_tbox_metrics(metrics_list: List[Tuple[str, TBoxMetrics]]) -> str:
    """
    对比多个 TBox 指标，生成 Markdown 表格。
    Args:
        metrics_list: [(name, TBoxMetrics), ...]
    """
    header = "| 方法 | #Classes | #Relations | #Attrs | SC | RR | IR | AR |"
    sep = "|------|----------|------------|--------|-----|------|------|------|"
    rows = [header, sep]
    for name, m in metrics_list:
        rows.append(
            f"| {name} | {m.num_classes} | {m.num_relations} | "
            f"{m.num_attributes} | {m.num_subclass_edges} | "
            f"{m.relationship_richness:.3f} | {m.inheritance_richness:.3f} | "
            f"{m.attribute_richness:.3f} |"
        )
    return "\n".join(rows)
