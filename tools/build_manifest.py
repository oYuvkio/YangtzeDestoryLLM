#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三分法语料用途清单生成工具（P4/P5/EVAL）。

目标：
- P4（Schema Enrichment）：仅用于本体/模式增强，概念性语句
- P5（Instance Population）：仅用于实例填充/建图，事件事实
- EVAL（Evaluation）：仅用于评测，含 dev/test 分层

规则：
- 规则A（概念/规范 → P4）：定义、分类、制度、流程描述
- 规则B（事件事实 → P5/EVAL）：具体时间、地点、数值
- 文档级互斥，支持章节级分流
- 可选时间隔离：--p4-year-max / --eval-year-min

使用示例：
    # 基础用法
    python tools/build_manifest.py \\
        --input data/corpus_for_kg/filtered_ytz_corpus/light_pool_dedup.jsonl \\
        --out data/manifests/purpose_manifest.jsonl \\
        --log-file logs/manifest/build.log

    # 启用时间隔离
    python tools/build_manifest.py \\
        --input data/corpus_for_kg/filtered_ytz_corpus/light_pool_dedup.jsonl \\
        --out data/manifests/purpose_manifest.jsonl \\
        --p4-year-max 2016 \\
        --eval-year-min 2017 \\
        --seed 42

    # 查看帮助
    python tools/build_manifest.py --help
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Set, Tuple

# ==============================================================================
# 项目路径配置
# ==============================================================================
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None  # type: ignore
    YAML_AVAILABLE = False


# ==============================================================================
# 常量定义
# ==============================================================================
class Purpose(str, Enum):
    """语料用途枚举"""
    P4 = "P4"      # Schema Enrichment（本体增强）
    P5 = "P5"      # Instance Population（实例填充/建图）
    EVAL = "EVAL"  # Evaluation（评测）


class SplitLevel(str, Enum):
    """分流粒度枚举"""
    DOC = "doc"
    SECTION = "section"


class Fold(str, Enum):
    """EVAL 数据集拆分"""
    DEV = "dev"
    TEST = "test"


class Constants:
    """全局常量（可从配置加载）"""
    VERSION: Final[str] = "1.1.0"
    TOOL_NAME: Final[str] = "三分法语料清单生成工具"
    
    # P4 倾向的来源类型
    P4_SOURCE_TYPES: Set[str] = {
        "emergency_plan",
        "gazette_yearbook", 
        "regulation",
        "technical_guideline",
        "law_plan",
    }
    
    # P4 优选的 topic_label
    P4_TOPIC_LABELS: Set[str] = {
        "institution_regulation",
        "backgroundanalysis",
        "background_analysis",
    }
    
    # P4 概念性标志词（正则模式）
    P4_CONCEPT_PATTERNS: List[str] = [
        r"(?:是指|定义为|系指)",
        r"(?:包括以下|分为以下|具体包括)",
        r"(?:按照.*规定|依据.*标准)",
        r"(?:响应级别|应急响应|预案启动)",
        r"(?:原则|职责|流程|标准|指标|术语)",
        r"(?:第[一二三四五六七八九十]+条)",
        r"(?:定义|概念)",
    ]
    
    # P4 最低概念得分阈值
    P4_MIN_SCORE: int = 3
    
    # EVAL 倾向的来源类型
    EVAL_SOURCE_TYPES: Set[str] = {
        "news",
        "case_study",
        "news_popular",
    }
    
    # EVAL 倾向的主题标签
    EVAL_TOPIC_LABELS: Set[str] = {
        "disasterevent",
        "disaster_event",
        "impact_assessment",
    }
    
    # 实例性标志（正则模式）
    INSTANCE_PATTERNS: List[str] = [
        r"\d{4}年\d{1,2}月\d{1,2}日",
        r"\d{4}年\d{1,2}月",
        r"\d+(\.\d+)?[万亿]?(?:人|亩|元|吨|公顷|平方公里)",
        r"洪峰流量.*?m[³3]/s",
        r"经济损失.*?[万亿]?元",
        r"受灾面积.*?(?:平方公里|km²|hm²|万亩)",
        r"超警\d+天",
        r"水位.*?\d+(\.\d+)?m",
        r"死亡\d+人",
        r"转移\d+[万]?人",
        r"(?:省|市|县|区|镇|村|站)",
    ]
    
    # 分层抽样目标（EVAL）
    STRATIFY_TARGETS: Dict[str, int] = {
        "disasterevent": 150,
        "disaster_event": 150,
        "measure_response": 180,
        "backgroundanalysis": 50,
        "background_analysis": 50,
        "institution_regulation": 50,
        "impact_assessment": 10,
    }
    
    # EVAL 总量上限
    EVAL_MAX_COUNT: Optional[int] = 500
    
    # EVAL 抽样比例（当不使用分层目标时）
    EVAL_SAMPLE_RATIO: float = 0.3
    
    # 默认 dev/test 比例
    DEFAULT_DEV_RATIO: float = 0.6
    DEFAULT_SEED: int = 42
    
    @classmethod
    def load_from_config(cls, cfg: Dict[str, Any]) -> None:
        """从配置文件加载参数"""
        split_cfg = cfg.get("corpus_split", {})
        if not split_cfg:
            return
        
        # P4 配置
        if split_cfg.get("p4_sources"):
            cls.P4_SOURCE_TYPES = set(split_cfg["p4_sources"])
        if split_cfg.get("p4_topic_labels"):
            cls.P4_TOPIC_LABELS = set(split_cfg["p4_topic_labels"])
        if split_cfg.get("p4_keywords"):
            cls.P4_CONCEPT_PATTERNS = split_cfg["p4_keywords"]
        if split_cfg.get("p4_min_score"):
            cls.P4_MIN_SCORE = split_cfg["p4_min_score"]
        
        # EVAL 配置
        if split_cfg.get("eval_sources"):
            cls.EVAL_SOURCE_TYPES = set(split_cfg["eval_sources"])
        if split_cfg.get("eval_topic_labels"):
            cls.EVAL_TOPIC_LABELS = set(split_cfg["eval_topic_labels"])
        if split_cfg.get("instance_patterns"):
            cls.INSTANCE_PATTERNS = split_cfg["instance_patterns"]
        if split_cfg.get("eval_stratify_targets"):
            cls.STRATIFY_TARGETS = split_cfg["eval_stratify_targets"]
        if split_cfg.get("eval_max_count"):
            cls.EVAL_MAX_COUNT = split_cfg["eval_max_count"]
        if split_cfg.get("eval_sample_ratio"):
            cls.EVAL_SAMPLE_RATIO = split_cfg["eval_sample_ratio"]
        
        # 其他配置
        if split_cfg.get("eval_dev_ratio"):
            cls.DEFAULT_DEV_RATIO = split_cfg["eval_dev_ratio"]
        if split_cfg.get("seed"):
            cls.DEFAULT_SEED = split_cfg["seed"]
        
        logger.info("✅ 已从配置文件加载参数")


# ==============================================================================
# 日志配置
# ==============================================================================
def setup_logger(
    name: str = "build_manifest",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """配置并返回 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


logger = setup_logger()


# ==============================================================================
# 数据结构
# ==============================================================================
@dataclass
class ManifestEntry:
    """Manifest 条目"""
    doc_id: str
    purpose: str
    split_level: str = "doc"
    section_hint: str = ""
    rationale: str = ""
    fold: Optional[str] = None  # 仅 EVAL 有效
    
    # 辅助字段（不写入 manifest）
    p4_score: int = field(default=0, repr=False)
    instance_score: int = field(default=0, repr=False)
    matched_patterns: List[str] = field(default_factory=list, repr=False)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典"""
        result = {
            "doc_id": self.doc_id,
            "purpose": self.purpose,
            "split_level": self.split_level,
            "section_hint": self.section_hint,
            "rationale": self.rationale,
        }
        if self.fold:
            result["fold"] = self.fold
        return result


@dataclass
class ClassifyStats:
    """分类统计"""
    total: int = 0
    p4_count: int = 0
    p5_count: int = 0
    eval_count: int = 0
    section_split_count: int = 0
    time_isolated_p4: int = 0
    time_isolated_eval: int = 0
    dev_count: int = 0
    test_count: int = 0
    
    # 详细规则统计
    rule_a1_source_type: int = 0      # P4 来源类型命中
    rule_a2_topic_label: int = 0      # P4 topic_label 命中
    rule_a3_concept_strong: int = 0   # P4 概念得分强命中
    rule_b1_topic_label: int = 0      # EVAL/P5 topic_label 命中
    rule_b2_instance_strong: int = 0  # EVAL/P5 实例得分强命中
    rule_c_time_isolation_p4: int = 0 # 时间隔离到 P4
    rule_c_time_isolation_eval: int = 0  # 时间隔离到 EVAL
    rule_d_mixed_content: int = 0     # 混合内容（章节级分流）
    rule_e_fallback_source: int = 0   # 兆底按来源类型
    rule_e_fallback_default: int = 0  # 兆底默认 P5
    stratify_sampled_eval: int = 0    # 分层抽样进 EVAL
    
    # 按 topic_label 统计
    eval_by_topic: Dict[str, int] = field(default_factory=dict)


# ==============================================================================
# 核心分类器（两阶段分类）
# ==============================================================================
class PurposeClassifier:
    """
    改进版三分法语料分类器
    
    两阶段分类策略：
    第一阶段：分类 P4 vs P5_CANDIDATE
    第二阶段：从 P5_CANDIDATE 中分层抽样选出 EVAL，剩余为 P5
    """
    
    def __init__(
        self,
        p4_year_max: Optional[int] = None,
        eval_year_min: Optional[int] = None,
        dev_ratio: float = Constants.DEFAULT_DEV_RATIO,
        seed: int = Constants.DEFAULT_SEED,
        use_stratify: bool = True,  # 是否使用分层抽样
    ):
        self.p4_year_max = p4_year_max
        self.eval_year_min = eval_year_min
        self.dev_ratio = dev_ratio
        self.seed = seed
        self.use_stratify = use_stratify
        self.rng = random.Random(seed)
        
        # 编译正则表达式
        self.p4_patterns = [re.compile(p) for p in Constants.P4_CONCEPT_PATTERNS]
        self.instance_patterns = [re.compile(p) for p in Constants.INSTANCE_PATTERNS]
        
        # 统计
        self.stats = ClassifyStats()
        
        # 已分配的 doc_id（确保互斥）
        self.assigned_docs: Dict[str, str] = {}  # doc_id -> purpose
        
        # 第一阶段的 P5 候选（用于第二阶段分层抽样）
        self.p5_candidates: List[Tuple[str, Dict[str, Any], ManifestEntry]] = []
    
    def _get_topic_label(self, doc: Dict[str, Any]) -> str:
        """提取 topic_label（兼容多种字段路径）"""
        # 尝试 filter_labels.topic_label
        filter_labels = doc.get("filter_labels", {})
        if isinstance(filter_labels, dict):
            topic = filter_labels.get("topic_label", "")
            if topic:
                return topic
        
        # 尝试 filter_decision.labels.topic_label
        filter_decision = doc.get("filter_decision", {})
        if isinstance(filter_decision, dict):
            labels = filter_decision.get("labels", {})
            if isinstance(labels, dict):
                topic = labels.get("topic_label", "")
                if topic:
                    return topic
        
        # 尝试顶层 topic_label
        return doc.get("topic_label", "") or "unknown"
    
    def _get_source_type(self, doc: Dict[str, Any]) -> str:
        """提取 source_type（兼容多种字段路径）"""
        source_type = doc.get("source_type", "")
        if source_type:
            return source_type
        
        # 回退到 filter_labels.source_guess
        filter_labels = doc.get("filter_labels", {})
        if isinstance(filter_labels, dict):
            return filter_labels.get("source_guess", "")
        
        return ""
    
    def _compute_p4_score(self, doc: Dict[str, Any]) -> Tuple[int, List[str]]:
        """计算 P4 倾向得分（概念性）"""
        score = 0
        matched = []
        text = doc.get("text", "")
        
        source_type = self._get_source_type(doc)
        topic_label = self._get_topic_label(doc)
        
        # 来源类型加分
        if source_type in Constants.P4_SOURCE_TYPES:
            score += 2
            matched.append(f"source:{source_type}")
            self.stats.rule_a1_source_type += 1
        
        # P4 优选 topic_label 加分
        if topic_label in Constants.P4_TOPIC_LABELS:
            score += 1
            matched.append(f"p4_topic:{topic_label}")
            self.stats.rule_a2_topic_label += 1
        
        # 概念性标志词匹配
        for pattern in self.p4_patterns:
            if pattern.search(text):
                score += 1
                matched.append(f"pattern:{pattern.pattern[:20]}")
        
        return score, matched
    
    def _compute_instance_score(self, doc: Dict[str, Any]) -> Tuple[int, List[str]]:
        """计算实例性得分（事件事实）"""
        score = 0
        matched = []
        text = doc.get("text", "")
        topic_label = self._get_topic_label(doc)
        
        # EVAL 主题标签加分
        if topic_label in Constants.EVAL_TOPIC_LABELS:
            score += 2
            matched.append(f"topic:{topic_label}")
            self.stats.rule_b1_topic_label += 1
        
        # 实例性标志匹配
        for pattern in self.instance_patterns:
            if pattern.search(text):
                score += 1
                matched.append(f"instance:{pattern.pattern[:20]}")
        
        return score, matched
    
    @staticmethod
    def _coerce_year(value: Any) -> Optional[int]:
        """
        将 year 字段尽量解析为 int 年份。

        - 支持 int / float / str（如 "2020"、"2020年"、"2020.0"）
        - 仅接受合理年份范围，避免误把页码/编号当作年份
        """
        if value is None:
            return None

        if isinstance(value, int):
            return value if 1800 <= value <= 2200 else None

        if isinstance(value, float):
            if value.is_integer():
                year = int(value)
                return year if 1800 <= year <= 2200 else None
            return None

        if isinstance(value, str):
            s = value.strip()
            if not s:
                return None
            m = re.search(r"(19|20)\d{2}", s)
            if not m:
                return None
            year = int(m.group(0))
            return year if 1800 <= year <= 2200 else None

        return None

    @staticmethod
    def _extract_year_from_text(text: str) -> Optional[int]:
        """
        从任意文本中提取可能的年份。

        优先级：
        1) 显式标记：__year_YYYY__（来自 meta/文件名）
        2) 中文写法：YYYY年
        3) 兜底：独立的 4 位年份（路径/标题中更常见）
        """
        if not text:
            return None

        # 1) __year_YYYY__（最可靠）
        m = re.search(r"__year_((?:19|20)\d{2})__", text)
        if m:
            return int(m.group(1))

        # 2) YYYY年（中文年份）
        m = re.search(r"((?:19|20)\d{2})年", text)
        if m:
            return int(m.group(1))

        # 3) 独立 4 位数字（尽量减少误伤）
        m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", text)
        if m:
            return int(m.group(1))

        return None

    def _get_year(self, doc: Dict[str, Any]) -> Optional[int]:
        """
        提取文档年份（用于可选的时间隔离）。

        注意：上游 `filter_corpus_light` 的 year 字段多为字符串（甚至为空），
        因此这里做更鲁棒的解析：
        1) doc["year"]：支持 int/float/str
        2) rel_path/source_file/title/doc_title：优先匹配 __year_YYYY__ / YYYY年
        3) text/doc_title：回退匹配 YYYY年
        """
        year = self._coerce_year(doc.get("year"))
        if year is not None:
            return year

        rel_path = str(doc.get("rel_path") or "")
        source_file = str(doc.get("source_file") or "")
        title = str(doc.get("title") or "")
        doc_title = str(doc.get("doc_title") or "")

        # 先从短文本（路径/标题）提取：更可靠，也更可能包含 __year_YYYY__
        meta_text = " ".join([rel_path, source_file, title, doc_title]).strip()
        year = self._extract_year_from_text(meta_text)
        if year is not None:
            return year

        # 再从正文中提取：可能包含事件年份/引用年份，作为兜底
        text = str(doc.get("text") or "") + doc_title
        return self._extract_year_from_text(text)
    
    def _get_doc_id(self, doc: Dict[str, Any]) -> str:
        """生成文档唯一 ID"""
        doc_id = doc.get("id")
        if doc_id:
            return str(doc_id)
        
        rel_path = doc.get("rel_path", "")
        if rel_path:
            return hashlib.md5(rel_path.encode()).hexdigest()[:12]
        
        text = doc.get("text", "")[:200]
        return hashlib.md5(text.encode()).hexdigest()[:12]
    
    def classify_phase1(self, doc: Dict[str, Any]) -> ManifestEntry:
        """
        第一阶段分类：P4 vs P5_CANDIDATE
        
        所有实例性语料先标记为 P5，后续再从中抽取 EVAL
        
        分类策略（优先级从高到低）：
        1. 时间隔离：年份 <= p4_year_max 且概念性 → P4
        2. 规则A强命中（P4得分 >= p4_min_score 且实例得分 == 0）→ P4
        3. 其他 → P5_CANDIDATE
        """
        self.stats.total += 1
        
        doc_id = self._get_doc_id(doc)
        year = self._get_year(doc)
        p4_score, p4_matched = self._compute_p4_score(doc)
        instance_score, instance_matched = self._compute_instance_score(doc)
        topic_label = self._get_topic_label(doc)
        
        entry = ManifestEntry(
            doc_id=doc_id,
            purpose="",
            p4_score=p4_score,
            instance_score=instance_score,
            matched_patterns=p4_matched + instance_matched,
        )
        
        # ===== 时间隔离优先 =====
        if year:
            # 时间隔离 → P4
            if self.p4_year_max and year <= self.p4_year_max and p4_score >= 2:
                entry.purpose = Purpose.P4.value
                entry.rationale = f"time_isolated:year={year}<=p4_max, p4_score={p4_score}"
                self.stats.time_isolated_p4 += 1
                self.stats.rule_c_time_isolation_p4 += 1
                self.stats.p4_count += 1
                self.assigned_docs[doc_id] = entry.purpose
                return entry
        
        # ===== 规则A：强概念性 → P4 =====
        if p4_score >= Constants.P4_MIN_SCORE and instance_score == 0:
            entry.purpose = Purpose.P4.value
            entry.rationale = f"rule_a3:p4_score={p4_score}>=min, no_instance"
            self.stats.p4_count += 1
            self.stats.rule_a3_concept_strong += 1
            self.assigned_docs[doc_id] = entry.purpose
            return entry
        
        # ===== 混合情况：P4 得分较高且明显大于实例得分 =====
        if p4_score >= 3 and p4_score > instance_score + 1:
            entry.purpose = Purpose.P4.value
            entry.split_level = SplitLevel.SECTION.value
            entry.section_hint = "mixed_p4_dominant"
            entry.rationale = f"mixed:p4_score={p4_score}>instance={instance_score}+1"
            self.stats.p4_count += 1
            self.stats.rule_d_mixed_content += 1
            self.stats.section_split_count += 1
            self.assigned_docs[doc_id] = entry.purpose
            return entry
        
        # ===== 其他情况：标记为 P5_CANDIDATE =====
        # 先临时标记为 P5，后续第二阶段可能转为 EVAL
        entry.purpose = Purpose.P5.value
        
        if instance_score >= 3:
            entry.rationale = f"p5_candidate:instance_score={instance_score}>=3"
            self.stats.rule_b2_instance_strong += 1
        elif instance_score >= 2 and p4_score >= 2:
            entry.split_level = SplitLevel.SECTION.value
            entry.section_hint = "mixed_content"
            entry.rationale = f"p5_candidate:mixed_p4={p4_score}_inst={instance_score}"
            self.stats.rule_d_mixed_content += 1
            self.stats.section_split_count += 1
        else:
            source_type = self._get_source_type(doc)
            if source_type in Constants.EVAL_SOURCE_TYPES:
                entry.rationale = f"p5_candidate:source={source_type}_in_eval_list"
                self.stats.rule_e_fallback_source += 1
            else:
                entry.rationale = f"p5_candidate:fallback_source={source_type}"
                self.stats.rule_e_fallback_default += 1
        
        self.stats.p5_count += 1
        self.assigned_docs[doc_id] = entry.purpose
        
        # 记录候选，用于第二阶段抽样
        self.p5_candidates.append((doc_id, doc, entry))
        
        return entry
    
    def sample_eval_from_p5(self) -> None:
        """
        第二阶段：从 P5 候选中分层抽样选出 EVAL
        """
        if not self.p5_candidates:
            logger.info("无 P5 候选，跳过分层抽样")
            return
        
        logger.info(f"\n开始第二阶段：从 {len(self.p5_candidates)} 个 P5 候选中分层抽样 EVAL...")
        
        # 按 topic_label 分组
        by_topic: Dict[str, List[Tuple[str, Dict, ManifestEntry]]] = {}
        for doc_id, doc, entry in self.p5_candidates:
            topic = self._get_topic_label(doc)
            by_topic.setdefault(topic, []).append((doc_id, doc, entry))
        
        logger.info(f"P5 候选 topic 分布：{{{', '.join(f'{k}:{len(v)}' for k, v in by_topic.items())}}}")
        
        eval_selected: List[str] = []
        
        if self.use_stratify:
            # 分层抽样：按目标数量抽取
            for topic, target_count in Constants.STRATIFY_TARGETS.items():
                pool = by_topic.get(topic, [])
                if not pool:
                    continue
                
                self.rng.shuffle(pool)
                selected = pool[:min(target_count, len(pool))]
                
                for doc_id, doc, entry in selected:
                    entry.purpose = Purpose.EVAL.value
                    entry.fold = Fold.DEV.value if self.rng.random() < self.dev_ratio else Fold.TEST.value
                    entry.rationale += f" -> stratify_eval(topic={topic})"
                    eval_selected.append(doc_id)
                    
                    # 更新统计
                    self.stats.p5_count -= 1
                    self.stats.eval_count += 1
                    self.stats.stratify_sampled_eval += 1
                    self.stats.eval_by_topic[topic] = self.stats.eval_by_topic.get(topic, 0) + 1
                    if entry.fold == Fold.DEV.value:
                        self.stats.dev_count += 1
                    else:
                        self.stats.test_count += 1
                    
                    self.assigned_docs[doc_id] = entry.purpose
                
                logger.info(f"  topic={topic}: 目标{target_count}, 实际抽取{len(selected)}")
        else:
            # 简单随机抽样：按比例抽取
            sample_ratio = Constants.EVAL_SAMPLE_RATIO
            for doc_id, doc, entry in self.p5_candidates:
                if self.rng.random() < sample_ratio:
                    topic = self._get_topic_label(doc)
                    entry.purpose = Purpose.EVAL.value
                    entry.fold = Fold.DEV.value if self.rng.random() < self.dev_ratio else Fold.TEST.value
                    entry.rationale += f" -> random_eval(ratio={sample_ratio})"
                    eval_selected.append(doc_id)
                    
                    self.stats.p5_count -= 1
                    self.stats.eval_count += 1
                    self.stats.stratify_sampled_eval += 1
                    self.stats.eval_by_topic[topic] = self.stats.eval_by_topic.get(topic, 0) + 1
                    if entry.fold == Fold.DEV.value:
                        self.stats.dev_count += 1
                    else:
                        self.stats.test_count += 1
                    
                    self.assigned_docs[doc_id] = entry.purpose
        
        # 检查 EVAL 总量上限
        if Constants.EVAL_MAX_COUNT and self.stats.eval_count > Constants.EVAL_MAX_COUNT:
            logger.warning(f"EVAL 数量({self.stats.eval_count})超过上限({Constants.EVAL_MAX_COUNT})")
        
        logger.info(f"✅ 从 P5 候选中抽取 EVAL: {len(eval_selected)} 条")
    
    def classify(self, doc: Dict[str, Any]) -> ManifestEntry:
        """单文档分类（兼容旧接口，内部调用 phase1）"""
        return self.classify_phase1(doc)
    
    def print_stats(self) -> None:
        """打印详细分类统计"""
        logger.info("=" * 60)
        logger.info("分类统计报告")
        logger.info("=" * 60)
        logger.info(f"总文档数: {self.stats.total}")
        logger.info("-" * 40)
        
        total = max(self.stats.total, 1)
        logger.info(f"P4（本体增强）: {self.stats.p4_count} ({self.stats.p4_count/total*100:.1f}%)")
        logger.info(f"P5（实例填充）: {self.stats.p5_count} ({self.stats.p5_count/total*100:.1f}%)")
        logger.info(f"EVAL（评测）: {self.stats.eval_count} ({self.stats.eval_count/total*100:.1f}%)")
        logger.info(f"  - dev: {self.stats.dev_count}")
        logger.info(f"  - test: {self.stats.test_count}")
        
        logger.info("-" * 40)
        logger.info("规则触发统计：")
        logger.info(f"  rule_a1_source_type(来源类型命中): {self.stats.rule_a1_source_type}")
        logger.info(f"  rule_a2_topic_label(P4 topic命中): {self.stats.rule_a2_topic_label}")
        logger.info(f"  rule_a3_concept_strong(概念强命中): {self.stats.rule_a3_concept_strong}")
        logger.info(f"  rule_b1_topic_label(EVAL topic命中): {self.stats.rule_b1_topic_label}")
        logger.info(f"  rule_b2_instance_strong(实例强命中): {self.stats.rule_b2_instance_strong}")
        logger.info(f"  rule_c_time_isolation_p4(时间隔离P4): {self.stats.rule_c_time_isolation_p4}")
        logger.info(f"  rule_d_mixed_content(混合内容): {self.stats.rule_d_mixed_content}")
        logger.info(f"  rule_e_fallback_source(兆底来源): {self.stats.rule_e_fallback_source}")
        logger.info(f"  rule_e_fallback_default(兆底默认): {self.stats.rule_e_fallback_default}")
        logger.info(f"  stratify_sampled_eval(分层抽样EVAL): {self.stats.stratify_sampled_eval}")
        
        if self.stats.eval_by_topic:
            logger.info("-" * 40)
            logger.info("EVAL 按 topic_label 分布：")
            for topic, count in sorted(self.stats.eval_by_topic.items(), key=lambda x: -x[1]):
                logger.info(f"  {topic}: {count}")
        
        logger.info("-" * 40)
        logger.info(f"章节级分流: {self.stats.section_split_count}")
        if self.p4_year_max:
            logger.info(f"时间隔离P4（<={self.p4_year_max}）: {self.stats.time_isolated_p4}")
        if self.eval_year_min:
            logger.info(f"时间隔离EVAL（>={self.eval_year_min}）: {self.stats.time_isolated_eval}")
        logger.info("=" * 60)


# ==============================================================================
# 主函数
# ==============================================================================
def load_config() -> Dict[str, Any]:
    """加载配置文件"""
    cfg_path = PROJECT_ROOT / "configs" / "cfg.yaml"
    if cfg_path.exists() and YAML_AVAILABLE:
        with open(cfg_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


def build_manifest(
    input_path: Path,
    output_path: Path,
    p4_year_max: Optional[int] = None,
    eval_year_min: Optional[int] = None,
    dev_ratio: float = Constants.DEFAULT_DEV_RATIO,
    seed: int = Constants.DEFAULT_SEED,
    use_stratify: bool = True,
) -> List[ManifestEntry]:
    """
    构建用途清单（两阶段分类）
    
    Args:
        input_path: 输入 JSONL 文件路径
        output_path: 输出 manifest 路径
        p4_year_max: P4 时间隔离上限
        eval_year_min: EVAL 时间隔离下限
        dev_ratio: dev/test 拆分比例
        seed: 随机种子
        use_stratify: 是否使用分层抽样
    
    Returns:
        ManifestEntry 列表
    """
    logger.info(f"开始构建用途清单（两阶段分类）...")
    logger.info(f"输入: {input_path}")
    logger.info(f"输出: {output_path}")
    logger.info(f"时间隔离: p4_year_max={p4_year_max}, eval_year_min={eval_year_min}")
    logger.info(f"分层抽样: {use_stratify}")
    logger.info(f"随机种子: {seed}")
    
    classifier = PurposeClassifier(
        p4_year_max=p4_year_max,
        eval_year_min=eval_year_min,
        dev_ratio=dev_ratio,
        seed=seed,
        use_stratify=use_stratify,
    )
    
    entries: List[ManifestEntry] = []
    
    # 第一阶段：读取并分类 P4 vs P5_CANDIDATE
    logger.info("\n=== 第一阶段：P4 vs P5_CANDIDATE ===")
    with open(input_path, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            
            try:
                doc = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"第 {line_no} 行 JSON 解析失败: {e}")
                continue
            
            entry = classifier.classify_phase1(doc)
            entries.append(entry)
            
            if line_no % 500 == 0:
                logger.info(f"已处理 {line_no} 条...")
    
    logger.info(f"第一阶段完成：P4={classifier.stats.p4_count}, P5_CANDIDATE={classifier.stats.p5_count}")
    
    # 第二阶段：从 P5_CANDIDATE 中分层抽样 EVAL
    logger.info("\n=== 第二阶段：分层抽样 EVAL ===")
    classifier.sample_eval_from_p5()
    
    # 验证互斥性
    p4_ids = {e.doc_id for e in entries if e.purpose == Purpose.P4.value}
    p5_ids = {e.doc_id for e in entries if e.purpose == Purpose.P5.value}
    eval_ids = {e.doc_id for e in entries if e.purpose == Purpose.EVAL.value}
    
    overlap_p4_p5 = p4_ids & p5_ids
    overlap_p4_eval = p4_ids & eval_ids
    overlap_p5_eval = p5_ids & eval_ids
    
    if overlap_p4_p5 or overlap_p4_eval or overlap_p5_eval:
        logger.error(f"发现重叠! P4∩P5={len(overlap_p4_p5)}, P4∩EVAL={len(overlap_p4_eval)}, P5∩EVAL={len(overlap_p5_eval)}")
    else:
        logger.info("✅ 互斥性验证通过：P4/P5/EVAL 无交集")
    
    # 写入 manifest
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
    
    logger.info(f"✅ Manifest 已保存到: {output_path}")
    
    # 保存运行配置
    config_path = output_path.with_suffix(".config.json")
    run_config = {
        "tool": Constants.TOOL_NAME,
        "version": Constants.VERSION,
        "timestamp": datetime.now().isoformat(),
        "input": str(input_path),
        "output": str(output_path),
        "p4_year_max": p4_year_max,
        "eval_year_min": eval_year_min,
        "dev_ratio": dev_ratio,
        "seed": seed,
        "use_stratify": use_stratify,
        "stats": {
            "total": classifier.stats.total,
            "p4_count": classifier.stats.p4_count,
            "p5_count": classifier.stats.p5_count,
            "eval_count": classifier.stats.eval_count,
            "dev_count": classifier.stats.dev_count,
            "test_count": classifier.stats.test_count,
            "stratify_sampled": classifier.stats.stratify_sampled_eval,
        },
        "rule_stats": {
            "rule_a1_source_type": classifier.stats.rule_a1_source_type,
            "rule_a2_topic_label": classifier.stats.rule_a2_topic_label,
            "rule_a3_concept_strong": classifier.stats.rule_a3_concept_strong,
            "rule_b1_topic_label": classifier.stats.rule_b1_topic_label,
            "rule_b2_instance_strong": classifier.stats.rule_b2_instance_strong,
            "rule_c_time_isolation_p4": classifier.stats.rule_c_time_isolation_p4,
            "rule_d_mixed_content": classifier.stats.rule_d_mixed_content,
            "rule_e_fallback_source": classifier.stats.rule_e_fallback_source,
            "rule_e_fallback_default": classifier.stats.rule_e_fallback_default,
        },
        "eval_by_topic": classifier.stats.eval_by_topic,
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(run_config, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 配置已保存到: {config_path}")
    
    # 打印统计
    classifier.print_stats()
    
    return entries


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description=Constants.TOOL_NAME,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础用法（使用分层抽样）
  python tools/build_manifest.py --input data/light_pool.jsonl --out data/manifests/manifest.jsonl

  # 启用时间隔离
  python tools/build_manifest.py --input data/light_pool.jsonl --out data/manifests/manifest.jsonl \\
      --p4-year-max 2016 --eval-year-min 2017

  # 不使用分层抽样（简单随机抽样）
  python tools/build_manifest.py --input data/light_pool.jsonl --out data/manifests/manifest.jsonl \\
      --no-stratify
        """,
    )
    
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="输入 JSONL 文件路径",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        required=True,
        help="输出 manifest 路径",
    )
    parser.add_argument(
        "--p4-year-max",
        type=int,
        default=None,
        help="P4 时间隔离上限年份（如 2016）",
    )
    parser.add_argument(
        "--eval-year-min",
        type=int,
        default=None,
        help="EVAL 时间隔离下限年份（如 2017）",
    )
    parser.add_argument(
        "--dev-ratio",
        type=float,
        default=None,
        help="EVAL 中 dev 的比例（默认从配置文件读取）",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="随机种子（默认从配置文件读取）",
    )
    parser.add_argument(
        "--no-stratify",
        action="store_true",
        help="不使用分层抽样，改用简单随机抽样",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="日志文件路径",
    )
    
    return parser.parse_args()


def main() -> int:
    """主入口"""
    args = parse_args()
    
    # 重新配置 logger
    global logger
    logger = setup_logger(log_file=args.log_file)
    
    logger.info("=" * 60)
    logger.info(f"{Constants.TOOL_NAME} v{Constants.VERSION}")
    logger.info("=" * 60)
    
    # 加载配置文件
    cfg = load_config()
    if cfg:
        Constants.load_from_config(cfg)
    
    # 检查输入文件
    if not args.input.exists():
        logger.error(f"输入文件不存在: {args.input}")
        return 1
    
    # 确定参数（命令行 > 配置文件 > 默认值）
    dev_ratio = args.dev_ratio if args.dev_ratio is not None else Constants.DEFAULT_DEV_RATIO
    seed = args.seed if args.seed is not None else Constants.DEFAULT_SEED
    
    try:
        build_manifest(
            input_path=args.input,
            output_path=args.out,
            p4_year_max=args.p4_year_max,
            eval_year_min=args.eval_year_min,
            dev_ratio=dev_ratio,
            seed=seed,
            use_stratify=not args.no_stratify,
        )
        return 0
    except Exception as e:
        logger.exception(f"构建失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
