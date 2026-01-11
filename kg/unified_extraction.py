"""
统一抽取流程模块。
Gold 和 Pred 使用相同的 Prompt、后处理逻辑和参数配置。
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from kg.prompts import UNIFIED_EXTRACTION_PROMPT
from kg.cq_pipeline import format_schema_for_prompt
from kg.hallucination_filter import HallucinationFilter
from kg.entity_fusion import SimpleEntityNormalizer


logger = logging.getLogger(__name__)


@dataclass
class ExtractionConfig:
    """统一的抽取配置"""
    fuzzy_threshold: float = 0.8      # 幻觉过滤阈值（统一）
    strict_mode: bool = False          # 严格模式（统一为 False）
    use_cot: bool = True               # 使用 CoT
    schema_style: str = "markdown"     # Schema 格式化风格
    enable_direction_fix: bool = True  # 启用方向修正


@dataclass
class ExtractionResult:
    """抽取结果"""
    events: List[Dict[str, Any]] = field(default_factory=list)
    triples: List[Dict[str, Any]] = field(default_factory=list)
    entities: List[Dict[str, Any]] = field(default_factory=list)
    filtered_triples: List[Dict[str, Any]] = field(default_factory=list)
    thought: str = ""
    stats: Dict[str, Any] = field(default_factory=dict)
    parse_error: bool = False


class DirectionNormalizer:
    """三元组方向修正器"""

    def __init__(self, tbox: Dict[str, Any]):
        self.tbox = tbox
        self.relation_signatures = self._build_signatures()

    @staticmethod
    def _normalize_types(value: Any) -> List[str]:
        if isinstance(value, (list, tuple, set)):
            return [str(v).strip().lower() for v in value if str(v).strip()]
        if value is None:
            return []
        text = str(value).strip()
        return [text.lower()] if text else []

    def _build_signatures(self) -> Dict[str, Tuple[List[str], List[str]]]:
        """构建关系签名映射：relation_name -> (domain_list, range_list)"""
        signatures = {}
        for rel in self.tbox.get("relations", []):
            name = rel.get("name", "").lower()
            domain = self._normalize_types(rel.get("domain"))
            range_ = self._normalize_types(rel.get("range"))
            if name:
                signatures[name] = (domain, range_)
        return signatures

    def _get_entity_type(self, entity_name: str, entities: List[Dict], events: List[Dict]) -> Optional[str]:
        """推断实体类型"""
        entity_name_lower = entity_name.lower().strip()

        # 从 entities 查找
        for e in entities:
            if e.get("name", "").lower().strip() == entity_name_lower:
                return e.get("type", "").lower()

        # 从 events 查找
        for ev in events:
            if ev.get("name", "").lower().strip() == entity_name_lower:
                return ev.get("event_type", "").lower()

        return None

    def fix_directions(
        self,
        triples: List[Dict[str, Any]],
        entities: List[Dict[str, Any]] = None,
        events: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        修正三元组方向。
        如果检测到主宾语类型与 Schema 定义相反，则交换主宾语。
        """
        entities = entities or []
        events = events or []
        fixed_triples = []

        for triple in triples:
            subject = triple.get("subject", "")
            predicate = triple.get("predicate", "").lower()
            obj = triple.get("object", "")

            if predicate not in self.relation_signatures:
                fixed_triples.append(triple)
                continue

            expected_domain, expected_range = self.relation_signatures[predicate]

            # 推断实际类型
            subject_type = self._get_entity_type(subject, entities, events)
            object_type = self._get_entity_type(obj, entities, events)

            # 检查是否需要交换
            need_swap = False
            if subject_type and object_type:
                # 如果主语类型匹配 range 且宾语类型匹配 domain，则需要交换
                if subject_type in expected_range and object_type in expected_domain:
                    need_swap = True

            if need_swap:
                fixed_triple = dict(triple)
                fixed_triple["subject"] = obj
                fixed_triple["object"] = subject
                fixed_triple["_direction_fixed"] = True
                fixed_triples.append(fixed_triple)
                logger.debug(f"方向修正: ({subject}, {predicate}, {obj}) -> ({obj}, {predicate}, {subject})")
            else:
                fixed_triples.append(triple)

        return fixed_triples


class UnifiedExtractionPipeline:
    """统一的抽取后处理流程"""

    def __init__(
        self,
        tbox: Dict[str, Any],
        config: ExtractionConfig = None,
    ):
        self.tbox = tbox
        self.config = config or ExtractionConfig()

        self.halluc_filter = HallucinationFilter(
            strict_mode=self.config.strict_mode,
            fuzzy_threshold=self.config.fuzzy_threshold,
        )
        self.direction_fixer = DirectionNormalizer(tbox)
        self.entity_normalizer = SimpleEntityNormalizer()

    def build_prompt(self, source_text: str) -> str:
        """构建统一的抽取 Prompt"""
        schema_text = format_schema_for_prompt(self.tbox, style=self.config.schema_style)
        return UNIFIED_EXTRACTION_PROMPT.format(
            schema_text=schema_text,
            input_text=source_text,
        )

    def parse_response(self, raw_response: str) -> Tuple[Dict[str, Any], str]:
        """解析 LLM 响应"""
        thought = ""
        result = {"entities": [], "events": [], "triples": []}

        # 提取思考过程
        if "【思考过程】" in raw_response:
            parts = raw_response.split("```json")
            if len(parts) >= 2:
                thought = parts[0].replace("【思考过程】", "").strip()

        # 提取 JSON
        json_match = re.search(r"```json\s*([\s\S]*?)\s*```", raw_response)
        if json_match:
            try:
                result = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                logger.warning("JSON 解析失败")
        else:
            # 尝试直接解析
            try:
                # 查找第一个 { 和最后一个 }
                start = raw_response.find("{")
                end = raw_response.rfind("}") + 1
                if start >= 0 and end > start:
                    result = json.loads(raw_response[start:end])
            except json.JSONDecodeError:
                logger.warning("无法解析响应中的 JSON")

        return result, thought

    def process(self, raw_result: Dict[str, Any], source_text: str) -> ExtractionResult:
        """统一后处理流程"""

        original_triples = raw_result.get("triples", [])
        entities = raw_result.get("entities", [])
        events = raw_result.get("events", [])

        # Step 1: 幻觉过滤
        verified = self.halluc_filter.verify(raw_result, source_text)

        # Step 2: 方向修正
        if self.config.enable_direction_fix:
            fixed_triples = self.direction_fixer.fix_directions(
                verified.valid_triples,
                entities=entities,
                events=verified.valid_events
            )
        else:
            fixed_triples = verified.valid_triples

        # Step 3: 实体归一化
        normalized_triples = self.entity_normalizer.normalize_triples(fixed_triples)

        # Step 4: TBox 约束验证
        valid_triples = self._validate_tbox(normalized_triples)

        return ExtractionResult(
            events=verified.valid_events,
            triples=valid_triples,
            entities=entities,
            filtered_triples=verified.filtered_triples,
            thought=raw_result.get("_thinking", ""),
            stats={
                "original": len(original_triples),
                "after_halluc_filter": len(verified.valid_triples),
                "after_direction_fix": len(fixed_triples),
                "final": len(valid_triples),
                "direction_fixed_count": sum(1 for t in fixed_triples if t.get("_direction_fixed")),
            },
            parse_error=False,
        )

    def _validate_tbox(self, triples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """验证三元组是否符合 TBox 约束"""
        valid_predicates = {
            rel.get("name", "").lower()
            for rel in self.tbox.get("relations", [])
        }

        valid_triples = []
        for triple in triples:
            predicate = triple.get("predicate", "").lower()
            if predicate in valid_predicates:
                valid_triples.append(triple)
            else:
                logger.debug(f"过滤未知谓词: {predicate}")

        return valid_triples


def create_unified_pipeline(tbox_path: str, **kwargs) -> UnifiedExtractionPipeline:
    """工厂函数：创建统一抽取流程"""
    from pathlib import Path
    tbox = json.loads(Path(tbox_path).read_text(encoding="utf-8"))
    config = ExtractionConfig(**kwargs)
    return UnifiedExtractionPipeline(tbox, config)
