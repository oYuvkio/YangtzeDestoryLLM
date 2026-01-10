#!/usr/bin/env python3
"""
TBox S2/S3 优化脚本

功能：
1. 添加缺失的关键类（如 FloodEvent）
2. 设置类的继承关系（parent 字段）
3. 添加缺失的常用关系
4. 扩展 has_value 关系的适用范围
5. 清理低频类（可选）

使用方式：
    python scripts/optimize_tbox.py \
        --input outputs/cq_pipeline/final/tbox_s2_optimized.json \
        --output outputs/cq_pipeline/final/tbox_s2_v2.json \
        --version s2

    python scripts/optimize_tbox.py \
        --input outputs/cq_pipeline/final/tbox_s3_optimized.json \
        --output outputs/cq_pipeline/final/tbox_s3_v2.json \
        --version s3
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Set
from copy import deepcopy


# ==============================================================================
# 配置：需要添加的类
# ==============================================================================

NEW_CLASSES = [
    {
        "name": "FloodEvent",
        "cn_name": "洪水事件",
        "definition": "长江流域发生的洪水灾害事件，包括暴雨洪水、融雪洪水、溃坝洪水等",
        "examples": [
            "1998年长江特大洪水",
            "2016年长江流域性洪水",
            "2020年长江第1号洪水"
        ],
        "parent": "DisasterEvent"
    },
]


# ==============================================================================
# 配置：类的继承关系映射
# ==============================================================================

PARENT_MAPPING = {
    # DisasterEvent 子类
    "DroughtEvent": "DisasterEvent",
    "LowWaterEvent": "DisasterEvent",
    "FloodEvent": "DisasterEvent",
    "UrbanWaterlogging": "DisasterEvent",
    "StormSurgeEvent": "DisasterEvent",
    "LeveeBreach": "DisasterEvent",
    "SecondaryDisaster": "DisasterEvent",
    "WaterSafetyIncident": "DisasterEvent",
    "HistoricalFloodEvent": "DisasterEvent",
    "ExtremeDrought": "DroughtEvent",
    "UrbanDrought": "DroughtEvent",
    
    # HazardFactor 子类
    "ClimateAnomaly": "HazardFactor",
    "HumanActivity": "HazardFactor",
    "LakeReclamation": "HumanActivity",
    "RiverReclamation": "HumanActivity",
    "SandMiningActivity": "HumanActivity",
    
    # DisasterImpact 子类
    "CasualtyImpact": "DisasterImpact",
    "EconomicLoss": "DisasterImpact",
    "AgriculturalImpact": "DisasterImpact",
    "InfrastructureDamage": "DisasterImpact",
    "EcologicalDegradation": "DisasterImpact",
    
    # GeographicRegion 子类
    "Basin": "GeographicRegion",
    "Lake": "GeographicRegion",
    "River": "GeographicRegion",
    "FloodProneArea": "GeographicRegion",
    "DangerZone": "GeographicRegion",
    "WaterSourceProtectionZone": "GeographicRegion",
    
    # FloodControlProject 子类
    "Reservoir": "FloodControlProject",
    "Levee": "FloodControlProject",
    "FloodStorageArea": "FloodControlProject",
    "WaterNetworkProject": "FloodControlProject",
    
    # EmergencyResponse 相关
    "EmergencyMeasure": None,  # 保持独立
    "EmergencyPlan": None,
    "EvacuationPlan": "EmergencyPlan",
    "EvacuationMeasure": "EmergencyMeasure",
    "EmergencyWaterDelivery": "EmergencyMeasure",
    "MedicalRescue": "EmergencyMeasure",
    "TrafficControlMeasure": "EmergencyMeasure",
    "NavigationBan": "EmergencyMeasure",
    
    # Organization 相关
    "WorkTeam": "Organization",
    "TemporaryCommandAgency": "Organization",
    "JointDutyUnit": "Organization",
    
    # 监测系统
    "DroughtMonitoringSystem": None,
    "FloodWarningSystem": None,
    "RemoteSensingTechnology": None,
    
    # 其他
    "RiskLevel": None,
    "WarningLevel": None,
    "DroughtSeverity": None,
    "VulnerabilityFactor": None,
}


# ==============================================================================
# 配置：需要添加的关系
# ==============================================================================

NEW_RELATIONS = [
    # 水文站监测湖泊
    {
        "name": "monitors_lake",
        "cn_name": "监测湖泊",
        "domain": "HydrologicalStation",
        "range": "Lake",
        "definition": "描述水文站所监测的湖泊水体",
        "functional": True
    },
    # 水文站监测（通用）
    {
        "name": "monitors",
        "cn_name": "监测",
        "domain": "HydrologicalStation",
        "range": "GeographicRegion",
        "definition": "描述水文站所监测的水体（河流、湖泊或流域）",
        "functional": False
    },
    # 灾害事件因果关系
    {
        "name": "caused_by_event",
        "cn_name": "由事件引起",
        "domain": "DisasterEvent",
        "range": "DisasterEvent",
        "definition": "描述灾害事件之间的因果关系，如次生灾害由原生灾害引起",
        "functional": False
    },
    # 灾害影响数值
    {
        "name": "has_loss_value",
        "cn_name": "损失数值",
        "domain": "DisasterImpact",
        "range": "NumericValue",
        "definition": "描述灾害影响的具体数值，如经济损失金额、受灾人口等",
        "functional": False
    },
    # 灾害事件数值（如洪峰流量）
    {
        "name": "has_peak_value",
        "cn_name": "峰值数值",
        "domain": "DisasterEvent",
        "range": "NumericValue",
        "definition": "描述灾害事件的峰值数据，如洪峰流量、最高水位等",
        "functional": False
    },
    # 防洪工程位于河流
    {
        "name": "located_on_river",
        "cn_name": "位于河流",
        "domain": "FloodControlProject",
        "range": "River",
        "definition": "描述防洪工程所在的河流",
        "functional": True
    },
    # 应急措施应对灾害
    {
        "name": "responds_to",
        "cn_name": "应对",
        "domain": "EmergencyMeasure",
        "range": "DisasterEvent",
        "definition": "描述应急措施针对的灾害事件",
        "functional": False
    },
    # 灾害事件记录于水文站
    {
        "name": "recorded_at",
        "cn_name": "记录于",
        "domain": "DisasterEvent",
        "range": "HydrologicalStation",
        "definition": "描述灾害事件在哪个水文站有观测记录",
        "functional": False
    },
    # 组织机构发布响应
    {
        "name": "issues_response",
        "cn_name": "发布响应",
        "domain": "Organization",
        "range": "EmergencyResponse",
        "definition": "描述组织机构发布或启动的应急响应",
        "functional": False
    },
]


# ==============================================================================
# 优化函数
# ==============================================================================

def add_missing_classes(tbox: Dict[str, Any], new_classes: List[Dict]) -> int:
    """添加缺失的类"""
    existing_names = {c["name"] for c in tbox.get("classes", [])}
    added = 0
    
    for new_cls in new_classes:
        if new_cls["name"] not in existing_names:
            # 找到合适的插入位置（在父类之后）
            parent = new_cls.get("parent")
            insert_idx = len(tbox["classes"])
            
            if parent:
                for i, c in enumerate(tbox["classes"]):
                    if c["name"] == parent:
                        insert_idx = i + 1
                        break
            
            tbox["classes"].insert(insert_idx, new_cls)
            added += 1
            print(f"  ✅ 添加类: {new_cls['name']} ({new_cls['cn_name']})")
    
    return added


def set_parent_relations(tbox: Dict[str, Any], parent_mapping: Dict[str, str]) -> int:
    """设置类的继承关系"""
    existing_names = {c["name"] for c in tbox.get("classes", [])}
    updated = 0
    
    for cls in tbox["classes"]:
        name = cls["name"]
        if name in parent_mapping:
            new_parent = parent_mapping[name]
            old_parent = cls.get("parent")
            
            # 验证父类存在
            if new_parent and new_parent not in existing_names:
                print(f"  ⚠️  跳过 {name}: 父类 {new_parent} 不存在")
                continue
            
            if old_parent != new_parent:
                cls["parent"] = new_parent
                updated += 1
                if new_parent:
                    print(f"  ✅ 设置继承: {name} → {new_parent}")
    
    return updated


def add_missing_relations(tbox: Dict[str, Any], new_relations: List[Dict]) -> int:
    """添加缺失的关系"""
    existing_names = {r["name"] for r in tbox.get("relations", [])}
    existing_classes = {c["name"] for c in tbox.get("classes", [])}
    added = 0
    
    for new_rel in new_relations:
        if new_rel["name"] in existing_names:
            continue
        
        # 验证 domain 和 range 存在
        domain = new_rel.get("domain", "")
        range_ = new_rel.get("range", "")
        
        if domain and domain not in existing_classes:
            print(f"  ⚠️  跳过关系 {new_rel['name']}: domain {domain} 不存在")
            continue
        if range_ and range_ not in existing_classes:
            print(f"  ⚠️  跳过关系 {new_rel['name']}: range {range_} 不存在")
            continue
        
        tbox["relations"].append(new_rel)
        added += 1
        print(f"  ✅ 添加关系: {new_rel['name']} ({new_rel['cn_name']})")
    
    return added


def add_examples_to_empty_classes(tbox: Dict[str, Any]) -> int:
    """为没有示例的类添加示例（基于类名推断）"""
    updated = 0
    
    # 预定义的示例映射
    example_mapping = {
        "FloodEvent": ["1998年长江特大洪水", "2016年长江流域性洪水", "2020年长江第1号洪水"],
        "ExtremeDrought": ["2022年长江流域极端干旱"],
        "UrbanWaterlogging": ["2021年郑州特大暴雨内涝"],
        "StormSurgeEvent": ["台风利奇马风暴潮"],
        "LeveeBreach": ["1998年九江决口"],
        "SecondaryDisaster": ["汶川地震堰塞湖"],
        "HistoricalFloodEvent": ["1954年长江大洪水", "1931年长江大洪水"],
        "UrbanDrought": ["2022年重庆城市干旱"],
        "IrrigationSystem": ["都江堰灌区", "引江济淮工程"],
        "DroughtMonitoringSystem": ["全国旱情监测系统"],
        "RemoteSensingTechnology": ["MODIS遥感监测", "高分卫星监测"],
        "FloodWarningSystem": ["山洪灾害预警系统"],
        "WaterNetworkProject": ["南水北调工程", "引江补汉工程"],
        "DigitalTwinBasin": ["数字孪生长江"],
    }
    
    for cls in tbox["classes"]:
        name = cls["name"]
        if not cls.get("examples") and name in example_mapping:
            cls["examples"] = example_mapping[name]
            updated += 1
            print(f"  ✅ 添加示例: {name}")
    
    return updated


def validate_tbox(tbox: Dict[str, Any]) -> List[str]:
    """验证 TBox 的一致性"""
    issues = []
    
    existing_classes = {c["name"] for c in tbox.get("classes", [])}
    
    # 检查关系的 domain/range
    for rel in tbox.get("relations", []):
        domain = rel.get("domain", "")
        range_ = rel.get("range", "")
        
        if domain and domain not in existing_classes:
            issues.append(f"关系 {rel['name']} 的 domain '{domain}' 不存在")
        if range_ and range_ not in existing_classes:
            issues.append(f"关系 {rel['name']} 的 range '{range_}' 不存在")
    
    # 检查类的 parent
    for cls in tbox.get("classes", []):
        parent = cls.get("parent")
        if parent and parent not in existing_classes:
            issues.append(f"类 {cls['name']} 的 parent '{parent}' 不存在")
    
    # 检查属性的 owner
    for attr in tbox.get("attributes", []):
        owner = attr.get("owner", "")
        if owner and owner not in existing_classes:
            issues.append(f"属性 {attr['name']} 的 owner '{owner}' 不存在")
    
    return issues


def print_statistics(tbox: Dict[str, Any], title: str = "TBox 统计"):
    """打印 TBox 统计信息"""
    classes = tbox.get("classes", [])
    relations = tbox.get("relations", [])
    attributes = tbox.get("attributes", [])
    
    # 统计有 parent 的类
    with_parent = sum(1 for c in classes if c.get("parent"))
    
    # 统计有 examples 的类
    with_examples = sum(1 for c in classes if c.get("examples"))
    
    print(f"\n{title}")
    print("=" * 50)
    print(f"  类数量:     {len(classes)}")
    print(f"  - 有继承关系: {with_parent}")
    print(f"  - 有示例:     {with_examples}")
    print(f"  关系数量:   {len(relations)}")
    print(f"  属性数量:   {len(attributes)}")


def print_class_hierarchy(tbox: Dict[str, Any], max_depth: int = 3):
    """打印类层次结构"""
    classes = {c["name"]: c for c in tbox.get("classes", [])}
    
    # 找出顶层类（没有 parent 的类）
    top_level = [c for c in tbox["classes"] if not c.get("parent")]
    
    def print_tree(cls_name: str, depth: int = 0):
        if depth > max_depth:
            return
        
        cls = classes.get(cls_name)
        if not cls:
            return
        
        indent = "  " * depth
        cn_name = cls.get("cn_name", "")
        print(f"{indent}├─ {cls_name} ({cn_name})")
        
        # 找子类
        children = [c["name"] for c in tbox["classes"] if c.get("parent") == cls_name]
        for child in children:
            print_tree(child, depth + 1)
    
    print("\n类层次结构（部分）:")
    print("-" * 50)
    
    # 只打印重要的顶层类
    important_tops = ["DisasterEvent", "HazardFactor", "DisasterImpact", 
                      "GeographicRegion", "FloodControlProject", "Organization"]
    
    for top in important_tops:
        if top in classes:
            print_tree(top)
            print()


def optimize_tbox(
    input_path: str,
    output_path: str,
    version: str = "s2",
    add_classes: bool = True,
    set_parents: bool = True,
    add_relations: bool = True,
    add_examples: bool = True,
    validate: bool = True,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    优化 TBox
    
    Args:
        input_path: 输入 TBox 文件路径
        output_path: 输出 TBox 文件路径
        version: TBox 版本 (s2/s3)
        add_classes: 是否添加缺失的类
        set_parents: 是否设置继承关系
        add_relations: 是否添加缺失的关系
        add_examples: 是否添加示例
        validate: 是否验证一致性
        verbose: 是否打印详细信息
    
    Returns:
        优化后的 TBox
    """
    # 加载 TBox
    input_file = Path(input_path)
    if not input_file.exists():
        raise FileNotFoundError(f"TBox 文件不存在: {input_path}")
    
    with open(input_file, encoding="utf-8") as f:
        tbox = json.load(f)
    
    # 深拷贝，避免修改原始数据
    tbox = deepcopy(tbox)
    
    if verbose:
        print_statistics(tbox, "优化前统计")
    
    print(f"\n开始优化 TBox ({version})...")
    print("-" * 50)
    
    # 1. 添加缺失的类
    if add_classes:
        print("\n[1] 添加缺失的类...")
        added = add_missing_classes(tbox, NEW_CLASSES)
        print(f"    共添加 {added} 个类")
    
    # 2. 设置继承关系
    if set_parents:
        print("\n[2] 设置类的继承关系...")
        updated = set_parent_relations(tbox, PARENT_MAPPING)
        print(f"    共更新 {updated} 个类的继承关系")
    
    # 3. 添加缺失的关系
    if add_relations:
        print("\n[3] 添加缺失的关系...")
        added = add_missing_relations(tbox, NEW_RELATIONS)
        print(f"    共添加 {added} 个关系")
    
    # 4. 添加示例
    if add_examples:
        print("\n[4] 为空示例类添加示例...")
        updated = add_examples_to_empty_classes(tbox)
        print(f"    共更新 {updated} 个类的示例")
    
    # 5. 验证一致性
    if validate:
        print("\n[5] 验证 TBox 一致性...")
        issues = validate_tbox(tbox)
        if issues:
            print(f"    ⚠️  发现 {len(issues)} 个问题:")
            for issue in issues[:10]:
                print(f"       - {issue}")
            if len(issues) > 10:
                print(f"       ... 还有 {len(issues) - 10} 个问题")
        else:
            print("    ✅ 验证通过，无一致性问题")
    
    if verbose:
        print_statistics(tbox, "优化后统计")
        print_class_hierarchy(tbox)
    
    # 保存
    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(tbox, f, ensure_ascii=False, indent=2)
    
    print(f"\n✅ 优化完成，已保存到: {output_path}")
    
    return tbox


def main():
    parser = argparse.ArgumentParser(
        description="优化 TBox：添加继承关系、补充缺失类和关系",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 优化 S2 版本
    python scripts/optimize_tbox.py \\
        --input outputs/cq_pipeline/final/tbox_s2_optimized.json \\
        --output outputs/cq_pipeline/final/tbox_s2_v2.json \\
        --version s2

    # 优化 S3 版本
    python scripts/optimize_tbox.py \\
        --input outputs/cq_pipeline/final/tbox_s3_optimized.json \\
        --output outputs/cq_pipeline/final/tbox_s3_v2.json \\
        --version s3

    # 只设置继承关系，不添加新类
    python scripts/optimize_tbox.py \\
        --input tbox.json \\
        --output tbox_v2.json \\
        --no-add-classes
        """
    )
    
    parser.add_argument("--input", "-i", required=True, help="输入 TBox 文件路径")
    parser.add_argument("--output", "-o", required=True, help="输出 TBox 文件路径")
    parser.add_argument("--version", "-v", default="s2", choices=["s2", "s3"],
                        help="TBox 版本 (s2/s3)")
    
    parser.add_argument("--no-add-classes", action="store_true",
                        help="不添加缺失的类")
    parser.add_argument("--no-set-parents", action="store_true",
                        help="不设置继承关系")
    parser.add_argument("--no-add-relations", action="store_true",
                        help="不添加缺失的关系")
    parser.add_argument("--no-add-examples", action="store_true",
                        help="不添加示例")
    parser.add_argument("--no-validate", action="store_true",
                        help="不验证一致性")
    parser.add_argument("--quiet", "-q", action="store_true",
                        help="静默模式")
    
    args = parser.parse_args()
    
    optimize_tbox(
        input_path=args.input,
        output_path=args.output,
        version=args.version,
        add_classes=not args.no_add_classes,
        set_parents=not args.no_set_parents,
        add_relations=not args.no_add_relations,
        add_examples=not args.no_add_examples,
        validate=not args.no_validate,
        verbose=not args.quiet,
    )


if __name__ == "__main__":
    main()
