#!/usr/bin/env python3
"""
三元组方向归一化

根据 TBox 的 domain/range 定义，自动校正主宾颠倒的三元组。

问题背景：
- Gold: (人为因素, has_hazard_factor, 洪水) - 主宾可能标反
- Pred: (洪水, has_hazard_factor, 人类活动) - 符合 TBox 定义
- 结果：即使语义相近，因为主宾颠倒导致不匹配

解决方案：
1. 加载 TBox 获取关系的 domain/range 定义
2. 推断三元组中实体的类型
3. 如果方向反了（subject 类型匹配 range，object 类型匹配 domain），交换主宾
4. 使用强制规则层处理常见的颠倒模式

使用方式：
    python scripts/p5/normalize_triple_direction.py \
        --input data/p5_eval_pool/gold.jsonl \
        --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \
        --output data/p5_eval_pool/gold_normalized.jsonl

    # 同时归一化 Gold 和 Pred
    python scripts/p5/normalize_triple_direction.py \
        --gold data/p5_eval_pool/gold.jsonl \
        --pred outputs/eval_models/xxx/predictions.jsonl \
        --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json \
        --gold-out data/p5_eval_pool/gold_normalized.jsonl \
        --pred-out outputs/eval_models/xxx/predictions_normalized.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Set, Tuple, Union


# ============================================================================
# 强制方向规则：基于关键词的主宾方向检查
# 注意：使用较长的关键词组合避免误匹配
# ============================================================================
FORCED_DIRECTION_RULES = {
    "affects_region": {
        # 主语应该是灾害/事件类
        "subject_keywords": ["洪水", "洪涝", "旱灾", "干旱", "灾害", "内涝", "洪患", "天气过程", "汛情"],
        # 宾语应该是地理区域类
        "object_keywords": ["省", "市", "县", "区", "流域", "地区", "河段", "中下游", "上游", "下游"]
    },
    "has_hazard_factor": {
        # 主语应该是灾害/事件类
        "subject_keywords": ["洪水", "洪涝", "旱灾", "干旱", "灾害", "洪患"],
        # 宾语应该是致灾因子类
        "object_keywords": ["暴雨", "降雨", "人为因素", "人类活动", "气候", "因素", "条件", "地形", "淤积", "崩岸"]
    },
    "belongs_to_basin": {
        # 主语应该是具体地点/河流/湖泊
        "subject_keywords": ["湖", "洞庭", "鄱阳", "太湖", "金沙江", "嘉陵江", "汉江", "岷江"],
        # 宾语应该是流域/水系
        "object_keywords": ["流域", "水系"]
    },
    "influenced_by_climate": {
        # 主语应该是事件/过程
        "subject_keywords": ["洪水", "干旱", "天气", "灾害", "过程"],
        # 宾语应该是气候现象
        "object_keywords": ["厄尔尼诺", "拉尼娜", "气候", "季风", "台风"]
    },
    # ============ 新增规则: 基于诊断报告 swap_examples ============
    "commands": {
        # Organization → Organization (上级指挥下级)
        "subject_keywords": ["指挥部", "总指挥", "防总", "水利部", "应急管理部", "防汛抗旱指挥部"],
        "object_keywords": ["组", "队", "办", "站", "中心", "工作组"]
    },
    "responsible_for": {
        # Organization → EmergencyMeasure
        "subject_keywords": ["指挥部", "政府", "部门", "委员会", "水利部", "应急管理部"],
        "object_keywords": ["措施", "任务", "工作", "抢险", "救灾", "转移", "安置"]
    },
    "causes_impact": {
        # DisasterEvent → DisasterImpact
        "subject_keywords": ["洪水", "干旱", "灾害", "洪涝", "暴雨", "洪患", "旱灾"],
        "object_keywords": ["损失", "伤亡", "受灾", "倒塌", "淹没", "减产", "死亡", "失踪"]
    },
    "protects_region": {
        # FloodControlProject → GeographicRegion
        "subject_keywords": ["水库", "大坝", "堤", "堰", "闸", "蓄滞洪区", "分洪区", "堤防"],
        "object_keywords": ["省", "市", "县", "区", "地区", "平原", "城市", "城区"]
    },
    "monitors_river": {
        # HydrologicalStation → River
        "subject_keywords": ["站", "水文站", "测站", "监测站"],
        "object_keywords": ["江", "河", "水", "流域", "长江", "汉江", "嘉陵江"]
    },
    "located_on_river": {
        # FloodControlProject → River
        "subject_keywords": ["水库", "大坝", "堤", "闸", "站", "枢纽", "堤防"],
        "object_keywords": ["江", "河", "水", "长江", "汉江", "嘉陵江"]
    },
    "flows_into": {
        # River → River
        "subject_keywords": ["支流", "溪", "沟", "河", "江"],
        "object_keywords": ["长江", "干流", "主流"]
    },
    "has_loss_value": {
        # DisasterImpact → NumericValue
        "subject_keywords": ["损失", "伤亡", "受灾", "倒塌", "死亡", "失踪", "受灾面积"],
        "object_keywords": ["亿", "万", "元", "人", "公顷", "间", "头", "座"]
    },
    "implements_measure": {
        # EmergencyResponse → EmergencyMeasure
        "subject_keywords": ["响应", "应急", "防汛", "抗旱", "级响应"],
        "object_keywords": ["措施", "转移", "抢险", "调度", "安置", "救援"]
    },
    "issues_response": {
        # Organization → EmergencyResponse
        "subject_keywords": ["指挥部", "政府", "部门", "水利部", "应急管理部"],
        "object_keywords": ["响应", "级响应", "预警", "应急响应"]
    }
}


def check_forced_swap(subject: str, predicate: str, obj: str) -> Optional[bool]:
    """
    检查是否需要强制交换主宾

    Args:
        subject: 主语
        predicate: 谓语（关系）
        obj: 宾语

    Returns:
        True: 需要交换
        False: 不需要交换
        None: 无法判断（交给 TBox 规则处理）
    """
    pred_lower = predicate.lower()

    if pred_lower not in FORCED_DIRECTION_RULES:
        return None

    rules = FORCED_DIRECTION_RULES[pred_lower]
    subj_kws = rules.get("subject_keywords", [])
    obj_kws = rules.get("object_keywords", [])

    # 检查主语是否包含应该在主语位置的关键词
    subj_has_subj_kw = any(kw in subject for kw in subj_kws)
    # 检查宾语是否包含应该在宾语位置的关键词
    obj_has_obj_kw = any(kw in obj for kw in obj_kws)

    # 检查主语是否包含应该在宾语位置的关键词（错位）
    subj_has_obj_kw = any(kw in subject for kw in obj_kws)
    # 检查宾语是否包含应该在主语位置的关键词（错位）
    obj_has_subj_kw = any(kw in obj for kw in subj_kws)

    # 明确的错位情况：主语有宾语关键词 且 宾语有主语关键词
    if subj_has_obj_kw and obj_has_subj_kw:
        return True

    # 明确的正确情况：主语有主语关键词 且 宾语有宾语关键词
    if subj_has_subj_kw and obj_has_obj_kw:
        return False

    # 无法确定，返回 None 让 TBox 规则处理
    return None


def load_tbox(tbox_path: Path) -> Dict[str, Any]:
    """加载 TBox"""
    return json.loads(tbox_path.read_text(encoding="utf-8"))


def build_relation_schema(tbox: Dict[str, Any]) -> Dict[str, Tuple[str, str]]:
    """
    构建关系 -> (domain, range) 映射

    Returns:
        Dict[relation_name, (domain_class, range_class)]
    """
    schema = {}
    for rel in tbox.get("relations", []):
        name = rel.get("name", "")
        domain = rel.get("domain", "")
        range_ = rel.get("range", "")
        if name:
            schema[name.lower()] = (domain, range_)
    return schema


def build_class_hierarchy(tbox: Dict[str, Any]) -> Dict[str, Set[str]]:
    """
    构建类层次结构（包含父类）

    Returns:
        Dict[class_name, set(class_name + all_parent_classes)]
    """
    hierarchy = {}
    classes = {c.get("name", ""): c for c in tbox.get("classes", []) if c.get("name")}

    for cls_name, cls_def in classes.items():
        parents = set([cls_name])
        # 追踪父类
        parent = cls_def.get("parent", "")
        while parent and parent in classes:
            parents.add(parent)
            parent = classes[parent].get("parent", "")
        hierarchy[cls_name] = parents

    return hierarchy


def build_entity_type_hints(tbox: Dict[str, Any]) -> Dict[str, str]:
    """
    构建实体名 -> 类型的启发式映射

    基于类的 cn_name 和定义来推断
    """
    hints = {}

    # 从 TBox classes 中提取关键词
    for cls in tbox.get("classes", []):
        cls_name = cls.get("name", "")
        cn_name = cls.get("cn_name", "")
        definition = cls.get("definition", "")

        if cn_name:
            # 中文名直接映射
            hints[cn_name.lower()] = cls_name

        # 从定义中提取关键词
        if definition:
            keywords = re.findall(r'[\u4e00-\u9fa5]+', definition)
            for kw in keywords:
                if len(kw) >= 2:
                    hints[kw.lower()] = cls_name

    # 添加常见的领域关键词映射
    domain_hints = {
        # 灾害事件类
        "洪水": "FloodEvent",
        "洪涝": "FloodEvent",
        "洪灾": "FloodEvent",
        "水灾": "FloodEvent",
        "旱灾": "DroughtEvent",
        "干旱": "DroughtEvent",
        "旱情": "DroughtEvent",
        # 地理实体类
        "长江": "River",
        "黄河": "River",
        "湖泊": "Lake",
        "水库": "Reservoir",
        "流域": "Basin",
        "省": "GeographicRegion",
        "市": "GeographicRegion",
        "县": "GeographicRegion",
        # 致灾因子类
        "暴雨": "ClimateAnomaly",
        "降雨": "ClimateAnomaly",
        "降水": "ClimateAnomaly",
        "气候": "ClimateAnomaly",
        "人为因素": "HumanActivity",
        "人类活动": "HumanActivity",
        # 时间实体
        "年": "TemporalEntity",
        "月": "TemporalEntity",
        "日": "TemporalEntity",
    }
    hints.update(domain_hints)

    return hints


def infer_entity_type(
    entity: str,
    entity_type_hints: Dict[str, str],
    class_hierarchy: Dict[str, Set[str]]
) -> Optional[str]:
    """
    推断实体的类型

    Args:
        entity: 实体名称
        entity_type_hints: 实体名 -> 类型的启发式映射
        class_hierarchy: 类层次结构

    Returns:
        推断的类型名称，或 None
    """
    entity_lower = entity.lower()

    # 1. 精确匹配
    if entity_lower in entity_type_hints:
        return entity_type_hints[entity_lower]

    # 2. 包含匹配（关键词在实体名中）
    for keyword, cls_name in entity_type_hints.items():
        if keyword in entity_lower:
            return cls_name

    # 3. 基于后缀的启发式规则
    if entity.endswith("站"):
        return "HydrologicalStation"
    if entity.endswith("水库"):
        return "Reservoir"
    if entity.endswith("湖"):
        return "Lake"
    if re.match(r'^\d{4}年', entity):
        # 以年份开头，可能是事件
        if any(kw in entity for kw in ["洪水", "洪涝", "旱灾", "干旱"]):
            return "DisasterEvent"
        return "TemporalEntity"

    return None


def type_matches_constraint(
    inferred_type: Optional[str],
    constraint_type: Union[str, List[str]],
    class_hierarchy: Dict[str, Set[str]]
) -> bool:
    """
    检查推断的类型是否匹配约束类型（考虑继承关系）

    Args:
        inferred_type: 推断的实体类型
        constraint_type: 约束类型，可以是单个字符串或字符串列表
        class_hierarchy: 类层次结构
    """
    if not inferred_type or not constraint_type:
        return True  # 无法判断，默认匹配

    # 将 constraint_type 统一为列表
    if isinstance(constraint_type, str):
        constraint_types = [constraint_type]
    else:
        constraint_types = constraint_type

    # 检查是否匹配任一约束类型
    for ct in constraint_types:
        # 检查是否是约束类型或其子类
        if inferred_type in class_hierarchy:
            if ct in class_hierarchy[inferred_type]:
                return True
        # 简单字符串匹配
        if inferred_type.lower() == ct.lower():
            return True

    return False


def normalize_triple(
    triple: Dict[str, Any],
    relation_schema: Dict[str, Tuple[str, str]],
    entity_type_hints: Dict[str, str],
    class_hierarchy: Dict[str, Set[str]]
) -> Tuple[Dict[str, Any], bool, str]:
    """
    归一化单个三元组的方向

    Args:
        triple: 三元组字典
        relation_schema: 关系 -> (domain, range) 映射
        entity_type_hints: 实体类型启发式映射
        class_hierarchy: 类层次结构

    Returns:
        (normalized_triple, was_swapped, swap_reason)
    """
    subject = triple.get("subject", "")
    predicate = triple.get("predicate", "")
    obj = triple.get("object", "")

    # 1. 首先检查强制规则
    forced_swap = check_forced_swap(subject, predicate, obj)
    if forced_swap is True:
        # 强制交换
        normalized = dict(triple)
        normalized["subject"] = obj
        normalized["object"] = subject
        normalized["_direction_swapped"] = True
        normalized["_swap_reason"] = "forced_rule"
        normalized["_original_subject"] = subject
        normalized["_original_object"] = obj
        return normalized, True, "forced_rule"
    elif forced_swap is False:
        # 强制不交换
        return triple, False, "forced_rule_correct"

    # 2. 如果强制规则无法判断，使用 TBox domain/range 规则
    pred_lower = predicate.lower()
    if pred_lower not in relation_schema:
        return triple, False, "unknown_predicate"

    domain, range_ = relation_schema[pred_lower]

    if not domain or not range_:
        return triple, False, "no_domain_range"

    # 推断 subject 和 object 的类型
    subject_type = infer_entity_type(subject, entity_type_hints, class_hierarchy)
    object_type = infer_entity_type(obj, entity_type_hints, class_hierarchy)

    # 检查当前方向是否正确
    subject_matches_domain = type_matches_constraint(subject_type, domain, class_hierarchy)
    object_matches_range = type_matches_constraint(object_type, range_, class_hierarchy)

    # 检查反转后是否更合理
    subject_matches_range = type_matches_constraint(subject_type, range_, class_hierarchy)
    object_matches_domain = type_matches_constraint(object_type, domain, class_hierarchy)

    # 决定是否需要交换
    current_score = (1 if subject_matches_domain else 0) + (1 if object_matches_range else 0)
    swapped_score = (1 if subject_matches_range else 0) + (1 if object_matches_domain else 0)

    if swapped_score > current_score:
        # 交换主宾
        normalized = dict(triple)
        normalized["subject"] = obj
        normalized["object"] = subject
        normalized["_direction_swapped"] = True
        normalized["_swap_reason"] = "tbox_rule"
        normalized["_original_subject"] = subject
        normalized["_original_object"] = obj
        return normalized, True, "tbox_rule"

    return triple, False, "correct"


def normalize_file(
    input_path: Path,
    output_path: Path,
    relation_schema: Dict[str, Tuple[str, str]],
    entity_type_hints: Dict[str, str],
    class_hierarchy: Dict[str, Set[str]]
) -> Dict[str, int]:
    """
    归一化文件中的所有三元组

    Returns:
        统计信息
    """
    stats = {
        "total_records": 0,
        "total_triples": 0,
        "swapped_triples": 0,
        "swap_by_forced_rule": 0,
        "swap_by_tbox_rule": 0,
    }

    with open(input_path, encoding="utf-8") as f_in, \
         open(output_path, "w", encoding="utf-8") as f_out:
        for line in f_in:
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                f_out.write(line + "\n")
                continue

            stats["total_records"] += 1

            # 归一化三元组
            triples = record.get("triples", [])
            normalized_triples = []

            for triple in triples:
                stats["total_triples"] += 1
                normalized, was_swapped, reason = normalize_triple(
                    triple, relation_schema, entity_type_hints, class_hierarchy
                )
                normalized_triples.append(normalized)
                if was_swapped:
                    stats["swapped_triples"] += 1
                    if reason == "forced_rule":
                        stats["swap_by_forced_rule"] += 1
                    elif reason == "tbox_rule":
                        stats["swap_by_tbox_rule"] += 1

            record["triples"] = normalized_triples
            f_out.write(json.dumps(record, ensure_ascii=False) + "\n")

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="三元组方向归一化")

    # 单文件模式
    parser.add_argument("--input", "-i", default=None, help="输入文件（单文件模式）")
    parser.add_argument("--output", "-o", default=None, help="输出文件（单文件模式）")

    # 双文件模式
    parser.add_argument("--gold", "-g", default=None, help="Gold 文件")
    parser.add_argument("--pred", "-p", default=None, help="Pred 文件")
    parser.add_argument("--gold-out", "-go", default=None, help="归一化后的 Gold 文件")
    parser.add_argument("--pred-out", "-po", default=None, help="归一化后的 Pred 文件")

    # TBox
    parser.add_argument("--tbox", "-t", required=True, help="TBox 文件路径")

    args = parser.parse_args()

    # 检查参数
    if args.input and args.output:
        # 单文件模式
        files_to_process = [(Path(args.input), Path(args.output))]
    elif args.gold and args.gold_out:
        files_to_process = [(Path(args.gold), Path(args.gold_out))]
        if args.pred and args.pred_out:
            files_to_process.append((Path(args.pred), Path(args.pred_out)))
    else:
        print("错误：请指定 --input/--output 或 --gold/--gold-out", file=sys.stderr)
        sys.exit(1)

    # 加载 TBox
    tbox_path = Path(args.tbox)
    if not tbox_path.exists():
        print(f"错误：TBox 文件不存在: {tbox_path}", file=sys.stderr)
        sys.exit(1)

    print(f"加载 TBox: {tbox_path}")
    tbox = load_tbox(tbox_path)

    # 构建辅助数据结构
    relation_schema = build_relation_schema(tbox)
    class_hierarchy = build_class_hierarchy(tbox)
    entity_type_hints = build_entity_type_hints(tbox)

    print(f"  关系数: {len(relation_schema)}")
    print(f"  类数: {len(class_hierarchy)}")
    print(f"  实体类型提示数: {len(entity_type_hints)}")

    # 处理文件
    total_stats = {
        "total_records": 0,
        "total_triples": 0,
        "swapped_triples": 0,
        "swap_by_forced_rule": 0,
        "swap_by_tbox_rule": 0,
    }

    for input_path, output_path in files_to_process:
        if not input_path.exists():
            print(f"警告：文件不存在: {input_path}")
            continue

        output_path.parent.mkdir(parents=True, exist_ok=True)

        print(f"\n处理: {input_path}")
        stats = normalize_file(
            input_path, output_path,
            relation_schema, entity_type_hints, class_hierarchy
        )

        print(f"  记录数: {stats['total_records']}")
        print(f"  三元组数: {stats['total_triples']}")
        print(f"  交换方向: {stats['swapped_triples']} ({stats['swapped_triples']/max(1, stats['total_triples'])*100:.1f}%)")
        print(f"    - 强制规则: {stats['swap_by_forced_rule']}")
        print(f"    - TBox规则: {stats['swap_by_tbox_rule']}")
        print(f"  输出: {output_path}")

        for key in total_stats:
            total_stats[key] += stats[key]

    # 总结
    print("\n" + "=" * 50)
    print("归一化完成")
    print("=" * 50)
    print(f"总记录数: {total_stats['total_records']}")
    print(f"总三元组数: {total_stats['total_triples']}")
    print(f"总交换数: {total_stats['swapped_triples']} ({total_stats['swapped_triples']/max(1, total_stats['total_triples'])*100:.1f}%)")
    print(f"  - 强制规则交换: {total_stats['swap_by_forced_rule']}")
    print(f"  - TBox规则交换: {total_stats['swap_by_tbox_rule']}")


if __name__ == "__main__":
    main()
