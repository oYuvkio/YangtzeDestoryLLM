"""
模式冲突检测：识别 TBox 中的潜在问题，供 P3/P4 后自检和人工审阅。
覆盖的检查项：
1) 悬空关系/属性：domain、range、owner 不在类集合中，或缺失。
2) 重复/冲突定义：类定义不一致、同名关系不同签名或多重定义。
3) 孤立类：未被任何关系/属性连接。
4) 空/极短定义：definition 为空或过短。
5) 名称重复（大小写差异）：同名类大小写不同。
"""
from __future__ import annotations

from typing import Any, Dict, List, Set


def detect_schema_conflicts(tbox: Dict[str, Any]) -> List[Dict[str, Any]]:
    conflicts: List[Dict[str, Any]] = []

    classes = tbox.get("classes", []) or []
    relations = tbox.get("relations", []) or []
    attributes = tbox.get("attributes", []) or []

    class_names: Set[str] = {c.get("name") for c in classes if c.get("name")}

    # 1) 类定义冲突 & 名称重复（大小写差异）
    class_defs: Dict[str, str] = {}
    seen_lower: Dict[str, str] = {}
    for c in classes:
        name = c.get("name")
        if not name:
            continue
        definition = c.get("definition", "") or ""
        # 定义冲突
        if name in class_defs and class_defs[name] != definition:
            conflicts.append(
                {
                    "type": "class_definition_conflict",
                    "name": name,
                    "def_a": class_defs[name],
                    "def_b": definition,
                }
            )
        class_defs[name] = definition
        # 大小写重复
        lower = name.lower()
        if lower in seen_lower and seen_lower[lower] != name:
            conflicts.append(
                {
                    "type": "duplicate_class_name_case",
                    "class1": seen_lower[lower],
                    "class2": name,
                    "message": f"类名大小写不同但含义相近：{seen_lower[lower]} vs {name}",
                }
            )
        else:
            seen_lower[lower] = name

    # 2) 关系完整性与重复签名/多重定义
    rel_signatures: Dict[str, Set[tuple]] = {}
    for r in relations:
        name = r.get("name")
        dom = r.get("domain")
        rng = r.get("range")
        definition = r.get("definition", "") or ""

        if not name or not dom or not rng:
            conflicts.append(
                {
                    "type": "relation_missing_domain_range",
                    "name": name or "",
                    "domain": dom or "",
                    "range": rng or "",
                }
            )
            continue

        if dom not in class_names:
            conflicts.append(
                {
                    "type": "dangling_domain",
                    "relation": name,
                    "domain": dom,
                    "message": f"关系 '{name}' 的 domain '{dom}' 不在类集合中",
                }
            )
        if rng not in class_names:
            conflicts.append(
                {
                    "type": "dangling_range",
                    "relation": name,
                    "range": rng,
                    "message": f"关系 '{name}' 的 range '{rng}' 不在类集合中",
                }
            )

        rel_signatures.setdefault(name, set()).add((dom, rng, definition))
        if len(rel_signatures[name]) > 1:
            conflicts.append(
                {
                    "type": "relation_same_name_multi_def",
                    "relation": name,
                    "message": "同名关系出现多个(domain, range, definition) 组合",
                }
            )

    # 3) 属性完整性
    for a in attributes:
        owner = a.get("owner")
        if not owner or owner not in class_names:
            conflicts.append(
                {
                    "type": "dangling_attribute",
                    "attribute": a.get("name", ""),
                    "owner": owner or "",
                    "message": f"属性 '{a.get('name','')}' 的 owner '{owner}' 不在类集合中",
                }
            )

    # 4) 孤立类：未被任何关系/属性连接
    connected: Set[str] = set()
    for r in relations:
        connected.add(r.get("domain", ""))
        connected.add(r.get("range", ""))
    for a in attributes:
        connected.add(a.get("owner", ""))
    for c in classes:
        name = c.get("name")
        if name and name not in connected:
            conflicts.append(
                {
                    "type": "isolated_class",
                    "class": name,
                    "message": f"类 '{name}' 未出现在任何关系或属性中",
                }
            )

    # 5) 空/极短定义
    for c in classes:
        name = c.get("name", "")
        definition = (c.get("definition") or "").strip()
        if name and (not definition or len(definition) < 5):
            conflicts.append(
                {
                    "type": "empty_definition",
                    "class": name,
                    "message": f"类 '{name}' 的定义为空或过短",
                }
            )

    return conflicts


def summarize_conflicts(conflicts: List[Dict[str, Any]]) -> Dict[str, int]:
    """按类型汇总冲突数量，便于快速浏览。"""
    summary: Dict[str, int] = {}
    for c in conflicts:
        ctype = c.get("type", "unknown")
        summary[ctype] = summary.get(ctype, 0) + 1
    return summary


def filter_critical_conflicts(conflicts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    过滤出关键冲突（domain/range/owner 悬空），需优先处理。
    """
    critical_types = {"dangling_domain", "dangling_range", "dangling_attribute", "relation_missing_domain_range"}
    return [c for c in conflicts if c.get("type") in critical_types]
