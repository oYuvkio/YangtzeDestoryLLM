# 精简版融合指导文档

## 一、方案架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                         整体架构                                 │
├─────────────────────────────────────────────────────────────────┤
│  【概念层】专家骨架(14类/11关系) + 聚类扩展 → 支持度/置信度筛选  │
│                              ↓                                   │
│  【抽取层】文本类型检测(5种) → 图结构CoT → 双重校验 → 归一化     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、专家骨架定义（合并版）


## 三、图结构类型（5种）

### 3.1 类型检测关键词

```python
TEXT_TYPE_KEYWORDS = {
    "flood_event": {
        "strong": ["洪水", "洪峰", "超警戒", "泄洪", "溃堤"],
        "weak": ["水位", "流量", "暴雨", "汛期"]
    },
    "drought_event": {
        "strong": ["干旱", "旱情", "旱灾", "抗旱"],
        "weak": ["高温", "少雨", "蓄水", "调水"]
    },
    "dispatch_rule": {
        "strong": ["当", "若", "则应", "不得超过", "控制在"],
        "weak": ["调度", "开启", "关闭", "泄量"]
    },
    "impact_statistics": {
        "strong": ["截至", "累计", "共计", "统计"],
        "weak": ["受灾人口", "经济损失", "万人", "亿元"]
    },
    "general_disaster": {}  # 兜底
}
```

### 3.2 各类型核心路径

| 类型              | 核心路径                                                                   |
| ----------------- | -------------------------------------------------------------------------- |
| flood_event       | Time→FloodEvent, HazardFactor→FloodEvent, Station→Value, FloodEvent→Impact |
| drought_event     | Time→DroughtEvent, HazardFactor→DroughtEvent, DroughtEvent→Impact          |
| dispatch_rule     | Value→EmergencyResponse, EmergencyResponse→Facility                        |
| impact_statistics | Region→Impact, Impact→Value, DisasterEvent→Value                           |
| general_disaster  | 全路径集合（兜底）                                                         |

---

## 四、核心代码模块

### 4.1 专家骨架 (`kg/ontology/expert_skeleton.py`)

```python
EXPERT_SKELETON = {
    "classes": [
        {"name": "DisasterEvent", "cn_name": "灾害事件", "parent": None, "is_anchor": True},
        {"name": "FloodEvent", "cn_name": "洪水事件", "parent": "DisasterEvent", "is_anchor": True},
        {"name": "DroughtEvent", "cn_name": "干旱事件", "parent": "DisasterEvent", "is_anchor": True},
        {"name": "HazardFactor", "cn_name": "致灾因子", "parent": None, "is_anchor": True},
        {"name": "Location", "cn_name": "地理位置", "parent": None, "is_anchor": True},
        {"name": "AdministrativeRegion", "cn_name": "行政区划", "parent": "Location", "is_anchor": True},
        {"name": "WaterBody", "cn_name": "水体", "parent": "Location", "is_anchor": True},
        {"name": "Impact", "cn_name": "灾害影响", "parent": None, "is_anchor": True},
        {"name": "EmergencyResponse", "cn_name": "应急响应", "parent": None, "is_anchor": True},
        {"name": "Organization", "cn_name": "机构", "parent": None, "is_anchor": True},
        {"name": "HydrologicalStation", "cn_name": "水文站", "parent": None, "is_anchor": True},
        {"name": "Time", "cn_name": "时间", "parent": None, "is_anchor": True},
        {"name": "Value", "cn_name": "数值指标", "parent": None, "is_anchor": True},
        {"name": "Facility", "cn_name": "水利设施", "parent": None, "is_anchor": True},
    ],
    "relations": [
        {"name": "has_cause", "cn_name": "致灾因子", "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"], "range": ["HazardFactor"]},
        {"name": "affects_region", "cn_name": "影响区域", "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"], "range": ["Location", "AdministrativeRegion", "WaterBody"]},
        {"name": "causes_impact", "cn_name": "造成影响", "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"], "range": ["Impact", "Value"]},
        {"name": "triggers_response", "cn_name": "触发响应", "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"], "range": ["EmergencyResponse"]},
        {"name": "located_in", "cn_name": "位于", "domain": ["WaterBody", "HydrologicalStation", "Facility"], "range": ["AdministrativeRegion", "Location"]},
        {"name": "monitors", "cn_name": "监测", "domain": ["HydrologicalStation"], "range": ["WaterBody"]},
        {"name": "executes", "cn_name": "执行", "domain": ["Organization"], "range": ["EmergencyResponse"]},
        {"name": "occurs_at", "cn_name": "发生于(地点)", "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"], "range": ["Location", "AdministrativeRegion", "WaterBody"]},
        {"name": "occurs_during", "cn_name": "发生于(时间)", "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"], "range": ["Time"]},
        {"name": "has_value", "cn_name": "测量值为", "domain": ["HydrologicalStation", "WaterBody", "Facility"], "range": ["Value"]},
        {"name": "operates", "cn_name": "操作", "domain": ["Organization", "EmergencyResponse"], "range": ["Facility"]},
    ]
}

class ExpertSkeleton:
    def __init__(self):
        self.class_map = {c["name"]: c for c in EXPERT_SKELETON["classes"]}
        self.relation_map = {r["name"]: r for r in EXPERT_SKELETON["relations"]}
  
    def to_tbox_format(self):
        return EXPERT_SKELETON
```

### 4.2 图结构定义 (`kg/extraction/graph_structure.py`)

```python
from dataclasses import dataclass, field
from typing import List, Dict, Tuple

@dataclass
class PathPattern:
    name: str
    pattern: str
    extraction_hint: str

@dataclass
class GraphStructure:
    type_id: str
    name: str
    paths: List[PathPattern]
    detection_keywords: Dict[str, List[str]]

GRAPH_STRUCTURES = {
    "flood_event": GraphStructure(
        type_id="flood_event",
        name="洪水事件",
        detection_keywords={"strong": ["洪水", "洪峰", "超警戒"], "weak": ["水位", "流量"]},
        paths=[
            PathPattern("洪水时间", "Time → occurs_during → FloodEvent", "如'1998年8月发生洪水'"),
            PathPattern("洪水原因", "HazardFactor → has_cause → FloodEvent", "如'暴雨导致洪水'"),
            PathPattern("水位监测", "HydrologicalStation → has_value → Value", "如'沙市站水位45米'"),
            PathPattern("洪水影响", "FloodEvent → causes_impact → Impact", "如'造成100万人受灾'"),
            PathPattern("影响区域", "FloodEvent → affects_region → AdministrativeRegion", "如'影响湖北省'"),
        ]
    ),
    "drought_event": GraphStructure(
        type_id="drought_event",
        name="干旱事件",
        detection_keywords={"strong": ["干旱", "旱情"], "weak": ["高温", "少雨"]},
        paths=[
            PathPattern("干旱时间", "Time → occurs_during → DroughtEvent", "如'2022年夏季干旱'"),
            PathPattern("干旱原因", "HazardFactor → has_cause → DroughtEvent", "如'高温少雨导致'"),
            PathPattern("干旱影响", "DroughtEvent → causes_impact → Impact", "如'农田受旱500万亩'"),
        ]
    ),
    "dispatch_rule": GraphStructure(
        type_id="dispatch_rule",
        name="调度规则",
        detection_keywords={"strong": ["当", "若", "控制在"], "weak": ["调度", "开启"]},
        paths=[
            PathPattern("条件触发", "Value → triggers_response → EmergencyResponse", "如'水位超145米时开闸'"),
            PathPattern("操作设施", "EmergencyResponse → operates → Facility", "如'开启泄洪闸'"),
        ]
    ),
    "impact_statistics": GraphStructure(
        type_id="impact_statistics",
        name="灾情统计",
        detection_keywords={"strong": ["截至", "累计"], "weak": ["受灾人口", "经济损失"]},
        paths=[
            PathPattern("区域统计", "AdministrativeRegion → causes_impact → Impact", "如'湖北省受灾...'"),
            PathPattern("影响数值", "Impact → has_value → Value", "如'受灾人口100万'"),
        ]
    ),
    "general_disaster": GraphStructure(
        type_id="general_disaster",
        name="通用灾害",
        detection_keywords={"strong": [], "weak": []},
        paths=[]  # 使用全部路径
    )
}

def detect_text_type(text: str) -> str:
    """自动检测文本类型"""
    scores = {}
    for type_id, graph in GRAPH_STRUCTURES.items():
        if type_id == "general_disaster":
            continue
        kws = graph.detection_keywords
        score = sum(2 for kw in kws.get("strong", []) if kw in text)
        score += sum(1 for kw in kws.get("weak", []) if kw in text)
        scores[type_id] = score
  
    if scores:
        best = max(scores, key=scores.get)
        if scores[best] >= 2:
            return best
    return "general_disaster"

def get_graph_structure(type_id: str) -> GraphStructure:
    return GRAPH_STRUCTURES.get(type_id, GRAPH_STRUCTURES["general_disaster"])
```

### 4.3 CoT Prompt构建 (`kg/extraction/graph_cot_prompt.py`)

```python
class GraphCoTPromptBuilder:
    def build_prompt(self, text: str, tbox: dict, text_type: str = None) -> str:
        if text_type is None:
            text_type = detect_text_type(text)
        graph = get_graph_structure(text_type)
      
        return f"""【角色】水旱灾害知识图谱抽取助手

【图结构】{graph.name}
核心路径：
{self._format_paths(graph.paths)}

【TBox约束】
实体类型：{', '.join(c['name'] for c in tbox['classes'])}
关系类型：{', '.join(r['name'] for r in tbox['relations'])}

【CoT步骤】
Step 1: 按图结构识别实体节点
Step 2: 按路径模式连接关系
Step 3: 证据回溯验证（找不到证据则丢弃）

【输出格式】
```json
{{"triples": [{{"subject": "...", "predicate": "...", "object": "...", "evidence": "..."}}]}}
```

【待抽取文本】
{text}"""

    def _format_paths(self, paths):
        return '\n'.join(f"- {p.name}: {p.pattern}" for p in paths[:6])
```

### 4.4 双重校验 (`kg/extraction/dual_verification.py`)

```python
import re

class DualVerifier:
    def verify(self, triples: list, text: str, tbox: dict) -> tuple:
        verified, rejected = [], []
        relation_names = {r["name"] for r in tbox.get("relations", [])}
      
        for t in triples:
            # 校验1: 原文回溯
            if not self._entity_in_text(t.get("subject", ""), text):
                rejected.append({**t, "reason": "主语不在原文"})
                continue
            if not self._entity_in_text(t.get("object", ""), text):
                rejected.append({**t, "reason": "宾语不在原文"})
                continue
          
            # 校验2: Schema一致性（宽松模式）
            if t.get("predicate") not in relation_names:
                t["_warning"] = "关系不在TBox中"
          
            verified.append(t)
      
        return verified, {"verified": len(verified), "rejected": len(rejected)}
  
    def _entity_in_text(self, entity: str, text: str) -> bool:
        if not entity:
            return False
        if entity in text:
            return True
        # 归一化匹配
        entity_norm = re.sub(r'[，。、\s]', '', entity)
        text_norm = re.sub(r'[，。、\s]', '', text)
        return entity_norm in text_norm
```

### 4.5 抽取执行器 (`kg/extraction/graph_cot_extractor.py`)

```python
import json
import re

class GraphCoTExtractor:
    def __init__(self, llm_client, config=None):
        self.llm = llm_client
        self.prompt_builder = GraphCoTPromptBuilder()
        self.verifier = DualVerifier()
  
    def extract(self, text: str, tbox: dict) -> dict:
        text_type = detect_text_type(text)
        prompt = self.prompt_builder.build_prompt(text, tbox, text_type)
      
        response = self.llm.generate(prompt, temperature=0.1)
        raw_triples = self._parse_response(response)
        verified, report = self.verifier.verify(raw_triples, text, tbox)
      
        return {
            "text_type": text_type,
            "raw_triples": raw_triples,
            "verified_triples": verified,
            "verification_report": report
        }
  
    def _parse_response(self, response: str) -> list:
        try:
            match = re.search(r'\{[\s\S]*\}', response)
            if match:
                result = json.loads(match.group())
                return result.get("triples", [])
        except:
            pass
        return []
```

---

## 五、配置文件

### 5.1 本体构建配置 (`configs/ontology_building.yaml`)

```yaml
clustering:
  min_freq: 3
  n_clusters_entity: 15
  dice_threshold: 0.5

fusion:
  similarity_threshold: 0.75

quality_filter:
  min_support: 5
  min_confidence: 0.3
  protect_anchors: true
```

### 5.2 抽取配置 (`configs/extraction.yaml`)

```yaml
extraction:
  temperature: 0.1
  auto_detect_type: true

verification:
  strict_mode: false
```

---

## 六、消融实验配置

```python
ABLATION_CONFIGS = {
    "full": {"use_graph": True, "use_cot": True, "use_verify": True},
    "wo_graph": {"use_graph": False, "use_cot": True, "use_verify": True},
    "wo_cot": {"use_graph": True, "use_cot": False, "use_verify": True},
    "wo_verify": {"use_graph": True, "use_cot": True, "use_verify": False},
    "baseline": {"use_graph": False, "use_cot": True, "use_verify": True},
}
```

---

## 七、文件结构

```
project/
├── configs/
│   ├── ontology_building.yaml
│   └── extraction.yaml
├── kg/
│   ├── ontology/
│   │   ├── expert_skeleton.py      # 专家骨架(14类/11关系)
│   │   ├── corpus_clustering.py    # 聚类挖掘
│   │   ├── hybrid_fusion.py        # 混合融合
│   │   └── quality_filter.py       # 支持度/置信度筛选
│   ├── extraction/
│   │   ├── graph_structure.py      # 5种图结构+检测
│   │   ├── graph_cot_prompt.py     # CoT Prompt
│   │   ├── dual_verification.py    # 双重校验
│   │   └── graph_cot_extractor.py  # 抽取执行器
│   └── llm_client.py
├── scripts/
│   ├── build_hybrid_ontology.py
│   ├── run_extraction.py
│   └── run_ablation.py
└── outputs/
```

---

## 八、关键注意事项

| 问题             | 解决方案                                   |
| ---------------- | ------------------------------------------ |
| 实体被LLM改写    | Prompt强调"原样保留"，校验时检查原文存在性 |
| 关系名不统一     | 明确列出允许的关系，校验时警告未知关系     |
| 图结构检测错误   | 使用通用图结构兜底，保证任何文本都能处理   |
| JSON解析失败     | 使用正则提取，增加重试机制                 |
| 专家骨架被误过滤 | 配置`protect_anchors: true`                |