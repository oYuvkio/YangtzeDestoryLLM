# 📋 长江流域水旱灾害知识图谱构建系统 - 代码改进指导文档

## 一、项目概述

### 1.1 项目背景
本项目是一个基于大语言模型（LLM）的长江流域水旱灾害知识图谱构建系统。采用CQ（能力问题）驱动的方法，通过P1-P5的流水线完成从本体构建到知识抽取的全过程。

### 1.2 改进目标
本次改进旨在解决两个核心问题：
1. **幻觉问题**：LLM生成原文中不存在的实体或关系
2. **实体冗余**：同一对象存在多种表述（如"长江"与"扬子江"）

### 1.3 改进范围
| 改进项           | 类型       | 优先级     | 预期效果           |
| ---------------- | ---------- | ---------- | ------------------ |
| P4+统一去重      | 调用优化   | P1         | 消除本体层重复概念 |
| P5+ 原文回溯校验 | 新增模块   | P0（最高） | 幻觉率从15%降至5%  |
| P5 CoT Prompt    | 修改Prompt | P1         | 召回率提升5-10%    |
| P6 知识融合      | 新增模块   | P1         | 实体冗余率降至5%   |

---

## 二、项目结构

### 2.1 当前目录结构
```
project/
├── kg/
│   └ __init__.py
│   └ cq_llm_pipeline.py      # 主流水线（P1-P5）
│   └ llm_core.py             # LLM调用封装
│   └ prompts.py              # Prompt模板
│   └── utils/
│       └ deduplication.py    # 向量去重工具
│       └ schema_alignment.py # Schema对齐
│       └ entity_linking.py   # 实体链接
├── outputs/
│   └── cq_pipeline/
│       └── final/              # 输出文件
└── data/
    └── corpus/                 # 语料库
```

### 2.2 改进后新增文件
```
kg/
├── hallucination_filter.py     # 【新增】P5+ 幻觉校验模块
├── entity_fusion.py            # 【新增】P6 知识融合模块
└── prompts.py                  # 【修改】新增CoT版本Prompt
```

---

## 三、改进任务详细说明

### 任务1：新增幻觉校验模块（P5+）

#### 3.1.1 目标
创建 `kg/hallucination_filter.py`，实现对P5抽取结果的原文回溯校验，过滤掉原文中不存在的幻觉实体。

#### 3.1.2 核心原理
**假设**：抽取任务的输出必须是输入的子集。如果抽取的实体不在原文中出现，则判定为幻觉。

#### 3.1.3 文件内容要求

```python
# kg/hallucination_filter.py

"""
原文回溯校验模块

功能：检查P5抽取的实体是否在原文中出现，过滤幻觉
位置：P5抽取之后、P6融合之前
"""

from difflib import SequenceMatcher
from typing import List, Dict, Tuple
import re
import logging

logger = logging.getLogger(__name__)


class HallucinationFilter:
    """
    原文回溯校验器
    
    核心逻辑：
    1. 对于每个三元组，检查subject和object是否在原文中出现
    2. 支持精确匹配和模糊匹配两种模式
    3. 记录被过滤的三元组及原因，便于统计幻觉率
    """
    
    def __init__(
        self, 
        fuzzy_threshold: float = 0.8,
        strict_mode: bool = True,
        min_entity_length: int = 2
    ):
        """
        初始化校验器
        
        Args:
            fuzzy_threshold: 模糊匹配相似度阈值（0-1），默认0.8
            strict_mode: 严格模式，True时仅精确匹配，False时启用模糊匹配
            min_entity_length: 最小实体长度，过短的实体跳过校验（如单个数字）
        """
        # 实现初始化逻辑
        pass
    
    def verify_triples(
        self, 
        triples: List[Dict], 
        original_text: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        批量验证三元组
        
        Args:
            triples: 三元组列表，格式为 [{"subject": str, "predicate": str, "object": str, ...}, ...]
            original_text: 原始文本
            
        Returns:
            valid_triples: 通过验证的三元组列表
            filtered_triples: 被过滤的三元组列表，每个元素包含 {"triple": dict, "reason": str}
        
        处理逻辑：
        1. 预处理原文（去除空白字符便于匹配）
        2. 遍历每个三元组
        3. 分别验证subject和object
        4. 两者都通过则保留，否则记录过滤原因
        """
        # 实现验证逻辑
        pass
    
    def _check_entity(
        self, 
        entity: str, 
        clean_text: str, 
        original_text: str
    ) -> Tuple[bool, str]:
        """
        检查单个实体是否存在于原文中
        
        Args:
            entity: 待检查的实体字符串
            clean_text: 去除空白后的原文
            original_text: 原始文本
            
        Returns:
            (is_valid, reason): 是否通过验证及原因
        
        匹配优先级：
        1. 精确匹配（去空格后）
        2. 原文精确匹配（保留空格）
        3. 模糊匹配（非严格模式下）
        """
        # 实现检查逻辑
        pass
    
    def _fuzzy_search(self, entity: str, text: str) -> float:
        """
        滑动窗口模糊搜索
        
        在文本中搜索与实体最相似的片段，返回最高相似度
        使用 difflib.SequenceMatcher 计算相似度
        """
        # 实现模糊搜索逻辑
        pass
    
    def get_hallucination_rate(self, total: int) -> float:
        """计算幻觉率 = 被过滤数量 / 总数量"""
        pass
    
    def get_statistics(self) -> Dict:
        """获取过滤统计信息"""
        pass


# 便捷函数
def filter_hallucinations(
    triples: List[Dict],
    original_text: str,
    strict_mode: bool = True,
    fuzzy_threshold: float = 0.8
) -> Tuple[List[Dict], List[Dict], float]:
    """
    便捷函数：一步完成幻觉过滤
    
    Returns:
        (valid_triples, filtered_triples, hallucination_rate)
    """
    pass
```

#### 3.1.4 测试用例要求

在文件末尾添加测试代码：

```python
if __name__ == "__main__":
    # 测试用例
    text = "1998年8月，长江干流沙市站水位达到45.22米，超过历史最高水位。"
    
    triples = [
        {"subject": "沙市站", "predicate": "水位达到", "object": "45.22米"},      # 应保留
        {"subject": "武汉站", "predicate": "水位达到", "object": "30米"},          # 应过滤（武汉站不在原文）
        {"subject": "长江干流", "predicate": "包含", "object": "沙市站"},          # 应保留
        {"subject": "1998年", "predicate": "发生", "object": "特大洪水"},          # 应过滤（特大洪水不在原文）
    ]
    
    valid, filtered, rate = filter_hallucinations(triples, text, strict_mode=True)
    
    print(f"通过: {len(valid)}, 过滤: {len(filtered)}, 幻觉率: {rate:.1%}")
    
    # 预期输出：通过: 2, 过滤: 2, 幻觉率: 50.0%
```

---

### 任务2：新增知识融合模块（P6）

#### 3.2.1 目标
创建 `kg/entity_fusion.py`，实现实体归一化和关系去重，解决抽取结果中的实体冗余问题。

#### 3.2.2 核心原理
1. **实体归一化**：将指代同一对象的不同表述合并（如"长江"="扬子江"）
2. **关系去重**：合并相同的(subject, predicate, object)三元组，统计支持度

#### 3.2.3 文件内容要求

```python
# kg/entity_fusion.py

"""
知识融合模块

功能：实体归一化 + 关系去重
位置：P5+校验之后、入库之前
"""

from typing import List, Dict, Tuple, Set, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class EntityFusion:
    """
    实体融合与关系去重
    
    功能1 - 实体归一化：
    - 使用预定义别名字典
    - 将同义实体映射到统一名称
    
    功能2 - 关系去重：
    - 合并相同的(subject, predicate, object)三元组
    - 记录支持度（出现次数）
    """
    
    def __init__(
        self,
        alias_dict: Optional[Dict[str, str]] = None,
        use_embedding: bool = False,
        embedding_threshold: float = 0.9
    ):
        """
        初始化融合器
        
        Args:
            alias_dict: 预定义的别名映射字典，格式 {"别名": "标准名"}
                       如果为None，使用内置的长江流域常见别名
            use_embedding: 是否使用向量相似度进行实体匹配（高级功能，可选）
            embedding_threshold: 向量相似度阈值
        """
        pass
    
    def _default_alias_dict(self) -> Dict[str, str]:
        """
        返回预定义的长江流域常见别名字典
        
        应包含：
        - 河流别名：扬子江->长江, 大江->长江
        - 湖泊别名：洞庭->洞庭湖, 鄱阳->鄱阳湖
        - 水库别名：三峡大坝->三峡水库
        - 城市别名：武汉市->武汉, 南京市->南京
        """
        pass
    
    def normalize_entity(self, entity: str) -> str:
        """
        单个实体归一化
        
        处理逻辑：
        1. 去除首尾空白
        2. 查找预定义别名
        3. 处理常见后缀变体（如"武汉市"中的"市"）
        4. 返回标准化名称
        """
        pass
    
    def normalize_entities(self, triples: List[Dict]) -> List[Dict]:
        """
        批量归一化三元组中的实体
        
        对每个三元组的subject和object进行归一化
        记录归一化日志
        """
        pass
    
    def deduplicate_relations(
        self, 
        triples: List[Dict],
        keep_evidence: bool = True
    ) -> List[Dict]:
        """
        关系去重
        
        Args:
            triples: 三元组列表
            keep_evidence: 是否保留所有evidence（合并为列表）
            
        Returns:
            去重后的三元组列表，每个三元组增加:
            - support: int, 出现次数
            - evidence: str或List[str], 原文证据
        
        处理逻辑：
        1. 以(subject, predicate, object)为key分组
        2. 合并同组三元组
        3. 统计支持度
        4. 合并evidence字段
        """
        pass
    
    def get_statistics(self) -> Dict:
        """获取融合统计信息"""
        pass


# 便捷函数
def fuse_knowledge(
    triples: List[Dict],
    alias_dict: Optional[Dict[str, str]] = None
) -> Tuple[List[Dict], Dict]:
    """
    便捷函数：完整的知识融合流程
    
    执行：实体归一化 -> 关系去重
    
    Returns:
        (fused_triples, statistics)
        
    statistics包含：
        - entity_merges: 实体合并次数
        - original_triple_count: 原始三元组数
        - final_triple_count: 最终三元组数
        - reduction_rate: 缩减比例
    """
    pass
```

#### 3.2.4 测试用例要求

```python
if __name__ == "__main__":
    # 测试用例
    triples = [
        {"subject": "长江", "predicate": "发生", "object": "洪水", "evidence": "长江发生洪水"},
        {"subject": "扬子江", "predicate": "发生", "object": "洪水", "evidence": "扬子江发生大水"},
        {"subject": "长江", "predicate": "流经", "object": "武汉市", "evidence": "长江流经武汉"},
        {"subject": "长江", "predicate": "流经", "object": "武汉", "evidence": "长江穿过武汉"},
    ]
    
    fused, stats = fuse_knowledge(triples)
    
    print(f"原始: {stats['original_triple_count']}, 融合后: {stats['final_triple_count']}")
    print(f"缩减率: {stats['reduction_rate']:.1%}")
    
    for t in fused:
        print(f"  {t['subject']} --{t['predicate']}--> {t['object']} (支持度: {t['support']})")
    
    # 预期输出：
    # 原始: 4, 融合后: 2
    # 缩减率: 50.0%
    # 长江 --发生--> 洪水 (支持度: 2)
    # 长江 --流经--> 武汉 (支持度: 2)
```

---

### 任务3：修改P5 Prompt为CoT版本

#### 3.3.1 目标
在 `kg/prompts.py` 中新增 `P5_COT_EXTRACTION_PROMPT`，实现思维链分步抽取。

#### 3.3.2 修改位置
文件：`kg/prompts.py`
位置：在现有的 `P5_EXTRACTION_PROMPT` 之后新增

#### 3.3.3 新增Prompt内容

```python
# 在 prompts.py 中新增

P5_COT_EXTRACTION_PROMPT = """
你是一名水旱灾害知识图谱构建专家。

TBox 定义（classes / relations / attributes）：
{schema_json}

事件 Schema 参考：
{event_schema}

---

【重要说明】

输入文本可能包含三个部分：
1. 【前文参考】：提供上下文背景
2. 【待抽取文本】：**主要抽取目标**
3. 【后文参考】：提供后续上下文

---

【核心约束 - 请务必遵守】

1. **所有抽取的实体必须是原文的子串**，不可改写、推断或编造
2. 关系必须来自Schema定义的relations列表，不可自创
3. 如果文本中找不到相关信息，返回空列表而非编造

---

请按照以下步骤进行**逐步推理（Chain of Thought）**：

**Step 1: 实体扫描与定位**
仔细阅读【待抽取文本】，识别所有可能属于TBox类别的实体（如时间、地点、河流、数值、灾害名等）。
*自我验证*：逐一检查这些实体是否在原文中**原样出现**？如果不是原文子串，请修正为原文表述或丢弃。

**Step 2: 关系判断与Schema约束**
对于识别出的实体对，判断它们之间是否存在TBox定义的关系。
检查：
- 关系predicate是否在TBox.relations.name列表中？
- 关系的subject和object类型是否符合domain/range约束？
- *去幻觉*：这条关系在原文中有明确的句子支持吗？如果没有，请丢弃。

**Step 3: 三元组组装与证据标注**
将验证通过的实体和关系组装为规范化JSON格式。
为每个三元组标注evidence字段（从原文复制支撑该关系的句子片段）。

---

类使用提示：{class_usage_hint}

输入文本:
{input_text}

---

输出格式要求：

1. **请先输出思考过程**（以"【思考过程】"开头），简述你识别到的关键实体和推理逻辑（50-100字即可）。
2. 然后输出一个JSON对象（以```json开头），包含"events"和"triples"字段。
3. JSON结构必须严格符合以下定义：

```json
{{
  "events": [
    {{
      "event_id": "evt_年份_序号",
      "event_type": "TBox中的类名（如FloodEvent）",
      "name": "事件中文名称",
      "time": {{"start_time": "YYYY-MM-DD或空字符串", "end_time": "YYYY-MM-DD或空字符串"}},
      "space": {{
        "main_stream": ["主要干流"],
        "tributaries": ["受影响支流或湖泊"],
        "provinces": ["主要受灾省份"]
      }},
      "causes": ["致灾因子列表"],
      "impacts": {{
        "affected_population": "受灾人口（原文表述）",
        "deaths": "死亡人数（原文表述）"
      }},
      "responses": [{{"stage": "应急响应", "measures": ["措施列表"]}}],
      "source": "数据来源"
    }}
  ],
  "triples": [
    {{
      "subject": "实体名（必须是原文子串）",
      "predicate": "关系名（必须来自TBox.relations）",
      "object": "实体名（必须是原文子串）",
      "event_id": "关联的事件ID或空字符串",
      "evidence": "支撑该三元组的原文句子片段"
    }}
  ]
}}
```

请开始推理：
"""
```

#### 3.3.4 同时需要新增响应解析函数

在 `prompts.py` 末尾或新建 `kg/utils/response_parser.py` 添加：

```python
import json
import re
from typing import Dict, Optional


def parse_cot_response(response_text: str) -> Optional[Dict]:
    """
    解析带有CoT思考过程的LLM响应
    
    处理逻辑：
    1. 尝试提取```json代码块中的内容
    2. 如果没有代码块，尝试找{...}
    3. 解析JSON并返回
    4. 解析失败返回None
    
    Args:
        response_text: LLM的原始响应文本
        
    Returns:
        解析后的字典，包含events和triples字段
        解析失败返回None
    """
    if not response_text:
        return None
    
    # 1. 尝试提取```json代码块
    json_match = re.search(r"```json\s*(.*?)\s*```", response_text, re.DOTALL)
    
    if json_match:
        json_str = json_match.group(1)
    else:
        # 2. 尝试提取```代码块（不带json标记）
        code_match = re.search(r"```\s*(.*?)\s*```", response_text, re.DOTALL)
        if code_match:
            json_str = code_match.group(1)
        else:
            # 3. 尝试找{...}
            start = response_text.find("{")
            end = response_text.rfind("}") + 1
            if start != -1 and end > start:
                json_str = response_text[start:end]
            else:
                return None
    
    try:
        data = json.loads(json_str.strip())
        return data
    except json.JSONDecodeError:
        logger.error(f"Failed to parse JSON: {json_str[:200]}...")
        return None


def extract_cot_thought(response_text: str) -> str:
    """
    提取CoT思考过程
    
    Args:
        response_text: LLM的原始响应文本
        
    Returns:
        思考过程字符串，无则返回空字符串
    """
    if not response_text:
        return ""
    
    # 查找【思考过程】标记后的内容
    match = re.search(r"【思考过程】(.*?)(?=```|$)", response_text, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""
```

---

### 任务4：修改Pipeline调用流程

#### 3.4.1 目标
修改 `kg/cq_llm_pipeline.py`，集成新模块到完整流程。

#### 3.4.2 修改内容

**修改1：在文件顶部添加导入**

```python
# 在现有导入之后添加
from kg.hallucination_filter import HallucinationFilter, filter_hallucinations
from kg.entity_fusion import EntityFusion, fuse_knowledge
from kg.prompts import P5_COT_EXTRACTION_PROMPT  # 如果新增了这个常量
from kg.utils.response_parser import parse_cot_response, extract_cot_thought
```

**修改2：新增带校验的抽取方法**

在 `CQLLMPipeline` 类中新增方法：

```python
def extract_events_with_verification(
    self,
    paragraph: str,
    schema: TBoxSchema,
    save_path: Optional[Path] = None,
    strict_mode: bool = True,
    use_cot: bool = True,
) -> Dict[str, Any]:
    """
    带幻觉校验的事件抽取（P5 + P5+）
    
    Args:
        paragraph: 待抽取的文本段落
        schema: TBox Schema
        save_path: 结果保存路径
        strict_mode: 幻觉校验的严格模式
        use_cot: 是否使用CoT版本的Prompt
        
    Returns:
        包含以下字段的字典：
        - events: 抽取的事件列表
        - triples: 校验后的三元组列表
        - filtered_triples: 被过滤的三元组列表
        - hallucination_rate: 幻觉率
        - thought: CoT思考过程（如果使用CoT Prompt）
    """
    # 1. 执行抽取（使用CoT或普通Prompt）
    if use_cot:
        prompt = P5_COT_EXTRACTION_PROMPT.format(
            schema_json=json.dumps(schema.to_dict(), ensure_ascii=False, indent=2),
            event_schema=self._get_event_schema(schema),
            class_usage_hint=self._get_class_usage_hint(schema),
            input_text=paragraph
        )
        response_text = self.llm_client.generate(prompt)
        raw_result = parse_cot_response(response_text)
        thought = extract_cot_thought(response_text)
    else:
        raw_result = self.extract_events(paragraph, schema, save_path=None)
        thought = ""
    
    if not raw_result:
        logger.warning("Failed to extract events")
        result = {
            'events': [],
            'triples': [],
            'filtered_triples': [],
            'hallucination_rate': 0.0,
            'raw_triple_count': 0,
            'valid_triple_count': 0,
            'thought': thought
        }
        if save_path:
            self._dump_json(result, save_path)
        return result
    
    # 2. 幻觉校验
    raw_triples = raw_result.get('triples', [])
    valid_triples, filtered_triples, hallucination_rate = filter_hallucinations(
        triples=raw_triples,
        original_text=paragraph,
        strict_mode=strict_mode
    )
    
    result = {
        'events': raw_result.get('events', []),
        'triples': valid_triples,
        'filtered_triples': filtered_triples,
        'hallucination_rate': hallucination_rate,
        'raw_triple_count': len(raw_triples),
        'valid_triple_count': len(valid_triples),
        'thought': thought
    }
    
    if save_path:
        self._dump_json(result, save_path)
    
    return result
```

**修改3：新增批量抽取+融合方法**

```python
def extract_and_fuse(
    self,
    segments: List[Dict[str, Any]],
    schema: TBoxSchema,
    save_dir: Optional[Path] = None,
    strict_mode: bool = True,
) -> Dict[str, Any]:
    """
    批量抽取并融合（P5 + P5+ + P6）
    
    完整流程：对每个片段抽取 -> 幻觉校验 -> 汇总 -> 实体归一化 -> 关系去重
    
    Args:
        segments: 文本片段列表，每个元素包含 {"text": str, ...}
        schema: TBox Schema
        save_dir: 结果保存目录
        strict_mode: 幻觉校验的严格模式
        
    Returns:
        包含以下字段的字典：
        - all_events: 所有抽取的事件
        - fused_triples: 融合后的三元组
        - statistics: 统计信息
    """
    all_events = []
    all_triples = []
    total_raw = 0
    total_filtered = 0
    all_thoughts = []
    
    # P5 + P5+: 逐片段抽取并校验
    for i, seg in enumerate(segments):
        text = seg.get('text', '')
        if not text.strip():
            continue
        
        result = self.extract_events_with_verification(
            paragraph=text,
            schema=schema,
            strict_mode=strict_mode,
        )
        
        all_events.extend(result.get('events', []))
        all_triples.extend(result.get('triples', []))
        total_raw += result.get('raw_triple_count', 0)
        total_filtered += len(result.get('filtered_triples', []))
        if result.get('thought'):
            all_thoughts.append({
                'segment_index': i,
                'text_preview': text[:100] + "...",
                'thought': result['thought']
            })
    
    # P6: 知识融合
    fused_triples, fusion_stats = fuse_knowledge(all_triples)
    
    result = {
        'all_events': all_events,
        'fused_triples': fused_triples,
        'all_thoughts': all_thoughts,
        'statistics': {
            'segment_count': len(segments),
            'event_count': len(all_events),
            'raw_triple_count': total_raw,
            'after_verification_count': len(all_triples),
            'after_fusion_count': len(fused_triples),
            'hallucination_rate': total_filtered / total_raw if total_raw > 0 else 0,
            'fusion_reduction_rate': fusion_stats.get('reduction_rate', 0),
            **fusion_stats
        }
    }
    
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)
        self._dump_json(result, save_dir / "extraction_result.json")
    
    return result
```

**修改4：更新run_quick_demo函数（可选）**

```python
def run_quick_demo() -> None:
    """演示完整流程"""
    pipeline = CQLLMPipeline()
    out_dir = Path("outputs/cq_pipeline/final")
    
    # ... 现有P1-P4代码 ...
    
    # P4+: 统一去重
    tbox_final = CQLLMPipeline.deduplicate_tbox(tbox_normalized, threshold=0.75)
    pipeline._dump_json(tbox_final.to_dict(), out_dir / "tbox_final_deduped.json")
    
    # P5 + P5+ + P6: 带校验和融合的抽取
    result = pipeline.extract_events_with_verification(
        paragraph=DEMO_PARAGRAPH_1998,
        schema=tbox_final,
        strict_mode=True,
    )
    
    print(f"抽取事件: {len(result['events'])} 个")
    print(f"原始三元组: {result['raw_triple_count']} 条")
    print(f"校验后: {result['valid_triple_count']} 条")
    print(f"幻觉率: {result['hallucination_rate']:.1%}")
    if result.get('thought'):
        print(f"\n思考过程:\n{result['thought']}")
```

---

## 四、执行顺序

请按以下顺序执行任务：

### 阶段1：核心模块开发
1. **任务1**：创建 `kg/hallucination_filter.py`
2. **任务2**：创建 `kg/entity_fusion.py`
3. 分别运行测试用例，确保模块功能正确

### 阶段2：Prompt优化
4. **任务3**：在 `kg/prompts.py` 中新增 `P5_COT_EXTRACTION_PROMPT` 和解析函数

### 阶段3：流程集成
5. **任务4**：修改 `kg/cq_llm_pipeline.py`，集成新模块

### 阶段4：验证测试
6. 运行 `run_quick_demo()` 验证完整流程

---

## 五、验收标准

### 5.1 功能验收

| 模块                | 验收标准                             |
| ------------------- | ------------------------------------ |
| HallucinationFilter | 测试用例通过，能正确过滤幻觉实体     |
| EntityFusion        | 测试用例通过，能正确归一化实体并去重 |
| P5_COT_PROMPT       | 能被LLM正确理解并返回格式正确的JSON  |
| Pipeline集成        | 完整流程能顺利运行，无报错           |

### 5.2 质量验收

| 指标       | 目标值             |
| ---------- | ------------------ |
| 幻觉率     | < 10%（理想 < 5%） |
| 实体冗余率 | < 10%（理想 < 5%） |
| 代码覆盖   | 核心逻辑有测试用例 |

### 5.3 代码规范

- 所有函数有类型注解
- 所有类和公共函数有docstring
- 使用logging记录关键操作
- 遵循PEP 8代码风格

---

## 六、注意事项

### 6.1 兼容性
- 新模块不应破坏现有功能
- 现有的 `extract_events` 方法保持不变
- 新增方法作为增强选项

### 6.2 性能考虑
- HallucinationFilter 使用字符串操作，无需外部依赖
- EntityFusion 的别名字典可扩展，但应控制规模
- 批量处理时注意内存占用

### 6.3 错误处理
- 输入为空时应返回空结果而非报错
- JSON解析失败时应有兜底处理
- 记录警告日志便于排查问题

---

## 七、参考资料

### 7.1 现有代码位置
- 主流水线：`kg/cq_llm_pipeline.py`
- Prompt模板：`kg/prompts.py`
- 去重工具：`kg/utils/deduplication.py`

### 7.2 数据格式示例

**三元组格式**：
```python
{
    "subject": "长江",
    "predicate": "发生",
    "object": "洪水",
    "event_id": "evt_1998_01",
    "evidence": "长江发生特大洪水"
}
```

**融合后三元组格式**：
```python
{
    "subject": "长江",
    "predicate": "发生",
    "object": "洪水",
    "event_id": "evt_1998_01",
    "evidence": ["长江发生洪水", "扬子江发生大水"],
    "support": 2
}
```