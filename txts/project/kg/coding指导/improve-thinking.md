# 水旱灾害知识图谱构建项目 - AI编码指导文档

## 文档说明

本文档用于指导AI助手（如Claude Code）对项目代码进行新增和改进。请严格按照本文档的步骤和规范执行。

---

## 一、项目概述

### 1.1 项目背景

这是一个基于大语言模型（LLM）的水旱灾害知识图谱构建项目。当前项目已实现P1-P5的基础流程，需要新增以下功能来解决LLM的"幻觉"问题。

### 1.2 改进目标

| 目标         | 描述                                       | 优先级   |
| ------------ | ------------------------------------------ | -------- |
| 本体统一去重 | 在P4之后、P5之前，对TBox进行统一的向量去重 | 高       |
| CoT分步抽取  | 将P5的Prompt改为思维链格式，分4步引导抽取  | **最高** |
| 原文回溯校验 | 新增P6模块，验证抽取结果是否在原文中有依据 | **最高** |
| 实体标准化   | 对抽取结果进行轻量级格式标准化             | 中       |

### 1.3 核心原则

1. **最小改动原则**：尽量复用现有代码，避免大规模重构
2. **向后兼容原则**：新增功能不破坏现有接口
3. **可测试原则**：每个新增模块必须可独立测试

---

## 二、项目结构

### 2.1 当前结构

```
kg/
├── pipelines/
│   └── cq_pipeline.py          # 主Pipeline类 [需修改]
├── utils/
│   ├── deduplication.py        # 向量去重工具 [已有]
│   ├── schema_alignment.py     # Schema对齐 [已有]
│   └── entity_linking.py       # 实体链接 [已有]
└── prompts/
    └── prompts.py              # Prompt模板 [需修改]
```

### 2.2 目标结构

```
kg/
├── pipelines/
│   └── cq_pipeline.py          # 主Pipeline类 [修改：新增3个方法]
├── extraction/
│   └── hallucination_filter.py # 幻觉过滤器 [新增文件]
├── utils/
│   ├── deduplication.py        # 向量去重工具 [已有]
│   ├── schema_alignment.py     # Schema对齐 [已有]
│   ├── entity_linking.py       # 实体链接 [已有]
│   └── entity_normalizer.py    # 实体标准化 [新增文件]
└── prompts/
    └── prompts.py              # Prompt模板 [修改：新增1个常量]
```

---

## 三、执行任务清单

### 任务总览

| 任务ID | 任务名称                          | 类型 | 依赖     | 预计工作量 |
| ------ | --------------------------------- | ---- | -------- | ---------- |
| T1     | 新增P5 CoT Prompt                 | 修改 | 无       | 15分钟     |
| T2     | 新增HallucinationFilter类         | 新增 | 无       | 30分钟     |
| T3     | 新增SimpleEntityNormalizer类      | 新增 | 无       | 15分钟     |
| T4     | 新增finalize_tbox方法             | 修改 | T2       | 20分钟     |
| T5     | 新增extract_with_verification方法 | 修改 | T1,T2,T3 | 25分钟     |
| T6     | 编写单元测试                      | 新增 | T1-T5    | 20分钟     |

**执行顺序**：T1 → T2 → T3 → T4 → T5 → T6

---

## 四、任务详细说明

### 任务T1：新增P5 CoT Prompt

#### 目标
在`prompts.py`中新增思维链格式的P5抽取Prompt。

#### 文件位置
`kg/prompts/prompts.py`

#### 操作步骤

1. 打开文件`kg/prompts/prompts.py`
2. 在文件末尾（在`P5_EXTRACTION_PROMPT`之后）添加新的常量`P5_EXTRACTION_PROMPT_COT`
3. 不要删除或修改原有的`P5_EXTRACTION_PROMPT`

#### 代码实现

```python
# ========== P5：事件与三元组抽取（CoT增强版） ==========
P5_EXTRACTION_PROMPT_COT = """
你是一名面向水旱灾害的知识图谱构建助手。

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

【抽取步骤】—— 请严格按照以下步骤进行思考（Chain-of-Thought）：

**Step 1: 实体扫描与定位**
仔细阅读【待抽取文本】，识别所有可能属于 TBox 类别的实体：
- 时间（年份、日期、时间段）
- 地点（省市、河流、水库、湖泊）
- 灾害事件（洪水、干旱等）
- 数值指标（水位、流量、损失数额）
- 机构/措施（政府部门、应急响应等）

【自检】：这些实体是否在原文中**原样出现**？如不是，请修正为原文表述。

**Step 2: 事件识别与分类**
判断文本是否描述了具体灾害事件，确定事件类型。
类使用提示：{class_usage_hint}

**Step 3: 关系构建与Schema约束**
用 TBox.relations 连接实体：
- 检查：predicate 是否在 TBox.relations.name 中？
- 检查：subject/object 类型是否符合 domain/range？

**Step 4: 证据回溯与去幻觉**【核心步骤】
对每条三元组，必须从原文找到支撑句：
- 如果找不到明确的原文依据，请**丢弃**该三元组
- 实体名称必须与原文**完全一致**，不可改写或推断

---

输入文本:
{input_text}

---

【输出要求】

1. **首先输出思考过程**（以"【思考过程】"开头），简述识别到的关键实体和推理逻辑
2. **然后输出JSON结果**（以 ```json 开头）

```json
{{
  "events": [
    {{
      "event_id": "evt_年份_序号",
      "event_type": "TBox中的类名",
      "name": "事件中文名称",
      "time": {{"start_time": "", "end_time": ""}},
      "space": {{"main_stream": [], "tributaries": [], "provinces": []}},
      "causes": [],
      "impacts": {{"affected_population": "", "deaths": "", "direct_economic_loss": ""}},
      "responses": [],
      "source": ""
    }}
  ],
  "triples": [
    {{
      "subject": "主语（必须是原文子串）",
      "predicate": "关系（必须来自TBox）",
      "object": "宾语（必须是原文子串）",
      "event_id": "关联事件ID或空",
      "evidence": "原文支撑句"
    }}
  ]
}}
```

请开始分析：
"""
```

#### 验证标准
- [ ] 文件无语法错误
- [ ] 常量`P5_EXTRACTION_PROMPT_COT`可被正常import
- [ ] 包含4个Step说明
- [ ] 包含`{schema_json}`、`{event_schema}`、`{input_text}`、`{class_usage_hint}`四个占位符

---

### 任务T2：新增HallucinationFilter类

#### 目标
创建原文回溯校验模块，用于过滤LLM生成的幻觉三元组。

#### 文件位置
`kg/extraction/hallucination_filter.py`（新建文件）

#### 操作步骤

1. 创建目录`kg/extraction/`（如不存在）
2. 创建文件`kg/extraction/__init__.py`
3. 创建文件`kg/extraction/hallucination_filter.py`

#### 代码实现

**文件：`kg/extraction/__init__.py`**

```python
from .hallucination_filter import HallucinationFilter, VerificationResult, filter_hallucinations

__all__ = ['HallucinationFilter', 'VerificationResult', 'filter_hallucinations']
```

**文件：`kg/extraction/hallucination_filter.py`**

```python
"""
原文回溯验证模块（P6）

核心思想：有效的抽取结果必须在原文中具有明确的文本证据。
通过检查三元组的subject和object是否在原文中出现来过滤幻觉。

技术来源：钟成(2025) §3.1.2 双重验证机制
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """
    验证结果数据类
    
    Attributes:
        valid_triples: 通过验证的三元组列表
        filtered_triples: 被过滤的三元组列表（含过滤原因）
        valid_events: 通过验证的事件列表
        total_triples: 待验证的三元组总数
        valid_count: 通过验证的三元组数
        filtered_count: 被过滤的三元组数
        hallucination_rate: 幻觉率（百分比）
        verification_log: 验证日志
    """
    valid_triples: List[Dict] = field(default_factory=list)
    filtered_triples: List[Dict] = field(default_factory=list)
    valid_events: List[Dict] = field(default_factory=list)
    
    total_triples: int = 0
    valid_count: int = 0
    filtered_count: int = 0
    hallucination_rate: float = 0.0
    
    verification_log: List[str] = field(default_factory=list)


class HallucinationFilter:
    """
    基于原文回溯的幻觉过滤器
    
    验证规则：
    1. 三元组的subject必须在原文中出现（精确匹配或模糊匹配）
    2. 三元组的object必须在原文中出现（精确匹配或模糊匹配）
    3. 同时通过验证的三元组才会被保留
    
    Args:
        strict_mode: 是否使用严格模式（仅精确匹配）
        fuzzy_threshold: 模糊匹配的相似度阈值（0.0-1.0）
        verbose: 是否输出详细日志
        
    Example:
        >>> filter = HallucinationFilter(strict_mode=False, fuzzy_threshold=0.8)
        >>> result = filter.verify(extraction_result, original_text)
        >>> print(f"幻觉率: {result.hallucination_rate:.2f}%")
    """
    
    def __init__(
        self,
        strict_mode: bool = False,
        fuzzy_threshold: float = 0.8,
        verbose: bool = True
    ):
        self.strict_mode = strict_mode
        self.fuzzy_threshold = fuzzy_threshold
        self.verbose = verbose
    
    def verify(
        self,
        extraction_result: Dict,
        original_text: str,
        context_before: str = "",
        context_after: str = ""
    ) -> VerificationResult:
        """
        验证抽取结果
        
        Args:
            extraction_result: P5抽取的结果，包含events和triples字段
            original_text: 原始文本（待抽取文本）
            context_before: 前文上下文（可选）
            context_after: 后文上下文（可选）
            
        Returns:
            VerificationResult: 包含验证结果和统计信息
        """
        result = VerificationResult()
        
        # 合并文本用于验证（主文本+上下文）
        full_text = self._merge_text(original_text, context_before, context_after)
        full_text = self._normalize_text(full_text)
        
        # 验证事件（宽松处理，主要验证事件名称）
        events = extraction_result.get("events", [])
        for event in events:
            if isinstance(event, dict):
                result.valid_events.append(event)
        
        # 验证三元组（严格处理）
        triples = extraction_result.get("triples", [])
        result.total_triples = len(triples)
        
        for triple in triples:
            if not isinstance(triple, dict):
                continue
                
            is_valid, reason = self._verify_triple(triple, full_text)
            
            if is_valid:
                result.valid_triples.append(triple)
                result.valid_count += 1
            else:
                triple_with_reason = {**triple, "filter_reason": reason}
                result.filtered_triples.append(triple_with_reason)
                result.filtered_count += 1
                
                if self.verbose:
                    s = triple.get("subject", "")
                    p = triple.get("predicate", "")
                    o = triple.get("object", "")
                    log_msg = f"[过滤] {s} --{p}--> {o} | 原因: {reason}"
                    result.verification_log.append(log_msg)
                    logger.debug(log_msg)
        
        # 计算幻觉率
        if result.total_triples > 0:
            result.hallucination_rate = result.filtered_count / result.total_triples * 100
        
        return result
    
    def _merge_text(self, main: str, before: str, after: str) -> str:
        """合并主文本和上下文"""
        parts = []
        if before and before.strip():
            parts.append(before.strip())
        parts.append(main.strip())
        if after and after.strip():
            parts.append(after.strip())
        return " ".join(parts)
    
    def _normalize_text(self, text: str) -> str:
        """标准化文本（去除多余空白）"""
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    def _verify_triple(self, triple: Dict, text: str) -> Tuple[bool, str]:
        """
        验证单个三元组
        
        Returns:
            Tuple[bool, str]: (是否有效, 原因说明)
        """
        subject = triple.get("subject", "").strip()
        obj = triple.get("object", "").strip()
        
        # 验证subject
        s_valid, s_method = self._check_existence(subject, text)
        if not s_valid:
            return False, f"主语'{subject}'未在原文中找到"
        
        # 验证object
        o_valid, o_method = self._check_existence(obj, text)
        if not o_valid:
            return False, f"宾语'{obj}'未在原文中找到"
        
        return True, f"验证通过(subject:{s_method}, object:{o_method})"
    
    def _check_existence(self, entity: str, text: str) -> Tuple[bool, str]:
        """
        检查实体是否存在于文本中
        
        Returns:
            Tuple[bool, str]: (是否存在, 匹配方法)
        """
        if not entity:
            return False, "empty"
        
        # 1. 精确匹配
        if entity in text:
            return True, "exact"
        
        # 严格模式下到此为止
        if self.strict_mode:
            return False, "not_found"
        
        # 2. 忽略空格匹配
        entity_norm = entity.replace(" ", "").replace("　", "")
        text_norm = text.replace(" ", "").replace("　", "")
        if entity_norm in text_norm:
            return True, "normalized"
        
        # 3. 模糊匹配（滑动窗口）
        entity_len = len(entity)
        best_ratio = 0.0
        
        for i in range(max(0, len(text) - entity_len - 5)):
            window = text[i:i + entity_len + 2]
            ratio = SequenceMatcher(None, entity, window[:entity_len]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
            if ratio >= self.fuzzy_threshold:
                return True, f"fuzzy({ratio:.2f})"
        
        return False, "not_found"


def filter_hallucinations(
    extraction_result: Dict,
    original_text: str,
    context_before: str = "",
    context_after: str = "",
    strict: bool = False,
    threshold: float = 0.8
) -> Dict:
    """
    便捷函数：过滤抽取结果中的幻觉
    
    Args:
        extraction_result: P5抽取结果
        original_text: 原始文本
        context_before: 前文上下文
        context_after: 后文上下文
        strict: 是否严格模式
        threshold: 模糊匹配阈值
        
    Returns:
        包含过滤结果和统计信息的字典
    """
    f = HallucinationFilter(strict_mode=strict, fuzzy_threshold=threshold)
    r = f.verify(extraction_result, original_text, context_before, context_after)
    
    return {
        "events": r.valid_events,
        "triples": r.valid_triples,
        "filtered_triples": r.filtered_triples,
        "stats": {
            "total": r.total_triples,
            "valid": r.valid_count,
            "filtered": r.filtered_count,
            "hallucination_rate": f"{r.hallucination_rate:.2f}%"
        },
        "log": r.verification_log
    }
```

#### 验证标准
- [ ] 文件无语法错误
- [ ] `HallucinationFilter`类可被正常实例化
- [ ] `verify`方法返回`VerificationResult`对象
- [ ] 精确匹配测试通过：`"长江" in "长江流域发生洪水"` 返回True
- [ ] 幻觉检测测试通过：`"黄河" in "长江流域发生洪水"` 返回False

---

### 任务T3：新增SimpleEntityNormalizer类

#### 目标
创建轻量级实体标准化模块，对抽取结果进行基础格式统一。

#### 文件位置
`kg/utils/entity_normalizer.py`（新建文件）

#### 代码实现

```python
"""
轻量级实体标准化模块

仅做基础的格式统一，不做复杂的实体链接。
主要功能：
1. 去除首尾空白
2. 统一空格
3. 全角转半角数字
"""

from __future__ import annotations

import re
from typing import Dict, List


class SimpleEntityNormalizer:
    """
    简单实体标准化器
    
    Example:
        >>> normalizer = SimpleEntityNormalizer()
        >>> normalizer.normalize("  长江  ")
        '长江'
        >>> normalizer.normalize("２０２０年")
        '2020年'
    """
    
    def __init__(self):
        pass
    
    def normalize(self, entity: str) -> str:
        """
        标准化单个实体
        
        Args:
            entity: 原始实体字符串
            
        Returns:
            标准化后的实体字符串
        """
        if not entity:
            return entity
        
        # 1. 去除首尾空白
        entity = entity.strip()
        
        # 2. 统一空格（多个空格合并为一个）
        entity = re.sub(r'\s+', ' ', entity)
        
        # 3. 去除全角空格
        entity = entity.replace('　', '')
        
        # 4. 全角转半角数字
        entity = self._full_to_half_digits(entity)
        
        return entity
    
    def normalize_triple(self, triple: Dict) -> Dict:
        """
        标准化单个三元组
        
        Args:
            triple: 原始三元组字典
            
        Returns:
            标准化后的三元组字典
        """
        normalized = triple.copy()
        
        if "subject" in normalized:
            normalized["subject"] = self.normalize(normalized["subject"])
        if "object" in normalized:
            normalized["object"] = self.normalize(normalized["object"])
        
        # predicate不做标准化（应与Schema保持一致）
        
        return normalized
    
    def normalize_triples(self, triples: List[Dict]) -> List[Dict]:
        """
        批量标准化三元组
        
        Args:
            triples: 三元组列表
            
        Returns:
            标准化后的三元组列表
        """
        return [self.normalize_triple(t) for t in triples]
    
    @staticmethod
    def _full_to_half_digits(text: str) -> str:
        """
        全角数字转半角
        
        ０１２３４５６７８９ -> 0123456789
        """
        result = []
        for char in text:
            code = ord(char)
            # 全角数字范围: 0xFF10 (０) - 0xFF19 (９)
            if 0xFF10 <= code <= 0xFF19:
                result.append(chr(code - 0xFEE0))
            else:
                result.append(char)
        return ''.join(result)


def normalize_entities(triples: List[Dict]) -> List[Dict]:
    """
    便捷函数：标准化三元组列表中的实体
    
    Args:
        triples: 三元组列表
        
    Returns:
        标准化后的三元组列表
    """
    normalizer = SimpleEntityNormalizer()
    return normalizer.normalize_triples(triples)
```

#### 验证标准
- [ ] 文件无语法错误
- [ ] 空白处理正确：`normalize("  长江  ")` 返回 `"长江"`
- [ ] 全角数字转换正确：`normalize("２０２０年")` 返回 `"2020年"`

---

### 任务T4：新增finalize_tbox方法

#### 目标
在`CQLLMPipeline`类中新增本体统一去重方法。

#### 文件位置
`kg/pipelines/cq_pipeline.py`

#### 操作步骤

1. 打开文件`kg/pipelines/cq_pipeline.py`
2. 在`CQLLMPipeline`类中，找到`run_p4_over_corpus`方法之后的位置
3. 添加`finalize_tbox`方法和辅助方法

#### 代码实现

```python
# 在 CQLLMPipeline 类中添加以下方法

def finalize_tbox(
    self,
    schema: TBoxSchema,
    *,
    class_threshold: float = 0.85,
    relation_threshold: float = 0.80,
    save_path: Optional[Path] = None,
) -> TBoxSchema:
    """
    本体统一去重（P4之后、P5之前调用）
    
    在CQ扩展和文献增强完成后，对整个TBox进行一次统一的向量去重，
    确保进入P5抽取阶段的Schema是干净、无冗余的。
    
    功能：
    1. 对所有类进行向量相似度去重
    2. 对所有关系进行向量相似度去重
    3. 更新relations的domain/range引用（指向保留的类）
    4. 更新attributes的owner引用（指向保留的类）
    
    Args:
        schema: P4增强后的TBox
        class_threshold: 类去重阈值（默认0.85，越高越严格）
        relation_threshold: 关系去重阈值（默认0.80）
        save_path: 保存路径（可选）
        
    Returns:
        去重后的Master TBox
    """
    logger.info(
        f"[finalize_tbox] 开始统一去重，输入: "
        f"{len(schema.classes)}类, {len(schema.relations)}关系"
    )
    
    dedup = EmbeddingDeduplicator(threshold=class_threshold)
    
    # 1. 类去重
    all_classes = [asdict(c) for c in schema.classes]
    class_result = dedup.deduplicate_classes([], all_classes)
    accepted_classes = class_result.accepted
    accepted_class_names = {c["name"] for c in accepted_classes}
    
    # 构建类名映射（被合并的 -> 保留的）
    class_name_map = self._build_class_name_map(
        all_classes, accepted_classes, dedup
    )
    
    # 记录合并信息
    for old_name, new_name in class_name_map.items():
        if old_name != new_name:
            logger.info(f"[finalize_tbox] 类合并: {old_name} -> {new_name}")
    
    # 2. 关系去重
    dedup_rel = EmbeddingDeduplicator(threshold=relation_threshold)
    all_relations = [asdict(r) for r in schema.relations]
    rel_result = dedup_rel.deduplicate_relations([], all_relations)
    accepted_relations = rel_result.accepted
    
    # 3. 更新关系的domain/range
    updated_relations = []
    for rel in accepted_relations:
        new_domain = class_name_map.get(rel["domain"], rel["domain"])
        new_range = class_name_map.get(rel["range"], rel["range"])
        
        # 检查domain/range是否仍然有效
        if new_domain in accepted_class_names and new_range in accepted_class_names:
            rel["domain"] = new_domain
            rel["range"] = new_range
            updated_relations.append(rel)
        else:
            logger.debug(
                f"[finalize_tbox] 关系域/值域无效，移除: {rel['name']} "
                f"({rel['domain']} -> {rel['range']})"
            )
    
    # 4. 更新属性的owner
    updated_attributes = []
    for attr in schema.attributes:
        new_owner = class_name_map.get(attr.owner, attr.owner)
        if new_owner in accepted_class_names:
            updated_attributes.append(AttributeDef(
                owner=new_owner,
                name=attr.name,
                cn_name=attr.cn_name,
                value_type=attr.value_type,
            ))
    
    # 5. 构建最终TBox
    final_schema = TBoxSchema(
        classes=[ClassDef(**c) for c in accepted_classes],
        relations=[RelationDef(**r) for r in updated_relations],
        attributes=updated_attributes,
    )
    
    logger.info(
        f"[finalize_tbox] 去重完成: "
        f"类 {len(schema.classes)} -> {len(final_schema.classes)}, "
        f"关系 {len(schema.relations)} -> {len(final_schema.relations)}"
    )
    
    if save_path:
        self._dump_json(final_schema.to_dict(), save_path)
    
    return final_schema

def _build_class_name_map(
    self,
    all_classes: List[Dict],
    accepted_classes: List[Dict],
    dedup: EmbeddingDeduplicator
) -> Dict[str, str]:
    """
    构建类名映射表
    
    将被去重移除的类名映射到保留的类名。
    """
    accepted_names = {c["name"] for c in accepted_classes}
    class_name_map = {}
    
    for c in all_classes:
        name = c["name"]
        if name in accepted_names:
            # 保留的类映射到自身
            class_name_map[name] = name
        else:
            # 被移除的类找到最相似的保留类
            best_match = self._find_most_similar(name, list(accepted_names), dedup)
            class_name_map[name] = best_match
    
    return class_name_map

def _find_most_similar(
    self,
    name: str,
    candidates: List[str],
    dedup: EmbeddingDeduplicator
) -> str:
    """
    找到与给定名称最相似的候选项
    """
    if not candidates:
        return name
    
    best_score = -1
    best_match = candidates[0]
    
    for cand in candidates:
        # 使用去重器的相似度计算方法
        score = dedup.compute_similarity(name, cand)
        if score > best_score:
            best_score = score
            best_match = cand
    
    return best_match
```

#### 验证标准
- [ ] 方法可被正常调用
- [ ] 返回类型为`TBoxSchema`
- [ ] 去重后类数量 ≤ 原始类数量
- [ ] relations的domain/range均指向存在的类

---

### 任务T5：新增extract_with_verification方法

#### 目标
在`CQLLMPipeline`类中新增带校验的抽取方法，整合P5和P6。

#### 文件位置
`kg/pipelines/cq_pipeline.py`

#### 前置条件
- 任务T1完成（P5_EXTRACTION_PROMPT_COT可用）
- 任务T2完成（HallucinationFilter可用）
- 任务T3完成（SimpleEntityNormalizer可用）

#### 操作步骤

1. 在文件顶部添加新的import语句
2. 在`CQLLMPipeline`类中添加方法

#### 代码实现

**添加import（在文件顶部）**

```python
# 在现有import之后添加
from kg.extraction.hallucination_filter import HallucinationFilter
from kg.utils.entity_normalizer import SimpleEntityNormalizer
from .prompts import P5_EXTRACTION_PROMPT_COT  # 如果prompts在同级目录
```

**添加方法**

```python
# 在 CQLLMPipeline 类中添加以下方法

def extract_with_verification(
    self,
    paragraph: str,
    schema: TBoxSchema,
    context_before: str = "",
    context_after: str = "",
    save_path: Optional[Path] = None,
    strict_filter: bool = False,
    favor_existing_classes: bool = True,
) -> Dict[str, Any]:
    """
    带原文回溯校验的知识抽取（P5 + P6）
    
    整合CoT约束抽取和原文回溯校验，一步完成高质量抽取。
    
    流程：
    1. P5: 使用CoT Prompt进行分步抽取
    2. 清洗: 对抽取结果进行基础清洗
    3. P6: 原文回溯校验，过滤幻觉
    4. 标准化: 对保留的结果进行格式标准化
    
    Args:
        paragraph: 待抽取文本
        schema: Master TBox（建议使用finalize_tbox后的结果）
        context_before: 前文上下文（可选）
        context_after: 后文上下文（可选）
        save_path: 保存路径（可选）
        strict_filter: 是否使用严格过滤模式
        favor_existing_classes: 是否优先使用现有类（传递给Prompt）
        
    Returns:
        包含抽取结果和验证统计的字典：
        {
            "events": [...],
            "triples": [...],
            "filtered_triples": [...],
            "stats": {...},
            "verification_log": [...]
        }
    """
    # P5: CoT抽取
    logger.info("[P5] CoT约束抽取...")
    
    # 构建带上下文的输入
    input_text = self._format_context_input(paragraph, context_before, context_after)
    
    # 构建Prompt
    schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)
    class_hints = self._build_class_hints(schema.classes)
    
    if favor_existing_classes:
        class_usage_hint = (
            f"优先使用 TBox 中已有的类名，不要随意创造新的事件类型。{class_hints}"
        )
    else:
        class_usage_hint = (
            f"允许充分使用 TBox 中的细粒度类。{class_hints}"
        )
    
    user_prompt = P5_EXTRACTION_PROMPT_COT.format(
        schema_json=schema_json,
        event_schema=EVENT_SCHEMA_HINT,
        input_text=input_text,
        class_usage_hint=class_usage_hint,
    )
    
    # 调用LLM
    res = self.client.call("仅输出JSON，先输出思考过程。", user_prompt)
    
    # 清洗P5结果
    res = self._sanitize_p5_result(res, schema)
    
    # P6: 原文回溯校验
    logger.info("[P6] 原文回溯校验...")
    halluc_filter = HallucinationFilter(
        strict_mode=strict_filter,
        fuzzy_threshold=0.8,
        verbose=True
    )
    
    verified = halluc_filter.verify(
        extraction_result=res,
        original_text=paragraph,
        context_before=context_before,
        context_after=context_after,
    )
    
    # 实体标准化
    normalizer = SimpleEntityNormalizer()
    normalized_triples = normalizer.normalize_triples(verified.valid_triples)
    
    # 组装结果
    result = {
        "events": verified.valid_events,
        "triples": normalized_triples,
        "filtered_triples": verified.filtered_triples,
        "stats": {
            "total_triples": verified.total_triples,
            "valid_triples": verified.valid_count,
            "filtered_triples": verified.filtered_count,
            "hallucination_rate": f"{verified.hallucination_rate:.2f}%",
        },
        "verification_log": verified.verification_log,
    }
    
    if save_path:
        self._dump_json(result, save_path)
    
    logger.info(
        f"[P5+P6] 完成: 事件{len(result['events'])}个, "
        f"有效三元组{verified.valid_count}/{verified.total_triples}, "
        f"幻觉率{verified.hallucination_rate:.2f}%"
    )
    
    return result

def _format_context_input(self, main: str, before: str, after: str) -> str:
    """
    格式化带上下文标记的输入文本
    """
    parts = []
    
    if before and before.strip():
        parts.append(f"【前文参考】\n{before.strip()}")
    
    parts.append(f"【待抽取文本】\n{main.strip()}")
    
    if after and after.strip():
        parts.append(f"【后文参考】\n{after.strip()}")
    
    return "\n\n".join(parts)

def _build_class_hints(self, classes: List[ClassDef], max_show: int = 8) -> str:
    """
    构建类使用提示
    """
    # 优先显示事件类
    event_classes = [
        c for c in classes 
        if "Event" in c.name or "事件" in c.cn_name
    ]
    
    if not event_classes:
        event_classes = classes[:max_show]
    else:
        event_classes = event_classes[:max_show]
    
    hints = [f"{c.name}({c.cn_name})" for c in event_classes]
    return f"可用事件类型: {', '.join(hints)}"
```

#### 验证标准
- [ ] 方法可被正常调用
- [ ] 返回字典包含`events`、`triples`、`filtered_triples`、`stats`字段
- [ ] `stats`包含`hallucination_rate`
- [ ] 幻觉三元组被正确过滤

---

### 任务T6：编写单元测试

#### 目标
为新增模块编写单元测试，确保功能正确。

#### 文件位置
`tests/test_hallucination_filter.py`（新建）

#### 代码实现

```python
"""
幻觉过滤器单元测试
"""

import pytest
from kg.extraction.hallucination_filter import (
    HallucinationFilter,
    VerificationResult,
    filter_hallucinations,
)
from kg.utils.entity_normalizer import SimpleEntityNormalizer


class TestHallucinationFilter:
    """HallucinationFilter测试类"""
    
    @pytest.fixture
    def filter_strict(self):
        """严格模式过滤器"""
        return HallucinationFilter(strict_mode=True)
    
    @pytest.fixture
    def filter_fuzzy(self):
        """模糊匹配过滤器"""
        return HallucinationFilter(strict_mode=False, fuzzy_threshold=0.8)
    
    @pytest.fixture
    def sample_text(self):
        """示例文本"""
        return "1998年6月至9月，长江流域发生特大洪水，造成直接经济损失2000亿元。"
    
    def test_exact_match_pass(self, filter_strict, sample_text):
        """测试精确匹配通过"""
        extraction = {
            "triples": [
                {"subject": "特大洪水", "predicate": "发生地点", "object": "长江流域"}
            ]
        }
        result = filter_strict.verify(extraction, sample_text)
        
        assert result.valid_count == 1
        assert result.filtered_count == 0
        assert result.hallucination_rate == 0.0
    
    def test_exact_match_fail(self, filter_strict, sample_text):
        """测试精确匹配失败（幻觉检测）"""
        extraction = {
            "triples": [
                {"subject": "特大洪水", "predicate": "发生地点", "object": "黄河流域"}
            ]
        }
        result = filter_strict.verify(extraction, sample_text)
        
        assert result.valid_count == 0
        assert result.filtered_count == 1
        assert result.hallucination_rate == 100.0
    
    def test_fuzzy_match(self, filter_fuzzy, sample_text):
        """测试模糊匹配"""
        extraction = {
            "triples": [
                {"subject": "特大洪水", "predicate": "发生时间", "object": "1998年6月"}
            ]
        }
        result = filter_fuzzy.verify(extraction, sample_text)
        
        # "1998年6月"是"1998年6月至9月"的子串，应该通过
        assert result.valid_count == 1
    
    def test_empty_triples(self, filter_strict, sample_text):
        """测试空三元组列表"""
        extraction = {"triples": []}
        result = filter_strict.verify(extraction, sample_text)
        
        assert result.total_triples == 0
        assert result.hallucination_rate == 0.0
    
    def test_with_context(self, filter_strict):
        """测试带上下文的验证"""
        main_text = "武汉关水位达到28.77米。"
        context_before = "1998年，长江发生特大洪水。"
        
        extraction = {
            "triples": [
                {"subject": "武汉关", "predicate": "水位", "object": "28.77米"},
                {"subject": "特大洪水", "predicate": "发生于", "object": "长江"}
            ]
        }
        
        result = filter_strict.verify(
            extraction, main_text, 
            context_before=context_before
        )
        
        # 两个三元组都应该通过（实体分别在主文本和上下文中）
        assert result.valid_count == 2


class TestSimpleEntityNormalizer:
    """SimpleEntityNormalizer测试类"""
    
    @pytest.fixture
    def normalizer(self):
        return SimpleEntityNormalizer()
    
    def test_strip_whitespace(self, normalizer):
        """测试去除空白"""
        assert normalizer.normalize("  长江  ") == "长江"
        assert normalizer.normalize("\t洪水\n") == "洪水"
    
    def test_full_to_half_digits(self, normalizer):
        """测试全角转半角"""
        assert normalizer.normalize("２０２０年") == "2020年"
        assert normalizer.normalize("１９９８") == "1998"
    
    def test_normalize_triple(self, normalizer):
        """测试三元组标准化"""
        triple = {
            "subject": "  长江  ",
            "predicate": "has_flood",
            "object": "２０２０年洪水"
        }
        result = normalizer.normalize_triple(triple)
        
        assert result["subject"] == "长江"
        assert result["predicate"] == "has_flood"  # predicate不变
        assert result["object"] == "2020年洪水"


class TestFilterHallucinationsFunction:
    """filter_hallucinations便捷函数测试"""
    
    def test_basic_usage(self):
        """测试基本使用"""
        extraction = {
            "events": [{"name": "1998年洪水"}],
            "triples": [
                {"subject": "洪水", "predicate": "发生于", "object": "长江"},
                {"subject": "洪水", "predicate": "发生于", "object": "不存在的河流"}
            ]
        }
        text = "1998年长江发生洪水。"
        
        result = filter_hallucinations(extraction, text)
        
        assert len(result["events"]) == 1
        assert len(result["triples"]) == 1
        assert len(result["filtered_triples"]) == 1
        assert "hallucination_rate" in result["stats"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
```

#### 验证标准
- [ ] 所有测试用例通过
- [ ] 运行`pytest tests/test_hallucination_filter.py -v`无错误

---

## 五、集成验证

### 5.1 完整流程测试

完成所有任务后，运行以下测试代码验证集成：

```python
# tests/test_integration.py

from pathlib import Path
from kg.pipelines.cq_pipeline import CQLLMPipeline

def test_full_pipeline():
    """完整流程集成测试"""
    
    # 初始化Pipeline
    pipeline = CQLLMPipeline()
    
    # 测试文本
    test_text = """
    1998年，受流域范围内持续性强降雨和上游来水偏多影响，
    长江中下游干流水位长期高于警戒，洞庭湖、鄱阳湖来水显著增加，
    导致两湖与干流洪水叠加。长江流域发生特大洪水过程，
    造成全国受灾人口2.23亿人，直接经济损失约1660亿元。
    """
    
    # 假设已有schema
    from kg.pipelines.cq_pipeline import TBoxSchema, ClassDef, RelationDef
    
    schema = TBoxSchema(
        classes=[
            ClassDef(name="FloodEvent", cn_name="洪水事件", 
                    definition="洪水灾害事件", examples=["1998年洪水"]),
        ],
        relations=[
            RelationDef(name="has_cause", cn_name="致灾因子",
                       domain="FloodEvent", range="HazardFactor",
                       definition="导致灾害的因素", functional=False),
        ],
        attributes=[]
    )
    
    # 执行带校验的抽取
    result = pipeline.extract_with_verification(
        paragraph=test_text,
        schema=schema,
        strict_filter=False
    )
    
    # 验证结果结构
    assert "events" in result
    assert "triples" in result
    assert "stats" in result
    assert "hallucination_rate" in result["stats"]
    
    print(f"抽取事件: {len(result['events'])}个")
    print(f"有效三元组: {result['stats']['valid_triples']}条")
    print(f"幻觉率: {result['stats']['hallucination_rate']}")
    
    return result


if __name__ == "__main__":
    result = test_full_pipeline()
    print("\n集成测试通过!")
```

### 5.2 验证清单

- [ ] T1: P5_EXTRACTION_PROMPT_COT可正常使用
- [ ] T2: HallucinationFilter可正常过滤幻觉
- [ ] T3: SimpleEntityNormalizer可正常标准化实体
- [ ] T4: finalize_tbox可正常去重TBox
- [ ] T5: extract_with_verification可正常执行完整流程
- [ ] T6: 所有单元测试通过
- [ ] 集成测试通过

---

## 六、注意事项

### 6.1 代码规范

1. **类型注解**：所有函数参数和返回值必须有类型注解
2. **文档字符串**：所有类和公共方法必须有docstring
3. **日志记录**：关键步骤使用`logger.info()`记录
4. **错误处理**：对可能失败的操作添加try-except

### 6.2 常见问题处理

| 问题           | 解决方案                                        |
| -------------- | ----------------------------------------------- |
| Import错误     | 检查文件路径和`__init__.py`                     |
| JSON解析失败   | 使用现有的`_safe_load`方法                      |
| 过滤过于严格   | 将`strict_mode`设为False，降低`fuzzy_threshold` |
| 去重阈值不合适 | 类阈值建议0.85，关系阈值建议0.80                |

### 6.3 性能考虑

1. **批量处理**：如需处理大量文本，建议实现批量版本的`extract_with_verification`
2. **缓存Embedding**：`EmbeddingDeduplicator`应复用，避免重复加载模型
3. **日志级别**：生产环境将verbose设为False，减少日志输出

---

## 七、完成标志

当以下条件全部满足时，视为改进完成：

1. ✅ 所有6个任务代码已添加
2. ✅ 无语法错误，项目可正常运行
3. ✅ 单元测试全部通过
4. ✅ 集成测试通过
5. ✅ 对示例文本的幻觉率 < 20%

---

*文档版本: v1.0*
*适用于: Claude Code / Cursor / Copilot 等AI编码助手*