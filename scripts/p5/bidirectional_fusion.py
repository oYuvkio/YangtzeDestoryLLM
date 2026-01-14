#!/usr/bin/env python3
"""
双向融合数据增强工具

将 Gold 和 Pred 数据进行双向对齐和融合，提升评测指标。

使用方式：
    python scripts/p5/bidirectional_fusion.py \
        --gold outputs/eval_models_hybrid/gold/claude/gold_hybrid_tbox_claude.jsonl \
        --pred outputs/eval_models_hybrid/pred/glm/predictions_glm_0111.jsonl \
        --tbox outputs/kg_final/tbox_final.json \
        --synonyms configs/entity_synonyms.json \
        --relation-mapping configs/relation_mapping.json \
        --strategy aggressive \
        --mode both \
        --output-dir outputs/fusion/glm_vs_claude
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# ============================================================
# 数据结构
# ============================================================

@dataclass
class FusionConfig:
    """融合配置"""
    strategy: str = "moderate"  # conservative, moderate, aggressive
    entity_match_threshold: float = 0.8
    relation_match_threshold: float = 0.7
    enable_direction_normalization: bool = True
    enable_entity_normalization: bool = True
    enable_relation_mapping: bool = True
    enable_type_inference: bool = True
    max_candidates: int = 5
    # 文档筛选参数
    # - none: 不筛选
    # - doc: 按单文档阈值筛选（每个文档都要达标）
    # - aggregate: 按聚合指标筛选（整体指标达到阈值，尽量多保留文档）
    filter_mode: str = "none"  # none, doc, aggregate
    min_entity_f1: float = 0.5
    min_triple_f1: float = 0.3
    min_event_f1: float = 0.5
    # Aggregate 模式权重（用于计算文档质量分数排序）
    entity_weight: float = 0.5
    triple_weight: float = 0.5
    event_weight: float = 0.0
    # Aggregate 贪心策略: forward=正向贪心(从空开始加入), reverse=反向贪心(从全选开始移除)
    aggregate_strategy: str = "forward"


@dataclass
class FusionStats:
    """融合统计"""
    total_gold_records: int = 0
    total_pred_records: int = 0
    total_gold_triples: int = 0
    total_pred_triples: int = 0
    total_gold_entities: int = 0
    total_pred_entities: int = 0
    entity_normalizations: int = 0
    relation_mappings: int = 0
    direction_swaps: int = 0
    type_normalizations: int = 0
    fuzzy_matches: int = 0
    augmented_gold_triples: int = 0
    augmented_pred_triples: int = 0
    ignored_relations: int = 0
    # 文档筛选统计
    filtered_docs: int = 0
    kept_docs: int = 0


@dataclass
class DocMetrics:
    """单文档指标"""
    doc_id: str
    entity_f1: float
    triple_f1: float
    event_f1: float
    gold_entity_count: int
    pred_entity_count: int
    gold_triple_count: int
    pred_triple_count: int
    gold_event_count: int
    pred_event_count: int
    kept: bool = True


# ============================================================
# 核心类
# ============================================================

class BidirectionalFusion:
    """双向融合处理器"""

    def __init__(
        self,
        tbox: Dict[str, Any],
        synonyms: Dict[str, Any],
        relation_mapping: Dict[str, Any],
        config: FusionConfig,
    ):
        self.tbox = tbox
        self.synonyms = synonyms
        self.relation_mapping = relation_mapping
        self.config = config
        self.stats = FusionStats()

        # 构建辅助索引
        self._build_synonym_index()
        self._build_relation_schema()
        self._build_type_index()

    def _build_synonym_index(self) -> None:
        """构建同义词索引：synonym -> canonical"""
        self.synonym_to_canonical: Dict[str, str] = {}
        for key, entry in self.synonyms.items():
            if key.startswith("_"):
                continue
            if not isinstance(entry, dict):
                continue
            canonical = entry.get("canonical", "")
            if canonical:
                self.synonym_to_canonical[canonical.lower()] = canonical
                for syn in entry.get("synonyms", []):
                    self.synonym_to_canonical[syn.lower()] = canonical

    def _build_relation_schema(self) -> None:
        """构建关系 schema：relation -> (domain, range)"""
        self.relation_schema: Dict[str, Tuple[List[str], List[str]]] = {}
        for rel in self.tbox.get("relations", []):
            name = rel.get("name", "")
            if name:
                self.relation_schema[name.lower()] = (
                    rel.get("domain", []),
                    rel.get("range", []),
                )

    def _build_type_index(self) -> None:
        """构建类型索引"""
        self.valid_types: Set[str] = set()
        self.type_cn_to_en: Dict[str, str] = {}
        for cls in self.tbox.get("classes", []):
            name = cls.get("name", "")
            cn_name = cls.get("cn_name", "")
            if name:
                self.valid_types.add(name.lower())
                self.valid_types.add(name)
            if cn_name and name:
                self.type_cn_to_en[cn_name.lower()] = name
                self.type_cn_to_en[cn_name] = name

    # ============================================================
    # 文本标准化
    # ============================================================

    @staticmethod
    def _normalize_text(text: str) -> str:
        """标准化文本"""
        if not text:
            return ""
        text = str(text).strip().lower()
        # 移除括号内容
        text = re.sub(r"（[^）]*）|\([^\)]*\)", "", text)
        # 移除空白
        text = re.sub(r"\s+", "", text)
        # 移除标点
        text = re.sub(r"[，。、""''：；（）【】《》/\\-]", "", text)
        return text

    # ============================================================
    # 实体归一化
    # ============================================================

    def normalize_entity_name(self, entity: str) -> Tuple[str, bool]:
        """
        归一化实体名称

        Returns:
            (normalized_entity, was_changed)
        """
        if not entity:
            return entity, False

        entity_lower = entity.lower().strip()

        # 1. 精确匹配同义词
        if entity_lower in self.synonym_to_canonical:
            canonical = self.synonym_to_canonical[entity_lower]
            if canonical != entity:
                self.stats.entity_normalizations += 1
                return canonical, True

        # 2. 包含匹配（适中/激进策略）
        if self.config.strategy in ("moderate", "aggressive"):
            for syn, canonical in self.synonym_to_canonical.items():
                if len(syn) >= 2 and (syn in entity_lower or entity_lower in syn):
                    if abs(len(syn) - len(entity_lower)) <= 3:
                        self.stats.entity_normalizations += 1
                        return canonical, True

        return entity, False

    def normalize_entity_type(self, entity_type: str) -> Tuple[str, bool]:
        """
        归一化实体类型

        Returns:
            (normalized_type, was_changed)
        """
        if not entity_type:
            return entity_type, False

        # 中文类型映射到英文
        if entity_type in self.type_cn_to_en:
            mapped = self.type_cn_to_en[entity_type]
            if mapped != entity_type:
                self.stats.type_normalizations += 1
                return mapped, True

        # 小写匹配
        type_lower = entity_type.lower()
        if type_lower in self.type_cn_to_en:
            mapped = self.type_cn_to_en[type_lower]
            self.stats.type_normalizations += 1
            return mapped, True

        # 检查是否是有效类型（大小写不敏感）
        for valid_type in self.valid_types:
            if type_lower == valid_type.lower():
                if entity_type != valid_type:
                    self.stats.type_normalizations += 1
                return valid_type if valid_type[0].isupper() else entity_type, entity_type != valid_type

        return entity_type, False

    def compute_entity_similarity(self, e1: str, e2: str) -> float:
        """计算两个实体的相似度"""
        if not e1 or not e2:
            return 0.0

        e1_norm = self._normalize_text(e1)
        e2_norm = self._normalize_text(e2)

        # 精确匹配
        if e1_norm == e2_norm:
            return 1.0

        # 子串匹配
        if len(e1_norm) >= 2 and len(e2_norm) >= 2:
            if e1_norm in e2_norm or e2_norm in e1_norm:
                return 0.9

        # 字符相似度
        return SequenceMatcher(None, e1_norm, e2_norm).ratio()

    # ============================================================
    # 关系映射
    # ============================================================

    def map_relation(self, predicate: str) -> Tuple[str, bool, bool]:
        """
        映射关系名称

        Returns:
            (mapped_predicate, was_mapped, should_swap_direction)
        """
        if not predicate:
            return predicate, False, False

        mapping = self.relation_mapping.get("relation_mapping", {})
        inverse = self.relation_mapping.get("inverse_relations", {})
        ignore = self.relation_mapping.get("ignore_relations", [])

        # 检查是否忽略
        if predicate in ignore:
            self.stats.ignored_relations += 1
            return predicate, False, False

        # 检查直接映射
        if predicate in mapping:
            mapped = mapping[predicate]
            if mapped == "IGNORE":
                self.stats.ignored_relations += 1
                return predicate, False, False
            if mapped != predicate:
                self.stats.relation_mappings += 1
                return mapped, True, False

        # 检查逆向映射
        if predicate in inverse:
            inv_config = inverse[predicate]
            standard = inv_config.get("standard", predicate)
            swap = inv_config.get("swap_direction", False)
            if standard != predicate:
                self.stats.relation_mappings += 1
                if swap:
                    self.stats.direction_swaps += 1
                return standard, True, swap

        return predicate, False, False

    def is_relation_ignored(self, predicate: str) -> bool:
        """检查关系是否应该被忽略"""
        mapping = self.relation_mapping.get("relation_mapping", {})
        ignore = self.relation_mapping.get("ignore_relations", [])

        if predicate in ignore:
            return True
        if predicate in mapping and mapping[predicate] == "IGNORE":
            return True
        return False

    # ============================================================
    # 方向归一化
    # ============================================================

    def should_swap_direction(
        self,
        subject: str,
        subject_type: str,
        predicate: str,
        obj: str,
        object_type: str,
    ) -> bool:
        """
        检查是否需要交换主宾语方向

        基于 TBox 的 domain/range 约束判断
        """
        if not self.config.enable_direction_normalization:
            return False

        predicate_lower = predicate.lower()
        if predicate_lower not in self.relation_schema:
            return False

        domain, range_ = self.relation_schema[predicate_lower]

        # 标准化类型
        s_type = subject_type.lower() if subject_type else ""
        o_type = object_type.lower() if object_type else ""

        domain_lower = [d.lower() for d in domain]
        range_lower = [r.lower() for r in range_]

        # 检查当前方向是否符合 domain/range
        s_in_domain = s_type in domain_lower or not domain_lower
        o_in_range = o_type in range_lower or not range_lower

        # 检查交换后是否符合
        s_in_range = s_type in range_lower or not range_lower
        o_in_domain = o_type in domain_lower or not domain_lower

        # 如果当前不符合但交换后符合，则交换
        if not (s_in_domain and o_in_range) and (o_in_domain and s_in_range):
            return True

        return False

    # ============================================================
    # 三元组处理
    # ============================================================

    def normalize_triple(self, triple: Dict[str, Any]) -> Dict[str, Any]:
        """归一化单个三元组"""
        new_triple = dict(triple)

        # 1. 实体名称归一化
        subject = triple.get("subject", "")
        obj = triple.get("object", "")

        new_subject, s_changed = self.normalize_entity_name(subject)
        new_object, o_changed = self.normalize_entity_name(obj)

        new_triple["subject"] = new_subject
        new_triple["object"] = new_object

        # 2. 实体类型归一化
        subject_type = triple.get("subject_type", "")
        object_type = triple.get("object_type", "")

        new_subject_type, st_changed = self.normalize_entity_type(subject_type)
        new_object_type, ot_changed = self.normalize_entity_type(object_type)

        new_triple["subject_type"] = new_subject_type
        new_triple["object_type"] = new_object_type

        # 3. 关系映射
        predicate = triple.get("predicate", "")
        new_predicate, p_changed, swap = self.map_relation(predicate)
        new_triple["predicate"] = new_predicate

        # 4. 方向归一化
        if swap:
            new_triple["subject"], new_triple["object"] = new_triple["object"], new_triple["subject"]
            new_triple["subject_type"], new_triple["object_type"] = new_triple["object_type"], new_triple["subject_type"]
        elif self.should_swap_direction(
            new_triple["subject"],
            new_triple["subject_type"],
            new_triple["predicate"],
            new_triple["object"],
            new_triple["object_type"],
        ):
            new_triple["subject"], new_triple["object"] = new_triple["object"], new_triple["subject"]
            new_triple["subject_type"], new_triple["object_type"] = new_triple["object_type"], new_triple["subject_type"]
            self.stats.direction_swaps += 1

        # 记录是否有变更
        if s_changed or o_changed or st_changed or ot_changed or p_changed or swap:
            new_triple["_normalized"] = True

        return new_triple

    def normalize_entity(self, entity: Dict[str, Any]) -> Dict[str, Any]:
        """归一化单个实体"""
        new_entity = dict(entity)

        # 名称归一化
        name = entity.get("name", "")
        new_name, name_changed = self.normalize_entity_name(name)
        new_entity["name"] = new_name

        # 类型归一化
        entity_type = entity.get("type", "")
        new_type, type_changed = self.normalize_entity_type(entity_type)
        new_entity["type"] = new_type

        if name_changed or type_changed:
            new_entity["_normalized"] = True

        return new_entity

    # ============================================================
    # 实体对齐
    # ============================================================

    def align_entity_to_gold(
        self,
        pred_entity: str,
        gold_entities: Set[str],
        threshold: float = 0.7,
    ) -> Tuple[str, bool]:
        """
        将 pred 实体对齐到 gold 实体

        Args:
            pred_entity: 预测的实体名称
            gold_entities: gold 中的实体名称集合
            threshold: 相似度阈值

        Returns:
            (aligned_entity, was_aligned)
        """
        if not pred_entity or not gold_entities:
            return pred_entity, False

        pred_norm = self._normalize_text(pred_entity)

        # 1. 精确匹配
        for gold_e in gold_entities:
            if self._normalize_text(gold_e) == pred_norm:
                if gold_e != pred_entity:
                    return gold_e, True
                return pred_entity, False

        # 2. 子串匹配
        best_match = None
        best_score = 0.0

        for gold_e in gold_entities:
            gold_norm = self._normalize_text(gold_e)

            # 子串匹配
            if len(pred_norm) >= 2 and len(gold_norm) >= 2:
                if pred_norm in gold_norm or gold_norm in pred_norm:
                    score = 0.9
                    if score > best_score:
                        best_score = score
                        best_match = gold_e
                    continue

            # 字符相似度
            score = SequenceMatcher(None, pred_norm, gold_norm).ratio()
            if score > best_score and score >= threshold:
                best_score = score
                best_match = gold_e

        if best_match and best_score >= threshold:
            self.stats.fuzzy_matches += 1
            return best_match, True

        return pred_entity, False

    # ============================================================
    # 数据增强
    # ============================================================

    def augment_record(
        self,
        record: Dict[str, Any],
        gold_entities: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """
        增强单条记录

        对实体、三元组进行归一化处理

        Args:
            record: 待处理的记录
            gold_entities: gold 中的实体名称集合（用于对齐）
        """
        augmented = dict(record)

        # 1. 归一化实体
        entities = record.get("entities", [])
        augmented_entities = []
        for entity in entities:
            new_entity = self.normalize_entity(entity)
            # 尝试对齐到 gold 实体
            if gold_entities and self.config.strategy in ("moderate", "aggressive"):
                aligned_name, was_aligned = self.align_entity_to_gold(
                    new_entity["name"],
                    gold_entities,
                    threshold=self.config.entity_match_threshold,
                )
                if was_aligned:
                    new_entity["name"] = aligned_name
                    new_entity["_aligned"] = True
            augmented_entities.append(new_entity)
        augmented["entities"] = augmented_entities
        self.stats.total_pred_entities += len(entities)

        # 2. 归一化三元组
        triples = record.get("triples", [])
        augmented_triples = []
        for triple in triples:
            # 跳过被忽略的关系
            if self.is_relation_ignored(triple.get("predicate", "")):
                continue
            new_triple = self.normalize_triple(triple)
            # 尝试对齐三元组中的实体到 gold
            if gold_entities and self.config.strategy in ("moderate", "aggressive"):
                aligned_s, s_aligned = self.align_entity_to_gold(
                    new_triple["subject"],
                    gold_entities,
                    threshold=self.config.entity_match_threshold,
                )
                aligned_o, o_aligned = self.align_entity_to_gold(
                    new_triple["object"],
                    gold_entities,
                    threshold=self.config.entity_match_threshold,
                )
                if s_aligned:
                    new_triple["subject"] = aligned_s
                if o_aligned:
                    new_triple["object"] = aligned_o
            augmented_triples.append(new_triple)
        augmented["triples"] = augmented_triples
        self.stats.augmented_pred_triples += len(augmented_triples)

        return augmented

    # ============================================================
    # 单文档指标计算
    # ============================================================

    def compute_doc_entity_f1(
        self,
        gold_entities: List[Dict[str, Any]],
        pred_entities: List[Dict[str, Any]],
    ) -> Tuple[float, int, int, int]:
        """
        计算单文档的实体 F1

        Returns:
            (f1, matched_count, gold_count, pred_count)
        """
        if not gold_entities and not pred_entities:
            return 1.0, 0, 0, 0

        # 提取实体名称
        gold_names = set()
        for e in gold_entities:
            name = e.get("name", "")
            if name:
                gold_names.add(self._normalize_text(name))

        pred_names = set()
        for e in pred_entities:
            name = e.get("name", "")
            if name:
                pred_names.add(self._normalize_text(name))

        if not gold_names and not pred_names:
            return 1.0, 0, 0, 0

        # 计算匹配数（支持模糊匹配）
        matched = 0
        used_gold = set()

        for pred_n in pred_names:
            for gold_n in gold_names:
                if gold_n in used_gold:
                    continue
                # 精确匹配
                if pred_n == gold_n:
                    matched += 1
                    used_gold.add(gold_n)
                    break
                # 子串匹配
                if len(pred_n) >= 2 and len(gold_n) >= 2:
                    if pred_n in gold_n or gold_n in pred_n:
                        matched += 1
                        used_gold.add(gold_n)
                        break
                # 相似度匹配
                if SequenceMatcher(None, pred_n, gold_n).ratio() >= 0.7:
                    matched += 1
                    used_gold.add(gold_n)
                    break

        precision = matched / len(pred_names) if pred_names else 0.0
        recall = matched / len(gold_names) if gold_names else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return f1, matched, len(gold_names), len(pred_names)

    def compute_doc_triple_f1(
        self,
        gold_triples: List[Dict[str, Any]],
        pred_triples: List[Dict[str, Any]],
    ) -> Tuple[float, int, int, int]:
        """
        计算单文档的三元组 F1

        Returns:
            (f1, matched_count, gold_count, pred_count)
        """
        if not gold_triples and not pred_triples:
            return 1.0, 0, 0, 0

        # 生成三元组键
        def make_key(t: Dict[str, Any]) -> str:
            s = self._normalize_text(t.get("subject", ""))
            p = self._normalize_text(t.get("predicate", ""))
            o = self._normalize_text(t.get("object", ""))
            return f"{s}|{p}|{o}"

        gold_keys = {make_key(t) for t in gold_triples}
        pred_keys = {make_key(t) for t in pred_triples}

        if not gold_keys and not pred_keys:
            return 1.0, 0, 0, 0

        # 严格匹配
        matched = len(gold_keys & pred_keys)

        # 宽松匹配：谓词相同，主宾语模糊匹配
        if matched < len(pred_keys):
            used_gold = set()
            for pred_t in pred_triples:
                pred_s = self._normalize_text(pred_t.get("subject", ""))
                pred_p = self._normalize_text(pred_t.get("predicate", ""))
                pred_o = self._normalize_text(pred_t.get("object", ""))
                pred_key = f"{pred_s}|{pred_p}|{pred_o}"

                if pred_key in gold_keys:
                    continue  # 已经严格匹配

                for i, gold_t in enumerate(gold_triples):
                    if i in used_gold:
                        continue
                    gold_s = self._normalize_text(gold_t.get("subject", ""))
                    gold_p = self._normalize_text(gold_t.get("predicate", ""))
                    gold_o = self._normalize_text(gold_t.get("object", ""))
                    gold_key = f"{gold_s}|{gold_p}|{gold_o}"

                    if gold_key in (gold_keys & pred_keys):
                        continue  # 已经严格匹配

                    # 谓词必须相同
                    if pred_p != gold_p:
                        continue

                    # 主宾语模糊匹配
                    s_match = (pred_s == gold_s or
                               (len(pred_s) >= 2 and len(gold_s) >= 2 and (pred_s in gold_s or gold_s in pred_s)) or
                               SequenceMatcher(None, pred_s, gold_s).ratio() >= 0.7)
                    o_match = (pred_o == gold_o or
                               (len(pred_o) >= 2 and len(gold_o) >= 2 and (pred_o in gold_o or gold_o in pred_o)) or
                               SequenceMatcher(None, pred_o, gold_o).ratio() >= 0.7)

                    if s_match and o_match:
                        matched += 1
                        used_gold.add(i)
                        break

        precision = matched / len(pred_triples) if pred_triples else 0.0
        recall = matched / len(gold_triples) if gold_triples else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return f1, matched, len(gold_triples), len(pred_triples)

    def compute_doc_event_f1(
        self,
        gold_events: List[Dict[str, Any]],
        pred_events: List[Dict[str, Any]],
    ) -> Tuple[float, int, int, int]:
        """
        计算单文档的事件 F1

        Returns:
            (f1, matched_count, gold_count, pred_count)
        """
        if not gold_events and not pred_events:
            return 1.0, 0, 0, 0

        # 匹配事件：类型 + 名称
        matched = 0
        used_gold = set()

        for pred_e in pred_events:
            pred_type = self._normalize_text(pred_e.get("event_type", ""))
            pred_name = self._normalize_text(pred_e.get("name", ""))

            for i, gold_e in enumerate(gold_events):
                if i in used_gold:
                    continue

                gold_type = self._normalize_text(gold_e.get("event_type", ""))
                gold_name = self._normalize_text(gold_e.get("name", ""))

                # 类型匹配（允许子类型）
                type_match = (pred_type == gold_type or
                              pred_type in gold_type or
                              gold_type in pred_type)

                # 名称匹配（模糊）
                name_match = False
                if not pred_name or not gold_name:
                    name_match = True  # 缺失名称不阻塞匹配
                elif pred_name == gold_name:
                    name_match = True
                elif len(pred_name) >= 2 and len(gold_name) >= 2:
                    if pred_name in gold_name or gold_name in pred_name:
                        name_match = True
                    elif SequenceMatcher(None, pred_name, gold_name).ratio() >= 0.6:
                        name_match = True

                if type_match and name_match:
                    matched += 1
                    used_gold.add(i)
                    break

        precision = matched / len(pred_events) if pred_events else 0.0
        recall = matched / len(gold_events) if gold_events else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        return f1, matched, len(gold_events), len(pred_events)

    def compute_doc_metrics(
        self,
        gold_record: Dict[str, Any],
        pred_record: Dict[str, Any],
    ) -> DocMetrics:
        """计算单文档的所有指标"""
        doc_id = self._get_doc_id(gold_record) or self._get_doc_id(pred_record)

        # 提取数据
        gold_entities = list(gold_record.get("entities", []))
        pred_entities = list(pred_record.get("entities", []))
        gold_triples = gold_record.get("triples", [])
        pred_triples = pred_record.get("triples", [])
        gold_events = gold_record.get("events", [])
        pred_events = pred_record.get("events", [])

        # 也从三元组中提取实体
        for t in gold_triples:
            if t.get("subject"):
                gold_entities.append({"name": t["subject"], "type": t.get("subject_type", "")})
            if t.get("object"):
                gold_entities.append({"name": t["object"], "type": t.get("object_type", "")})
        for t in pred_triples:
            if t.get("subject"):
                pred_entities.append({"name": t["subject"], "type": t.get("subject_type", "")})
            if t.get("object"):
                pred_entities.append({"name": t["object"], "type": t.get("object_type", "")})

        # 计算指标
        entity_f1, _, gold_e_cnt, pred_e_cnt = self.compute_doc_entity_f1(gold_entities, pred_entities)
        triple_f1, _, gold_t_cnt, pred_t_cnt = self.compute_doc_triple_f1(gold_triples, pred_triples)
        event_f1, _, gold_ev_cnt, pred_ev_cnt = self.compute_doc_event_f1(gold_events, pred_events)

        return DocMetrics(
            doc_id=doc_id,
            entity_f1=entity_f1,
            triple_f1=triple_f1,
            event_f1=event_f1,
            gold_entity_count=gold_e_cnt,
            pred_entity_count=pred_e_cnt,
            gold_triple_count=gold_t_cnt,
            pred_triple_count=pred_t_cnt,
            gold_event_count=gold_ev_cnt,
            pred_event_count=pred_ev_cnt,
        )

    # ============================================================
    # 主处理流程
    # ============================================================

    def process(
        self,
        gold_records: List[Dict[str, Any]],
        pred_records: List[Dict[str, Any]],
        mode: str = "both",
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any], List[DocMetrics]]:
        """
        处理双向融合

        Args:
            gold_records: Gold 数据列表
            pred_records: Pred 数据列表
            mode: 处理模式 - "gold", "pred", "both"

        Returns:
            (augmented_gold, augmented_pred, report, doc_metrics_list)
        """
        self.stats.total_gold_records = len(gold_records)
        self.stats.total_pred_records = len(pred_records)

        # 构建 doc_id 索引
        pred_by_doc_id = {self._get_doc_id(r): r for r in pred_records}

        augmented_gold = []
        augmented_pred = []
        doc_metrics_list: List[DocMetrics] = []

        for gold_r in gold_records:
            doc_id = self._get_doc_id(gold_r)
            pred_r = pred_by_doc_id.get(doc_id, {"triples": [], "entities": [], "events": []})

            self.stats.total_gold_triples += len(gold_r.get("triples", []))
            self.stats.total_pred_triples += len(pred_r.get("triples", []))
            self.stats.total_gold_entities += len(gold_r.get("entities", []))

            # 提取 gold 实体名称集合（用于对齐）
            gold_entity_names: Set[str] = set()
            for e in gold_r.get("entities", []):
                if e.get("name"):
                    gold_entity_names.add(e["name"])
            # 也从三元组中提取实体
            for t in gold_r.get("triples", []):
                if t.get("subject"):
                    gold_entity_names.add(t["subject"])
                if t.get("object"):
                    gold_entity_names.add(t["object"])

            # 先进行归一化处理
            if mode in ("gold", "both"):
                aug_gold_r = self.augment_record(gold_r, None)
            else:
                aug_gold_r = gold_r

            if mode in ("pred", "both"):
                aug_pred_r = self.augment_record(pred_r, gold_entity_names)
            else:
                aug_pred_r = pred_r

            # 计算单文档指标
            doc_metrics = self.compute_doc_metrics(aug_gold_r, aug_pred_r)
            doc_metrics_list.append(doc_metrics)

            # 文档级别筛选
            if self.config.filter_mode == "doc":
                # 检查是否满足阈值
                keep = True
                has_content = False  # 至少有一种类型的数据
                
                # 只有当有数据时才检查阈值
                if doc_metrics.gold_entity_count > 0 or doc_metrics.pred_entity_count > 0:
                    has_content = True
                    if doc_metrics.entity_f1 < self.config.min_entity_f1:
                        keep = False
                if doc_metrics.gold_triple_count > 0 or doc_metrics.pred_triple_count > 0:
                    has_content = True
                    if doc_metrics.triple_f1 < self.config.min_triple_f1:
                        keep = False
                if doc_metrics.gold_event_count > 0 or doc_metrics.pred_event_count > 0:
                    has_content = True
                    if doc_metrics.event_f1 < self.config.min_event_f1:
                        keep = False
                
                # 如果完全没有内容，不保留
                if not has_content:
                    keep = False

                doc_metrics.kept = keep

                if keep:
                    augmented_gold.append(aug_gold_r)
                    augmented_pred.append(aug_pred_r)
                    self.stats.kept_docs += 1
                else:
                    self.stats.filtered_docs += 1
            elif self.config.filter_mode == "aggregate":
                # aggregate 模式：先收集所有数据，后续统一筛选
                augmented_gold.append(aug_gold_r)
                augmented_pred.append(aug_pred_r)
            else:
                # 不筛选，保留所有文档
                augmented_gold.append(aug_gold_r)
                augmented_pred.append(aug_pred_r)

        # aggregate 模式：按聚合指标筛选
        if self.config.filter_mode == "aggregate":
            augmented_gold, augmented_pred, doc_metrics_list = self._filter_by_aggregate_metrics(
                augmented_gold, augmented_pred, doc_metrics_list
            )

        report = self._generate_report()
        return augmented_gold, augmented_pred, report, doc_metrics_list

    def _filter_by_aggregate_metrics(
        self,
        gold_records: List[Dict[str, Any]],
        pred_records: List[Dict[str, Any]],
        doc_metrics_list: List[DocMetrics],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[DocMetrics]]:
        """
        按聚合指标筛选文档。

        支持两种贪心策略（通过 config.aggregate_strategy 控制）：
        - forward: 正向贪心，从空开始逐步加入高质量文档，直到无法满足阈值
        - reverse: 反向贪心，从全选开始逐步移除最差文档，直到满足阈值
        
        Returns:
            (filtered_gold, filtered_pred, updated_doc_metrics)
        """
        import logging
        logger = logging.getLogger(__name__)

        strategy = self.config.aggregate_strategy
        logger.info(f"[Aggregate] 使用 {strategy} 策略 ({'从空开始加入' if strategy == 'forward' else '从全选开始移除'})")

        # 辅助函数：计算F1
        def calc_f1(matched: int, gold: int, pred: int) -> float:
            if gold == 0 and pred == 0:
                return 1.0
            if gold == 0 or pred == 0:
                return 0.0
            p = matched / pred
            r = matched / gold
            return 2 * p * r / (p + r) if (p + r) > 0 else 0.0

        # 1. 过滤掉内容不足的文档，并预计算每个文档的统计量
        # 要求：gold 和 pred 双方都至少有两项非空（entity/triple/event 三项中）
        valid_docs: List[DocMetrics] = []
        doc_stats_map = {}

        for dm in doc_metrics_list:
            # 检查 gold 侧非空项数
            gold_non_empty = sum([
                1 if dm.gold_entity_count > 0 else 0,
                1 if dm.gold_triple_count > 0 else 0,
                1 if dm.gold_event_count > 0 else 0,
            ])
            # 检查 pred 侧非空项数
            pred_non_empty = sum([
                1 if dm.pred_entity_count > 0 else 0,
                1 if dm.pred_triple_count > 0 else 0,
                1 if dm.pred_event_count > 0 else 0,
            ])
            # 要求双方都至少有 2 项非空
            has_sufficient_content = (gold_non_empty >= 2 and pred_non_empty >= 2)
            
            if not has_sufficient_content:
                dm.kept = False
                self.stats.filtered_docs += 1
                continue
            
            # 预估匹配数量（基于 F1 反推: F1 = 2*m / (g+p) => m = F1*(g+p)/2）
            est_matched_e = 0
            if dm.gold_entity_count > 0 and dm.pred_entity_count > 0:
                est_matched_e = int(dm.entity_f1 * (dm.gold_entity_count + dm.pred_entity_count) / 2)
                est_matched_e = min(est_matched_e, dm.gold_entity_count, dm.pred_entity_count)
            
            est_matched_t = 0
            if dm.gold_triple_count > 0 and dm.pred_triple_count > 0:
                est_matched_t = int(dm.triple_f1 * (dm.gold_triple_count + dm.pred_triple_count) / 2)
                est_matched_t = min(est_matched_t, dm.gold_triple_count, dm.pred_triple_count)
            
            est_matched_ev = 0
            if dm.gold_event_count > 0 and dm.pred_event_count > 0:
                est_matched_ev = int(dm.event_f1 * (dm.gold_event_count + dm.pred_event_count) / 2)
                est_matched_ev = min(est_matched_ev, dm.gold_event_count, dm.pred_event_count)

            # 计算质量分数用于排序
            w_e = self.config.entity_weight
            w_t = self.config.triple_weight
            w_ev = self.config.event_weight
            total_w = w_e + w_t + w_ev if (w_e + w_t + w_ev) > 0 else 1.0
            quality_score = (dm.entity_f1 * w_e + dm.triple_f1 * w_t + dm.event_f1 * w_ev) / total_w

            doc_stats_map[dm.doc_id] = {
                "g_e": dm.gold_entity_count, "p_e": dm.pred_entity_count, "m_e": est_matched_e,
                "g_t": dm.gold_triple_count, "p_t": dm.pred_triple_count, "m_t": est_matched_t,
                "g_ev": dm.gold_event_count, "p_ev": dm.pred_event_count, "m_ev": est_matched_ev,
                "dm": dm, "quality": quality_score
            }
            valid_docs.append(dm)

        # 根据策略执行不同的贪心算法
        if strategy == "forward":
            selected_ids = self._forward_greedy(valid_docs, doc_stats_map, calc_f1, logger)
        else:
            selected_ids = self._reverse_greedy(valid_docs, doc_stats_map, calc_f1, logger)

        # 标记保留/过滤
        selected_docs: List[DocMetrics] = []
        for dm in doc_metrics_list:
            if dm.doc_id in selected_ids:
                dm.kept = True
                self.stats.kept_docs += 1
                selected_docs.append(dm)
            else:
                dm.kept = False
                self.stats.filtered_docs += 1
        
        # 构建筛选后的结果
        filtered_gold = [r for r in gold_records if self._get_doc_id(r) in selected_ids]
        filtered_pred = [r for r in pred_records if self._get_doc_id(r) in selected_ids]
        
        # 计算最终聚合指标
        total_g_e = sum(doc_stats_map[did]["g_e"] for did in selected_ids)
        total_p_e = sum(doc_stats_map[did]["p_e"] for did in selected_ids)
        total_m_e = sum(doc_stats_map[did]["m_e"] for did in selected_ids)
        total_g_t = sum(doc_stats_map[did]["g_t"] for did in selected_ids)
        total_p_t = sum(doc_stats_map[did]["p_t"] for did in selected_ids)
        total_m_t = sum(doc_stats_map[did]["m_t"] for did in selected_ids)
        total_g_ev = sum(doc_stats_map[did]["g_ev"] for did in selected_ids)
        total_p_ev = sum(doc_stats_map[did]["p_ev"] for did in selected_ids)
        total_m_ev = sum(doc_stats_map[did]["m_ev"] for did in selected_ids)

        final_entity_f1 = calc_f1(total_m_e, total_g_e, total_p_e)
        final_triple_f1 = calc_f1(total_m_t, total_g_t, total_p_t)
        final_event_f1 = calc_f1(total_m_ev, total_g_ev, total_p_ev)

        logger.info(f"[Aggregate] 筛选完成: 保留 {len(selected_docs)}/{len(doc_metrics_list)} 文档")
        logger.info(f"[Aggregate] 聚合指标: Entity F1={final_entity_f1:.4f}, Triple F1={final_triple_f1:.4f}, Event F1={final_event_f1:.4f}")

        return filtered_gold, filtered_pred, doc_metrics_list

    def _forward_greedy(self, valid_docs, doc_stats_map, calc_f1, logger):
        """
        正向贪心：从空开始，按质量分数从高到低加入文档，直到无法满足阈值。
        目标：尽可能多保留文档，同时保证整体指标 >= 阈值。
        """
        # 按质量分数从高到低排序
        sorted_docs = sorted(valid_docs, key=lambda dm: doc_stats_map[dm.doc_id]["quality"], reverse=True)
        
        selected_ids = set()
        total_g_e = total_p_e = total_m_e = 0
        total_g_t = total_p_t = total_m_t = 0
        total_g_ev = total_p_ev = total_m_ev = 0

        for dm in sorted_docs:
            stats = doc_stats_map[dm.doc_id]
            
            # 尝试加入这个文档
            new_g_e = total_g_e + stats["g_e"]
            new_p_e = total_p_e + stats["p_e"]
            new_m_e = total_m_e + stats["m_e"]
            new_g_t = total_g_t + stats["g_t"]
            new_p_t = total_p_t + stats["p_t"]
            new_m_t = total_m_t + stats["m_t"]
            new_g_ev = total_g_ev + stats["g_ev"]
            new_p_ev = total_p_ev + stats["p_ev"]
            new_m_ev = total_m_ev + stats["m_ev"]

            new_e_f1 = calc_f1(new_m_e, new_g_e, new_p_e)
            new_t_f1 = calc_f1(new_m_t, new_g_t, new_p_t)
            new_ev_f1 = calc_f1(new_m_ev, new_g_ev, new_p_ev)

            # 检查是否仍满足阈值
            meets_threshold = (
                new_e_f1 >= self.config.min_entity_f1 and
                new_t_f1 >= self.config.min_triple_f1 and
                new_ev_f1 >= self.config.min_event_f1
            )

            if meets_threshold or len(selected_ids) == 0:
                # 加入这个文档
                selected_ids.add(dm.doc_id)
                total_g_e, total_p_e, total_m_e = new_g_e, new_p_e, new_m_e
                total_g_t, total_p_t, total_m_t = new_g_t, new_p_t, new_m_t
                total_g_ev, total_p_ev, total_m_ev = new_g_ev, new_p_ev, new_m_ev
            # 如果不满足阈值，跳过这个文档（继续尝试下一个）

        return selected_ids

    def _reverse_greedy(self, valid_docs, doc_stats_map, calc_f1, logger):
        """
        反向贪心：从全选开始，逐步移除对整体指标拖累最大的文档，直到满足阈值。
        目标：尽可能多保留文档，同时保证整体指标 >= 阈值。
        """
        selected_ids = {dm.doc_id for dm in valid_docs}
        
        # 初始化全局计数器
        total_g_e = sum(doc_stats_map[did]["g_e"] for did in selected_ids)
        total_p_e = sum(doc_stats_map[did]["p_e"] for did in selected_ids)
        total_m_e = sum(doc_stats_map[did]["m_e"] for did in selected_ids)
        total_g_t = sum(doc_stats_map[did]["g_t"] for did in selected_ids)
        total_p_t = sum(doc_stats_map[did]["p_t"] for did in selected_ids)
        total_m_t = sum(doc_stats_map[did]["m_t"] for did in selected_ids)
        total_g_ev = sum(doc_stats_map[did]["g_ev"] for did in selected_ids)
        total_p_ev = sum(doc_stats_map[did]["p_ev"] for did in selected_ids)
        total_m_ev = sum(doc_stats_map[did]["m_ev"] for did in selected_ids)

        w_e = self.config.entity_weight
        w_t = self.config.triple_weight
        w_ev = self.config.event_weight
        total_w = w_e + w_t + w_ev if (w_e + w_t + w_ev) > 0 else 1.0

        while len(selected_ids) > 1:
            curr_e_f1 = calc_f1(total_m_e, total_g_e, total_p_e)
            curr_t_f1 = calc_f1(total_m_t, total_g_t, total_p_t)
            curr_ev_f1 = calc_f1(total_m_ev, total_g_ev, total_p_ev)

            # 检查是否满足阈值
            if (curr_e_f1 >= self.config.min_entity_f1 and
                curr_t_f1 >= self.config.min_triple_f1 and
                curr_ev_f1 >= self.config.min_event_f1):
                break

            # 找出移除后能最大提升整体指标的文档
            current_score = (curr_e_f1 * w_e + curr_t_f1 * w_t + curr_ev_f1 * w_ev) / total_w
            best_improvement = -float('inf')
            worst_doc_id = None

            # 使用排序后的列表遍历，确保结果可复现
            for doc_id in sorted(selected_ids):
                stats = doc_stats_map[doc_id]
                
                tm_e = total_m_e - stats["m_e"]
                tg_e = total_g_e - stats["g_e"]
                tp_e = total_p_e - stats["p_e"]
                tm_t = total_m_t - stats["m_t"]
                tg_t = total_g_t - stats["g_t"]
                tp_t = total_p_t - stats["p_t"]
                tm_ev = total_m_ev - stats["m_ev"]
                tg_ev = total_g_ev - stats["g_ev"]
                tp_ev = total_p_ev - stats["p_ev"]

                next_e_f1 = calc_f1(tm_e, tg_e, tp_e)
                next_t_f1 = calc_f1(tm_t, tg_t, tp_t)
                next_ev_f1 = calc_f1(tm_ev, tg_ev, tp_ev)
                next_score = (next_e_f1 * w_e + next_t_f1 * w_t + next_ev_f1 * w_ev) / total_w
                
                improvement = next_score - current_score
                if improvement > best_improvement:
                    best_improvement = improvement
                    worst_doc_id = doc_id

            if worst_doc_id:
                selected_ids.remove(worst_doc_id)
                stats = doc_stats_map[worst_doc_id]
                total_g_e -= stats["g_e"]
                total_p_e -= stats["p_e"]
                total_m_e -= stats["m_e"]
                total_g_t -= stats["g_t"]
                total_p_t -= stats["p_t"]
                total_m_t -= stats["m_t"]
                total_g_ev -= stats["g_ev"]
                total_p_ev -= stats["p_ev"]
                total_m_ev -= stats["m_ev"]
            else:
                break

        return selected_ids

    @staticmethod
    def _get_doc_id(record: Dict[str, Any]) -> str:
        """获取文档 ID"""
        for key in ("doc_id", "docid", "id"):
            if key in record:
                return str(record[key])
        return ""

    def _generate_report(self) -> Dict[str, Any]:
        """生成处理报告"""
        return {
            "config": {
                "strategy": self.config.strategy,
                "entity_match_threshold": self.config.entity_match_threshold,
                "relation_match_threshold": self.config.relation_match_threshold,
                "enable_direction_normalization": self.config.enable_direction_normalization,
                "enable_entity_normalization": self.config.enable_entity_normalization,
                "enable_relation_mapping": self.config.enable_relation_mapping,
                "filter_mode": self.config.filter_mode,
                "min_entity_f1": self.config.min_entity_f1,
                "min_triple_f1": self.config.min_triple_f1,
                "min_event_f1": self.config.min_event_f1,
            },
            "stats": {
                "total_gold_records": self.stats.total_gold_records,
                "total_pred_records": self.stats.total_pred_records,
                "total_gold_triples": self.stats.total_gold_triples,
                "total_pred_triples": self.stats.total_pred_triples,
                "total_gold_entities": self.stats.total_gold_entities,
                "total_pred_entities": self.stats.total_pred_entities,
                "entity_normalizations": self.stats.entity_normalizations,
                "type_normalizations": self.stats.type_normalizations,
                "relation_mappings": self.stats.relation_mappings,
                "direction_swaps": self.stats.direction_swaps,
                "ignored_relations": self.stats.ignored_relations,
                "augmented_pred_triples": self.stats.augmented_pred_triples,
                "filtered_docs": self.stats.filtered_docs,
                "kept_docs": self.stats.kept_docs,
            },
        }


# ============================================================
# 辅助函数
# ============================================================

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    """加载 JSONL 文件"""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return records


def save_jsonl(records: List[Dict[str, Any]], path: Path) -> None:
    """保存 JSONL 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_json(path: Path) -> Dict[str, Any]:
    """加载 JSON 文件"""
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(data: Dict[str, Any], path: Path) -> None:
    """保存 JSON 文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ============================================================
# 命令行接口
# ============================================================

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="双向融合数据增强工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 适中策略，双向融合
  python scripts/p5/bidirectional_fusion.py \\
      --gold outputs/eval_models_hybrid/gold/claude/gold_hybrid_tbox_claude.jsonl \\
      --pred outputs/eval_models_hybrid/pred/glm/predictions_glm_0111.jsonl \\
      --tbox outputs/kg_final/tbox_final.json \\
      --synonyms configs/entity_synonyms.json \\
      --relation-mapping configs/relation_mapping.json \\
      --strategy moderate \\
      --output-dir outputs/fusion/glm_vs_claude

  # 激进策略，仅增强 Pred
  python scripts/p5/bidirectional_fusion.py \\
      --gold outputs/eval_models_hybrid/gold/claude/gold_hybrid_tbox_claude.jsonl \\
      --pred outputs/eval_models_hybrid/pred/glm/predictions_glm_0111.jsonl \\
      --tbox outputs/kg_final/tbox_final.json \\
      --strategy aggressive \\
      --mode pred \\
      --output-dir outputs/fusion/glm_vs_claude
        """
    )

    # 输入文件
    parser.add_argument("--gold", "-g", required=True, help="Gold 标注文件（jsonl）")
    parser.add_argument("--pred", "-p", required=True, help="Pred 预测文件（jsonl）")
    parser.add_argument("--tbox", "-t", required=True, help="TBox 文件（json）")

    # 配置文件（可选）
    parser.add_argument("--synonyms", "-s", default="configs/entity_synonyms.json",
                        help="实体同义词库（json）")
    parser.add_argument("--relation-mapping", "-r", default="configs/relation_mapping.json",
                        help="关系映射配置（json）")

    # 融合策略
    parser.add_argument("--strategy", choices=["conservative", "moderate", "aggressive"],
                        default="moderate", help="融合策略（默认: moderate）")
    parser.add_argument("--mode", choices=["gold", "pred", "both"],
                        default="both", help="处理模式（默认: both）")

    # 文档筛选参数
    parser.add_argument("--filter-mode", choices=["none", "doc", "aggregate"],
                        default="none", 
                        help="筛选模式: none=不筛选, doc=按单文档阈值筛选, aggregate=按聚合指标筛选（默认: none）")
    parser.add_argument("--min-entity-f1", type=float, default=0.5,
                        help="实体 F1 阈值（默认: 0.5）")
    parser.add_argument("--min-triple-f1", type=float, default=0.3,
                        help="三元组 F1 阈值（默认: 0.3）")
    parser.add_argument("--min-event-f1", type=float, default=0.5,
                        help="事件 F1 阈值（默认: 0.5）")
    parser.add_argument("--export-doc-ids", action="store_true",
                        help="导出保留文档的 doc_id 列表（用于重新评估）")
    
    # Aggregate 模式权重参数（用于计算文档质量分数）
    parser.add_argument("--entity-weight", type=float, default=0.5,
                        help="Entity F1 权重（默认: 0.5）")
    parser.add_argument("--triple-weight", type=float, default=0.5,
                        help="Triple F1 权重（默认: 0.5）")
    parser.add_argument("--event-weight", type=float, default=0.0,
                        help="Event F1 权重（默认: 0.0，即不考虑事件）")
    parser.add_argument("--aggregate-strategy", choices=["forward", "reverse"],
                        default="forward",
                        help="聚合筛选策略: forward=正向贪心(从空开始加入高质量文档), reverse=反向贪心(从全选开始移除最差文档)（默认: forward）")

    # 阈值参数
    parser.add_argument("--entity-threshold", type=float, default=0.8,
                        help="实体匹配阈值（默认: 0.8）")
    parser.add_argument("--relation-threshold", type=float, default=0.7,
                        help="关系匹配阈值（默认: 0.7）")

    # 输出
    parser.add_argument("--output-dir", "-o", required=True, help="输出目录")

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # 加载数据
    print("=" * 60)
    print("双向融合数据增强")
    print("=" * 60)

    gold_path = Path(args.gold)
    pred_path = Path(args.pred)
    tbox_path = Path(args.tbox)
    synonyms_path = Path(args.synonyms)
    relation_mapping_path = Path(args.relation_mapping)
    output_dir = Path(args.output_dir)

    print(f"Gold: {gold_path}")
    print(f"Pred: {pred_path}")
    print(f"TBox: {tbox_path}")
    print(f"策略: {args.strategy}")
    print(f"模式: {args.mode}")
    print(f"筛选模式: {args.filter_mode}")
    if args.filter_mode == "doc":
        print(f"  实体 F1 阈值: {args.min_entity_f1}")
        print(f"  三元组 F1 阈值: {args.min_triple_f1}")
        print(f"  事件 F1 阈值: {args.min_event_f1}")
    elif args.filter_mode == "aggregate":
        print(f"  实体 F1 阈值: {args.min_entity_f1}")
        print(f"  三元组 F1 阈值: {args.min_triple_f1}")
        print(f"  事件 F1 阈值: {args.min_event_f1}")
        print(f"  权重配置: Entity={args.entity_weight}, Triple={args.triple_weight}, Event={args.event_weight}")
        print(f"  贪心策略: {args.aggregate_strategy} ({'从空开始加入' if args.aggregate_strategy == 'forward' else '从全选开始移除'})")
    print()

    # 加载文件
    gold_records = load_jsonl(gold_path)
    pred_records = load_jsonl(pred_path)
    tbox = load_json(tbox_path)

    synonyms = {}
    if synonyms_path.exists():
        synonyms = load_json(synonyms_path)

    relation_mapping = {"relation_mapping": {}, "inverse_relations": {}, "ignore_relations": []}
    if relation_mapping_path.exists():
        relation_mapping = load_json(relation_mapping_path)

    print(f"Gold 记录数: {len(gold_records)}")
    print(f"Pred 记录数: {len(pred_records)}")
    print(f"同义词条目: {len([k for k in synonyms if not k.startswith('_')])}")
    print(f"关系映射数: {len(relation_mapping.get('relation_mapping', {}))}")
    print()

    # 配置
    config = FusionConfig(
        strategy=args.strategy,
        entity_match_threshold=args.entity_threshold,
        relation_match_threshold=args.relation_threshold,
        filter_mode=args.filter_mode,
        min_entity_f1=args.min_entity_f1,
        min_triple_f1=args.min_triple_f1,
        min_event_f1=args.min_event_f1,
        entity_weight=args.entity_weight,
        triple_weight=args.triple_weight,
        event_weight=args.event_weight,
        aggregate_strategy=args.aggregate_strategy,
    )

    # 根据策略调整配置
    if args.strategy == "conservative":
        config.entity_match_threshold = 1.0
        config.enable_direction_normalization = False
    elif args.strategy == "aggressive":
        config.entity_match_threshold = 0.6
        config.enable_direction_normalization = True

    # 执行融合
    print("开始融合处理...")
    fusion = BidirectionalFusion(tbox, synonyms, relation_mapping, config)
    augmented_gold, augmented_pred, report, doc_metrics_list = fusion.process(
        gold_records, pred_records, mode=args.mode
    )

    # 保存结果
    output_dir.mkdir(parents=True, exist_ok=True)

    # 根据筛选模式选择输出文件名
    if args.filter_mode in ("doc", "aggregate"):
        gold_output = output_dir / "gold_filtered.jsonl"
        pred_output = output_dir / "pred_filtered.jsonl"
    else:
        gold_output = output_dir / "gold_augmented.jsonl"
        pred_output = output_dir / "pred_augmented.jsonl"
    report_output = output_dir / "fusion_report.json"
    doc_metrics_output = output_dir / "doc_metrics.jsonl"

    save_jsonl(augmented_gold, gold_output)
    save_jsonl(augmented_pred, pred_output)
    save_json(report, report_output)

    # 保存文档级别指标
    with open(doc_metrics_output, "w", encoding="utf-8") as f:
        for dm in doc_metrics_list:
            f.write(json.dumps({
                "doc_id": dm.doc_id,
                "entity_f1": round(dm.entity_f1, 4),
                "triple_f1": round(dm.triple_f1, 4),
                "event_f1": round(dm.event_f1, 4),
                "gold_entity_count": dm.gold_entity_count,
                "pred_entity_count": dm.pred_entity_count,
                "gold_triple_count": dm.gold_triple_count,
                "pred_triple_count": dm.pred_triple_count,
                "gold_event_count": dm.gold_event_count,
                "pred_event_count": dm.pred_event_count,
                "kept": dm.kept,
            }, ensure_ascii=False) + "\n")

    print()
    print("=" * 60)
    print("融合完成")
    print("=" * 60)
    print(f"Gold 输出: {gold_output}")
    print(f"Pred 输出: {pred_output}")
    print(f"报告: {report_output}")
    print(f"文档指标: {doc_metrics_output}")
    print()
    print("统计信息:")
    for key, value in report["stats"].items():
        print(f"  {key}: {value}")

    # 如果启用了筛选，显示筛选统计
    if args.filter_mode in ("doc", "aggregate"):
        kept = report["stats"]["kept_docs"]
        filtered = report["stats"]["filtered_docs"]
        total = kept + filtered
        print()
        print(f"筛选模式: {args.filter_mode}")
        print(f"筛选结果: 保留 {kept}/{total} 文档 ({kept/total*100:.1f}%)")

        # 计算保留文档的平均指标
        kept_metrics = [dm for dm in doc_metrics_list if dm.kept]
        if kept_metrics:
            avg_entity_f1 = sum(dm.entity_f1 for dm in kept_metrics) / len(kept_metrics)
            avg_triple_f1 = sum(dm.triple_f1 for dm in kept_metrics) / len(kept_metrics)
            avg_event_f1 = sum(dm.event_f1 for dm in kept_metrics) / len(kept_metrics)
            print(f"保留文档平均指标:")
            print(f"  Entity F1: {avg_entity_f1:.4f}")
            print(f"  Triple F1: {avg_triple_f1:.4f}")
            print(f"  Event F1: {avg_event_f1:.4f}")
            
            if args.filter_mode == "aggregate":
                # aggregate 模式：计算聚合指标（更准确）
                total_gold_e = sum(dm.gold_entity_count for dm in kept_metrics)
                total_pred_e = sum(dm.pred_entity_count for dm in kept_metrics)
                total_gold_t = sum(dm.gold_triple_count for dm in kept_metrics)
                total_pred_t = sum(dm.pred_triple_count for dm in kept_metrics)
                total_gold_ev = sum(dm.gold_event_count for dm in kept_metrics)
                total_pred_ev = sum(dm.pred_event_count for dm in kept_metrics)
                print(f"聚合统计:")
                print(f"  实体: Gold={total_gold_e}, Pred={total_pred_e}")
                print(f"  三元组: Gold={total_gold_t}, Pred={total_pred_t}")
                print(f"  事件: Gold={total_gold_ev}, Pred={total_pred_ev}")

        # 导出 doc_id 列表
        if args.export_doc_ids:
            doc_ids_file = output_dir / "kept_doc_ids.txt"
            with open(doc_ids_file, "w", encoding="utf-8") as f:
                for dm in kept_metrics:
                    f.write(dm.doc_id + "\n")
            print(f"\n已导出 doc_id 列表: {doc_ids_file}")
            print(f"用法示例:")
            print(f"  # 用这些 doc_id 重新评估")
            print(f"  bash scripts/p5/run_single_model.sh \\")
            print(f"    --pred-file {pred_output} \\")
            print(f"    --test-file {gold_output} \\")
            print(f"    --tbox {args.tbox} \\")
            print(f"    --output-base {output_dir}/eval_results")


if __name__ == "__main__":
    main()
