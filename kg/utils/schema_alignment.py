"""
模式层对齐：用于多源 TBox 合并时的命名冲突与同义归一。
"""
from __future__ import annotations

from typing import Dict, List, Tuple

SYNONYM_TABLE = {
    "classes": {
        "FloodEvent": ["洪水事件", "洪灾", "水灾事件"],
        "DroughtEvent": ["干旱事件", "旱灾", "旱情"],
        "Province": ["省份", "省级行政区"],
        "EmergencyResponse": ["应急响应", "应急处置", "紧急响应"],
    },
    "relations": {
        "has_cause": ["caused_by", "致灾因子", "导致原因"],
        "affects_region": ["影响区域", "受灾区域", "涉及地区"],
        "triggers": ["触发", "启动", "引发"],
    },
}


class SchemaAligner:
    """简单的模式对齐器，基于预设同义表做名称归一。"""

    def __init__(self, synonym_table: Dict | None = None):
        self.synonym_table = synonym_table or SYNONYM_TABLE
        self._build_reverse_map()

    def _build_reverse_map(self):
        self.alias_to_canonical = {}
        for category, mappings in self.synonym_table.items():
            for canonical, aliases in mappings.items():
                for alias in aliases:
                    self.alias_to_canonical[(category, alias.lower())] = canonical

    def align_class_name(self, name: str) -> str:
        return self.alias_to_canonical.get(("classes", name.lower()), name)

    def align_relation_name(self, name: str) -> str:
        return self.alias_to_canonical.get(("relations", name.lower()), name)

    def merge_tboxes(self, base: dict, addon: dict, strategy: str = "base_priority") -> Tuple[dict, List[dict]]:
        """
        合并两个 TBox，返回 (merged, conflicts)。
        strategy: base_priority / addon_priority / manual
        """
        conflicts: List[dict] = []
        merged = {
            "classes": list(base.get("classes", [])),
            "relations": list(base.get("relations", [])),
            "attributes": list(base.get("attributes", [])),
        }
        existing_class_names = {c["name"] for c in merged["classes"] if c.get("name")}
        existing_rel_keys = {(r["name"], r.get("domain"), r.get("range")) for r in merged["relations"] if r.get("name")}

        # 合并类
        for c in addon.get("classes", []):
            aligned = self.align_class_name(c.get("name", ""))
            if aligned in existing_class_names:
                # 简单冲突检测：定义不同即记为冲突
                base_def = next((x for x in merged["classes"] if x["name"] == aligned), {}).get("definition")
                if base_def != c.get("definition"):
                    conflicts.append({"type": "class_definition_conflict", "name": aligned})
                continue
            merged["classes"].append({**c, "name": aligned})
            existing_class_names.add(aligned)

        # 合并关系
        for r in addon.get("relations", []):
            aligned = self.align_relation_name(r.get("name", ""))
            key = (aligned, r.get("domain"), r.get("range"))
            if key in existing_rel_keys:
                continue
            merged["relations"].append({**r, "name": aligned})
            existing_rel_keys.add(key)

        # 属性直接追加（可按 owner+name 去重）
        existing_attr_keys = {(a.get("owner"), a.get("name")) for a in merged["attributes"]}
        for a in addon.get("attributes", []):
            key = (a.get("owner"), a.get("name"))
            if key in existing_attr_keys:
                continue
            merged["attributes"].append(a)
            existing_attr_keys.add(key)

        if strategy == "addon_priority":
            # 简化策略：如果冲突且 addon_priority，直接覆盖定义
            for c in addon.get("classes", []):
                aligned = self.align_class_name(c.get("name", ""))
                for i, bc in enumerate(merged["classes"]):
                    if bc.get("name") == aligned:
                        merged["classes"][i] = {**bc, **c, "name": aligned}
            # 关系冲突覆盖可按需扩展

        return merged, conflicts
