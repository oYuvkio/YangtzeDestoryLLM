# 本体定义（规定了有哪些实体类型和关系）

from dataclasses import dataclass
from typing import Dict

@dataclass
class Node:
    id: str
    label: str  # e.g., "event", "location", "time", "cause", "impact", "measure"
    props: Dict

@dataclass
class Edge:
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
