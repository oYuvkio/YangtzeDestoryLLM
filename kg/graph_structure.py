"""
图结构定义与文本类型检测模块。

用于在 P5 抽取时提供图结构提示，指导 CoT 按路径抽取。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple


@dataclass
class NodeType:
    """图结构节点类型定义"""
    role: str
    entity_types: List[str]
    description: str
    keywords: List[str] = field(default_factory=list)


@dataclass
class PathPattern:
    """图结构路径模式定义"""
    name: str
    pattern: str
    description: str
    extraction_hint: str
    priority: int = 1


@dataclass
class GraphStructure:
    """图结构定义"""
    type_id: str
    name: str
    description: str
    nodes: Dict[str, NodeType]
    paths: List[PathPattern]
    detection_keywords: Dict[str, List[str]] = field(default_factory=dict)

    def get_cot_steps(self) -> List[str]:
        """生成图结构驱动的 CoT 步骤"""
        steps: List[str] = []

        node_lines: List[str] = []
        role_names = {"subject": "S(起始)", "intermediate": "I(中间)", "object": "O(终止)"}
        for role, node in self.nodes.items():
            role_cn = role_names.get(role, role)
            types_str = ", ".join(node.entity_types)
            node_lines.append(f"  - **{role_cn}节点**: {types_str}")
            node_lines.append(f"    {node.description}")
        steps.append(
            "【Step 1: 识别实体并标注角色】\n"
            "按节点角色分类识别文本中的实体：\n"
            f"{chr(10).join(node_lines)}\n"
            "【输出示例】\n"
            "- S1: \"1998年8月\" (Time)\n"
            "- I1: \"长江特大洪水\" (FloodEvent)\n"
            "- O1: \"100万人受灾\" (Impact)\n"
            "【自检】实体是否为原文子串？角色是否正确？"
        )

        path_lines: List[str] = []
        for idx, path in enumerate(self.paths, 1):
            role_pattern = self._annotate_pattern(path.pattern)
            path_lines.append(f"  {idx}. **{path.name}**: `{role_pattern}`")
            path_lines.append(f"     提示: {path.extraction_hint}")
        steps.append(
            "【Step 2: 路径驱动关系连接】\n"
            "按路径模式连接已识别节点（S→I→O）：\n"
            f"{chr(10).join(path_lines)}\n"
            "自检：关系方向是否正确？是否遗漏路径？"
        )

        steps.append(
            "【Step 3: 证据回溯与三元组生成】\n"
            "为每条候选关系寻找原文证据：\n"
            "1) 证据句来自原文\n"
            "2) 主语/宾语至少有一个出现在证据句中\n"
            "找不到证据则丢弃。"
        )

        steps.append(
            "【Step 4: JSON 输出】\n"
            "只输出验证通过的三元组，确保 JSON 结构正确。"
        )

        return steps

    def format_for_prompt(self) -> str:
        """格式化图结构为 Prompt 片段"""
        lines = [
            f"**文本类型**: {self.name}",
            f"**说明**: {self.description}",
            "",
            "**图结构角色示意**:",
            "```",
            "[S:起始] ──关系──→ [I:中间] ──关系──→ [O:终止]",
            "```",
            "",
            "**节点类型**:",
        ]
        role_names = {"subject": "起始(S)", "intermediate": "中间(I)", "object": "终止(O)"}
        for role, node in self.nodes.items():
            lines.append(f"- **{role_names.get(role, role)}**: {', '.join(node.entity_types)}")
            lines.append(f"  {node.description}")
            if node.keywords:
                lines.append(f"  关键词: {', '.join(node.keywords[:5])}")
        lines.append("")
        lines.append("**核心抽取路径**:")
        for idx, path in enumerate(self.paths, 1):
            role_pattern = self._annotate_pattern(path.pattern)
            lines.append(f"{idx}. `{role_pattern}` — {path.description}")
        return "\n".join(lines)

    def _annotate_pattern(self, pattern: str) -> str:
        """为路径模式添加角色标注（S/I/O）。"""
        parts = [p.strip() for p in pattern.split(" → ")]
        if len(parts) != 3:
            return pattern
        start, relation, end = parts
        start_role = self._resolve_role(start)
        end_role = self._resolve_role(end)
        return f"[{start_role}:{start}] → {relation} → [{end_role}:{end}]"

    def _resolve_role(self, entity_label: str) -> str:
        """根据实体类型名称推断角色。"""
        candidates = [seg.strip() for seg in entity_label.split("/") if seg.strip()]
        for seg in candidates:
            for role, node in self.nodes.items():
                if seg in node.entity_types:
                    return {"subject": "S", "intermediate": "I", "object": "O"}.get(role, "?")
        return "?"


GRAPH_STRUCTURES: Dict[str, GraphStructure] = {
    "flood_event": GraphStructure(
        type_id="flood_event",
        name="洪水事件描述",
        description="描述洪水发生过程、水位流量变化、影响和应对措施的文本",
        detection_keywords={
            "strong": ["洪水", "洪峰", "超警戒", "超保证", "泄洪", "分洪", "溃堤", "决口"],
            "weak": ["水位", "流量", "暴雨", "汛期", "防汛", "堤防", "漫堤"],
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "HazardFactor", "WaterBody"],
                description="洪水发生的时间、致灾因子或河流水体",
                keywords=["年", "月", "日", "暴雨", "台风", "长江", "汉江"],
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["FloodEvent", "DisasterEvent", "HydrologicalStation", "Facility"],
                description="洪水事件、监测站点或水利设施",
                keywords=["洪水", "洪峰", "沙市站", "汉口站", "三峡水库"],
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value", "Impact", "EmergencyResponse", "AdministrativeRegion"],
                description="水位流量数值、灾害影响、应急措施或受影响区域",
                keywords=["米", "立方米/秒", "受灾", "转移", "响应", "省", "市"],
            ),
        },
        paths=[
            PathPattern("洪水时间", "Time → occurs_during → FloodEvent",
                       "洪水发生的时间", "如“1998年8月发生特大洪水”", 1),
            PathPattern("洪水原因", "HazardFactor → has_cause → FloodEvent",
                       "导致洪水的原因", "如“持续暴雨导致洪水”", 1),
            PathPattern("洪水地点", "FloodEvent → occurs_at → Location",
                       "洪水发生的地点", "如“长江中下游发生洪水”", 1),
            PathPattern("水位监测", "HydrologicalStation → has_value → Value",
                       "水文站的水位/流量数值", "如“沙市站水位45.22米”", 1),
            PathPattern("站点监测", "HydrologicalStation → monitors → WaterBody",
                       "水文站监测的水体", "如“汉口站监测长江”", 2),
            PathPattern("洪水影响", "FloodEvent → causes_impact → Impact",
                       "洪水造成的影响", "如“洪水造成100万人受灾”", 1),
            PathPattern("影响区域", "FloodEvent → affects_region → AdministrativeRegion",
                       "洪水影响的区域", "如“洪水影响湖北、江西”", 1),
            PathPattern("触发响应", "FloodEvent → triggers_response → EmergencyResponse",
                       "洪水触发的响应", "如“启动防汛Ⅰ级响应”", 1),
            PathPattern("水库调度", "EmergencyResponse → operates → Facility",
                       "对水库的调度操作", "如“三峡水库拦洪削峰”", 2),
            PathPattern("机构执行", "Organization → executes → EmergencyResponse",
                       "机构执行的措施", "如'水利部启动应急响应'", 2),
            PathPattern("因果链", "HazardFactor → causes → FloodEvent",
                       "致灾因子导致洪水", "如'持续暴雨导致洪水'", 1),
            PathPattern("区域受灾", "AdministrativeRegion → isAffectedBy → FloodEvent",
                       "区域受洪水影响", "如'湖北省受洪水影响'", 1),
        ],
    ),
    "drought_event": GraphStructure(
        type_id="drought_event",
        name="干旱事件描述",
        description="描述干旱发生过程、旱情发展、影响和抗旱措施的文本",
        detection_keywords={
            "strong": ["干旱", "旱情", "旱灾", "抗旱", "特旱", "重旱"],
            "weak": ["高温", "少雨", "降水偏少", "蓄水", "调水", "饮水困难", "农田受旱"],
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "HazardFactor"],
                description="干旱发生的时间或致灾因子",
                keywords=["年", "月", "夏季", "高温", "少雨", "降水偏少"],
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["DroughtEvent", "DisasterEvent", "WaterBody", "Facility"],
                description="干旱事件、受影响水体或水利设施",
                keywords=["干旱", "旱情", "洞庭湖", "鄱阳湖", "水库"],
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value", "Impact", "EmergencyResponse", "AdministrativeRegion"],
                description="蓄水量数值、旱灾影响、抗旱措施或受影响区域",
                keywords=["亿立方米", "受旱", "饮水困难", "调水", "省", "县"],
            ),
        },
        paths=[
            PathPattern("干旱时间", "Time → occurs_during → DroughtEvent",
                       "干旱发生的时间", "如“2022年夏季发生特大干旱”", 1),
            PathPattern("干旱原因", "HazardFactor → has_cause → DroughtEvent",
                       "导致干旱的原因", "如“持续高温少雨导致干旱”", 1),
            PathPattern("干旱区域", "DroughtEvent → affects_region → AdministrativeRegion",
                       "干旱影响的区域", "如“干旱影响长江中下游地区”", 1),
            PathPattern("干旱影响", "DroughtEvent → causes_impact → Impact",
                       "干旱造成的影响", "如“干旱导致农田受旱500万亩”", 1),
            PathPattern("水体蓄水", "WaterBody → has_value → Value",
                       "水体的蓄水量", "如“洞庭湖蓄水量偏少”", 1),
            PathPattern("抗旱措施", "Organization → executes → EmergencyResponse",
                       "抗旱措施的执行", "如“水利部实施应急调水”", 1),
            PathPattern("设施调度", "EmergencyResponse → operates → Facility",
                       "对设施的调度", "如'三峡水库加大下泄流量'", 2),
            PathPattern("因果链", "HazardFactor → causes → DroughtEvent",
                       "致灾因子导致干旱", "如'降水偏少导致干旱'", 1),
            PathPattern("区域受灾", "AdministrativeRegion → isAffectedBy → DroughtEvent",
                       "区域受干旱影响", "如'四川省受干旱影响'", 1),
        ],
    ),
    "dispatch_rule": GraphStructure(
        type_id="dispatch_rule",
        name="调度规则描述",
        description="描述水库、闸门等水利工程调度规则和操作条件的文本",
        detection_keywords={
            "strong": ["当", "若", "如果", "则应", "应当", "不得超过", "控制在", "按照"],
            "weak": ["调度", "运用", "开启", "关闭", "泄量", "下泄", "蓄水", "库水位"],
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "Value", "HazardFactor"],
                description="触发条件（时间条件、阈值条件或水情条件）",
                keywords=["当", "若", "汛期", "超过", "达到", "水位", "流量"],
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["Facility", "EmergencyResponse"],
                description="调度对象（水库、闸门）或操作动作",
                keywords=["水库", "闸门", "泄洪", "开启", "关闭", "调节"],
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value", "Facility", "WaterBody", "Location"],
                description="调度目标值、下游设施或保护对象",
                keywords=["不超过", "控制在", "立方米/秒", "下游", "河道"],
            ),
        },
        paths=[
            PathPattern("时间条件", "Time → triggers_response → EmergencyResponse",
                       "时间条件触发操作", "如“汛期应控制库水位不超过145米”", 1),
            PathPattern("阈值触发", "Value → triggers_response → EmergencyResponse",
                       "阈值条件触发操作", "如“水位超过145米时开启泄洪闸”", 1),
            PathPattern("操作设施", "EmergencyResponse → operates → Facility",
                       "操作作用于设施", "如“开启泄洪闸”", 1),
            PathPattern("设施位置", "Facility → located_in → Location",
                       "设施所在位置", "如“三峡水库位于湖北省”", 2),
            PathPattern("运行参数", "Facility → has_value → Value",
                       "设施运行参数", "如“下泄流量不超过35000立方米/秒”", 1),
            PathPattern("保护对象", "EmergencyResponse → affects_region → Location",
                       "调度保护的区域", "如“确保荆江河段安全”", 2),
        ],
    ),
    "impact_statistics": GraphStructure(
        type_id="impact_statistics",
        name="灾情统计描述",
        description="描述灾害损失统计数据、受灾情况汇总的文本",
        detection_keywords={
            "strong": ["截至", "累计", "共计", "统计", "合计", "总计"],
            "weak": ["受灾人口", "经济损失", "死亡", "失踪", "万人", "亿元", "万亩", "倒塌"],
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "AdministrativeRegion", "DisasterEvent", "FloodEvent", "DroughtEvent"],
                description="统计时段、统计区域或灾害事件",
                keywords=["截至", "全年", "汛期", "全省", "全国", "此次"],
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["Impact"],
                description="统计类别（受灾人口、经济损失等）",
                keywords=["受灾人口", "死亡", "农作物受灾", "房屋倒塌", "经济损失"],
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value"],
                description="统计数值",
                keywords=["万人", "人", "亿元", "万亩", "间", "公顷"],
            ),
        },
        paths=[
            PathPattern("区域统计", "AdministrativeRegion → causes_impact → Impact",
                       "区域的灾情统计", "如“湖北省受灾人口...”", 1),
            PathPattern("影响数值", "Impact → has_value → Value",
                       "影响类别的数值", "如“受灾人口100万人”", 1),
            PathPattern("事件损失", "DisasterEvent → causes_impact → Value",
                       "灾害事件的损失", "如“此次洪水造成经济损失50亿元”", 1),
            PathPattern("时段统计", "Time → occurs_during → DisasterEvent",
                       "统计的时间范围", "如“2020年汛期...”", 2),
            PathPattern("区域事件", "DisasterEvent → affects_region → AdministrativeRegion",
                       "灾害影响的区域", "如'洪涝灾害影响10个省份'", 1),
            PathPattern("区域受灾", "AdministrativeRegion → isAffectedBy → DisasterEvent",
                       "区域受灾害影响", "如'10省份受灾'", 1),
        ],
    ),
    "general_disaster": GraphStructure(
        type_id="general_disaster",
        name="通用灾害描述",
        description="综合性灾害描述文本，或无法明确分类的灾害相关文本",
        detection_keywords={
            "strong": [],
            "weak": ["灾害", "灾情", "防灾", "减灾", "救灾", "应急"],
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "Location", "AdministrativeRegion", "HazardFactor", "WaterBody"],
                description="时间、地点或原因",
                keywords=["年", "月", "省", "市", "流域", "暴雨", "台风"],
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=[
                    "DisasterEvent",
                    "FloodEvent",
                    "DroughtEvent",
                    "Facility",
                    "HydrologicalStation",
                    "Organization",
                ],
                description="灾害事件、设施或机构",
                keywords=["灾害", "洪水", "干旱", "水库", "水文站", "水利部"],
            ),
            "object": NodeType(
                role="object",
                entity_types=["Impact", "Value", "EmergencyResponse", "AdministrativeRegion"],
                description="影响、数值、措施或区域",
                keywords=["受灾", "损失", "米", "响应", "转移", "省"],
            ),
        },
        paths=[
            PathPattern("时间关联", "Time → occurs_during → DisasterEvent",
                       "事件发生时间", "寻找时间与事件的关联", 1),
            PathPattern("地点关联", "DisasterEvent → occurs_at → Location",
                       "事件发生地点", "寻找地点与事件的关联", 1),
            PathPattern("原因关联", "HazardFactor → has_cause → DisasterEvent",
                       "事件的原因", "寻找因果关系", 1),
            PathPattern("因果关联", "HazardFactor → causes → DisasterEvent",
                       "因果链关系", "寻找因果关系", 1),
            PathPattern("影响关联", "DisasterEvent → causes_impact → Impact",
                       "事件的影响", "寻找影响描述", 1),
            PathPattern("数值关联", "HydrologicalStation → has_value → Value",
                       "监测数值", "寻找数值表达", 1),
            PathPattern("响应关联", "DisasterEvent → triggers_response → EmergencyResponse",
                       "触发的响应", "寻找响应措施", 1),
            PathPattern("执行关联", "Organization → executes → EmergencyResponse",
                       "机构执行措施", "寻找执行主体", 2),
            PathPattern("区域关联", "DisasterEvent → affects_region → AdministrativeRegion",
                       "影响区域", "寻找区域范围", 1),
            PathPattern("受影响", "Location → isAffectedBy → DisasterEvent",
                       "区域受影响", "寻找受影响关系", 1),
            PathPattern("设施关联", "EmergencyResponse → operates → Facility",
                       "设施操作", "寻找设施操作", 2),
            PathPattern("位置关联", "Facility → located_in → Location",
                       "设施位置", "寻找位置关系", 2),
        ],
    ),
}


class TextTypeDetector:
    """文本类型检测器"""

    def __init__(self, confidence_threshold: float = 0.3, default_type: str = "general_disaster"):
        self.confidence_threshold = confidence_threshold
        self.default_type = default_type

    def detect(self, text: str) -> Tuple[str, float, Dict]:
        scores: Dict[str, float] = {}
        details: Dict[str, Dict] = {}

        for type_id, graph in GRAPH_STRUCTURES.items():
            if type_id == self.default_type:
                continue

            keywords = graph.detection_keywords
            strong_kws = keywords.get("strong", [])
            weak_kws = keywords.get("weak", [])

            strong_hits = [kw for kw in strong_kws if kw in text]
            weak_hits = [kw for kw in weak_kws if kw in text]
            score = len(strong_hits) * 2 + len(weak_hits)
            max_score = len(strong_kws) * 2 + len(weak_kws)
            normalized = score / max_score if max_score else 0.0

            scores[type_id] = normalized
            details[type_id] = {
                "strong_matches": strong_hits,
                "weak_matches": weak_hits,
                "raw_score": score,
                "normalized_score": round(normalized, 3),
            }

        if scores:
            best_type = max(scores, key=scores.get)
            best_score = scores[best_type]
            if best_score >= self.confidence_threshold:
                return best_type, best_score, details

        return self.default_type, 0.0, details

    def detect_with_fallback(self, text: str) -> str:
        type_id, _, _ = self.detect(text)
        return type_id


def detect_text_type(text: str) -> str:
    detector = TextTypeDetector()
    return detector.detect_with_fallback(text)


def get_graph_structure(type_id: str) -> GraphStructure:
    return GRAPH_STRUCTURES.get(type_id, GRAPH_STRUCTURES["general_disaster"])


def get_graph_structure_for_text(text: str) -> Tuple[GraphStructure, str, float]:
    detector = TextTypeDetector()
    type_id, confidence, _ = detector.detect(text)
    return get_graph_structure(type_id), type_id, confidence


def get_supported_types() -> List[str]:
    return list(GRAPH_STRUCTURES.keys())
