"""
实体标准化/消歧模块：
- 支持地名、灾害术语的别名归一。
- 提供批量归一（triples/events）接口。
- 可自定义扩展映射，支持“别名包含”与“前缀/后缀模糊”匹配。
"""
from __future__ import annotations

from typing import Dict, List, Optional

# 长江流域地名标准化表
LOCATION_NORMALIZATION = {
    "武汉市": ["武汉", "江城", "武昌"],
    "宜昌市": ["宜昌", "三峡门户"],
    "重庆市": ["重庆", "山城"],
    "洞庭湖": ["洞庭", "八百里洞庭"],
    "鄱阳湖": ["鄱阳", "饶河"],
    "三峡水库": ["三峡大坝", "三峡工程", "三峡"],
    "长江中下游": ["中下游", "长江中下游干流"],
}

# 灾害术语标准化
DISASTER_TERM_NORMALIZATION = {
    "特大洪水": ["大洪水", "特大洪灾", "重大洪水"],
    "干旱": ["旱灾", "旱情", "大旱"],
    "暴雨": ["强降雨", "特大暴雨", "持续降雨"],
}


class EntityNormalizer:
    """实体标准化器，支持可扩展映射与模糊匹配。"""

    def __init__(self, custom_mappings: Optional[Dict[str, List[str]]] = None):
        base = {**LOCATION_NORMALIZATION, **DISASTER_TERM_NORMALIZATION}
        if custom_mappings:
            base.update(custom_mappings)
        self.mappings = base
        self.alias_to_canonical = self._build_reverse_map(base)

    @staticmethod
    def _build_reverse_map(mappings: Dict[str, List[str]]) -> Dict[str, str]:
        alias_to_canonical: Dict[str, str] = {}
        for canonical, aliases in mappings.items():
            alias_to_canonical[canonical] = canonical
            for alias in aliases:
                alias_to_canonical[alias] = canonical
        return alias_to_canonical

    def normalize(self, entity: str, entity_type: Optional[str] = None) -> str:
        """
        将实体名称标准化：
        1) 直接精确匹配别名表；
        2) 若未命中，尝试“包含式”模糊（如别名出现在实体子串中）；
        """
        if not entity:
            return entity
        e = entity.strip()
        # 精确匹配
        if e in self.alias_to_canonical:
            return self.alias_to_canonical[e]
        # 包含式模糊（避免过度匹配，限制在已知别名长度>1）
        for alias, canon in self.alias_to_canonical.items():
            if len(alias) > 1 and alias in e:
                return canon
        return e

    def normalize_triple(self, triple: dict) -> dict:
        return {
            "subject": self.normalize(triple.get("subject", "")),
            "predicate": triple.get("predicate", ""),
            "object": self.normalize(triple.get("object", "")),
            "event_id": triple.get("event_id", ""),
            "evidence": triple.get("evidence", ""),
        }

    def normalize_events(self, events: List[dict]) -> List[dict]:
        norm_events = []
        for event in events or []:
            ev = dict(event)
            space = ev.get("space", {}) or {}
            for key in ["main_stream", "tributaries", "provinces"]:
                if key in space and isinstance(space[key], list):
                    space[key] = [self.normalize(loc, "location") for loc in space[key]]
            ev["space"] = space
            norm_events.append(ev)
        return norm_events

    def normalize_extraction_result(self, result: dict) -> dict:
        norm_triples = [self.normalize_triple(t) for t in result.get("triples", []) or []]
        norm_events = self.normalize_events(result.get("events", []) or [])
        return {"events": norm_events, "triples": norm_triples}


# 兼容旧接口
def normalize_entity(entity: str, entity_type: str | None = None) -> str:
    return EntityNormalizer().normalize(entity, entity_type)


def normalize_extraction_result(result: dict) -> dict:
    return EntityNormalizer().normalize_extraction_result(result)
