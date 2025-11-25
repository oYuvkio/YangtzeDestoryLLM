# 本体定义（规定了有哪些实体类型和关系）

from dataclasses import dataclass
from typing import Dict


@dataclass
class Node:
    """表示图谱中的节点及其基本属性。"""
    id: str
    label: str  # e.g., "event", "location", "time", "cause", "impact", "measure"
    props: Dict


@dataclass
class Edge:
    """表示带方向的边，包含关系类型。"""
    src: str
    rel: str   # e.g., "occurs_in", "occurs_on", "caused_by", "has_impact", "handled_by"
    dst: str


RELATIONS = {
    "location": "occurs_in",
    "time": "occurs_on",
    "cause": "caused_by",
    "impact": "has_impact",
    "measure": "handled_by",
    "source": "sourced_from",
}
