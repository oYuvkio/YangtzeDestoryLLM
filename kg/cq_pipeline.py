"""
CQ 驱动的长江灾害知识图谱构建流水线（P1~P5）。

核心思想：以能力问题 (CQ) 反推 TBox，再在 TBox 约束下抽取 ABox。
Prompt 设计、伪代码与示例均与 ``summary/CQ_Summary.txt`` 对齐，方便论文复现。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from kg.utils.deduplication import EmbeddingDeduplicator
from kg.utils.schema_alignment import SchemaAligner
from .llm_core import LLMFactory, LLMBackend
from .prompts import (
    P1_CQ_PROMPT,
    P2_SCHEMA_PROMPT,
    P3_REFINEMENT_PROMPT,
    P4_AUGMENT_PROMPT,
    P5_EXTRACTION_PROMPT,
    EVENT_SCHEMA_HINT,
    P5_COT_EXTRACTION_PROMPT,
    parse_cot_response,
    extract_cot_thought,
    UNIFIED_SYSTEM_PROMPT_COT,
    UNIFIED_USER_PROMPT_COT,
    UNIFIED_VERIFICATION_THRESHOLD,
)
from kg.utils.entity_linking import EntityNormalizer, normalize_entity
from kg.hallucination_filter import HallucinationFilter, filter_hallucinations, VerificationResult
from kg.entity_fusion import EntityFusion, fuse_knowledge, SimpleEntityNormalizer


logger = logging.getLogger(__name__)


# =========================
# 数据结构定义
# =========================
@dataclass
class CQ:
    id: str
    question: str
    category: str


@dataclass
class ClassDef:
    name: str
    cn_name: str
    definition: str
    examples: List[str]
    parent: Optional[str] = None  # 父类名称，用于表达继承关系


@dataclass
class RelationDef:
    name: str
    cn_name: str
    domain: str
    range: str
    definition: str
    functional: Optional[bool] = None


@dataclass
class AttributeDef:
    owner: str
    name: str
    cn_name: str
    value_type: str


@dataclass
class TBoxSchema:
    classes: List[ClassDef]
    relations: List[RelationDef]
    attributes: List[AttributeDef]

    def to_dict(self) -> Dict[str, Any]:
        """便于序列化/写入文件。"""
        return {
            "classes": [asdict(c) for c in self.classes],
            "relations": [asdict(r) for r in self.relations],
            "attributes": [asdict(a) for a in self.attributes],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TBoxSchema":
        """从字典构建 TBoxSchema。"""
        def pick(d: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
            return {k: d.get(k) for k in keys if k in d}

        class_keys = ["name", "cn_name", "definition", "examples", "parent"]
        rel_keys = ["name", "cn_name", "domain", "range", "definition", "functional"]
        attr_keys = ["owner", "name", "cn_name", "value_type"]

        classes = [
            ClassDef(**pick(c, class_keys))
            for c in data.get("classes", []) or []
            if c.get("name")
        ]
        relations = [
            RelationDef(**pick(r, rel_keys))
            for r in data.get("relations", []) or []
            if r.get("name") and r.get("domain") and r.get("range")
        ]
        attributes = [
            AttributeDef(**pick(a, attr_keys))
            for a in data.get("attributes", []) or []
            if a.get("owner") and a.get("name")
        ]

        return cls(classes=classes, relations=relations, attributes=attributes)

    @classmethod
    def load_from_file(cls, file_path: Path) -> "TBoxSchema":
        """从JSON文件加载TBoxSchema。"""
        with file_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)


# =========================
# Schema 格式化工具
# =========================
def format_schema_for_prompt(schema_json: Dict[str, Any], style: str = "markdown") -> str:
    """
    将 TBox Schema 格式化为 Prompt 可用的文本。

    Args:
        schema_json: TBox JSON 对象
        style: 格式化风格，"markdown" 或 "json"

    Returns:
        格式化后的 Schema 文本
    """
    if style == "json":
        return json.dumps(schema_json, ensure_ascii=False, indent=2)

    lines = []

    # 格式化类（中文名在前）
    lines.append("【实体类型定义】\n")
    for cls in schema_json.get("classes", []):
        name = cls.get("name", "")
        cn_name = cls.get("cn_name", "")
        definition = cls.get("definition", "")
        examples = cls.get("examples", [])

        lines.append(f"- **{cn_name}** (ID: `{name}`)")
        lines.append(f"  - 定义：{definition}")
        if examples:
            lines.append(f"  - 示例：{', '.join(examples[:3])}")

    # 格式化关系（表格形式，强调方向）
    lines.append("\n【关系类型定义】\n")
    lines.append("| 中文名 | 关系ID | 主语类型(domain) | 宾语类型(range) | 说明 |")
    lines.append("|--------|--------|------------------|-----------------|------|")

    for rel in schema_json.get("relations", []):
        name = rel.get("name", "")
        cn_name = rel.get("cn_name", "")
        domain = rel.get("domain", "")
        range_ = rel.get("range", "")
        definition = rel.get("definition", "")
        if len(definition) > 30:
            definition = definition[:30] + "..."

        lines.append(f"| {cn_name} | `{name}` | {domain} | {range_} | {definition} |")

    return "\n".join(lines)


# =========================
# LLM 调用助手
# =========================
class LLMJsonClient:
    """封装 JSON 强制输出的调用逻辑，屏蔽不同 provider 细节。"""

    def __init__(self, llm: LLMBackend):
        self.llm = llm

    def call(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        以 messages 形式调用 LLM 并解析 JSON。
        若模型返回 Markdown 代码块，会自动剥离。
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        raw = self.llm.chat_messages(messages, json_mode=True)
        return self._safe_load(raw)

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """移除可能的 ```json 代码块，保持 JSON 纯文本。"""
        cleaned = text.strip()
        if cleaned.startswith("```") and cleaned.endswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    def _safe_load(self, raw: str) -> Dict[str, Any]:
        """
        尽量鲁棒地从模型输出中解析 JSON：
        1) 直接 json.loads；
        2) 若失败，尝试从文本中截取第一个 {...} 或 [...] 片段再解析；
        3) 仍失败则返回空 dict。
        """
        cleaned = self._strip_code_fence(raw)
        if not cleaned:
            return {}
        try:
            obj = json.loads(cleaned)
        except Exception:
            obj = None

        if obj is None:
            # 尝试截取 JSON 子串（优先对象，其次数组）
            match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
            if match:
                snippet = match.group(1)
                try:
                    obj = json.loads(snippet)
                    logger.warning("[LLMJsonClient] JSON 解析失败，已使用子串兜底解析。")
                except Exception:
                    obj = None

        if obj is None:
            preview = cleaned[:500].replace("\n", " ")
            logger.warning(f"[LLMJsonClient] JSON 解析失败，返回空结果。preview={preview}")
            return {}

        # 如果模型直接给了一个数组，就包一层 cqs，方便 P1 使用
        if isinstance(obj, list):
            return {"cqs": obj}

        if isinstance(obj, dict):
            return obj

        return {}


# =========================
# 主 Pipeline
# =========================
class CQLLMPipeline:
    """
    CQ 驱动的 KG 构建流水线。以最小接口覆盖 P1~P5：
    - generate_cqs        (P1)
    - cq_to_schema        (P2)
    - refine_schema       (P3)
    - enhance_schema      (P4)
    - extract_events      (P5)
    """

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None, output_dir: str = "outputs/cq_pipeline/final"):
        config = llm_config or {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "temperature": 0.1,
        }
        self.llm_config = config  # 保存配置，便于日志/调试
        self.llm = LLMFactory.create(config)
        self.client = LLMJsonClient(self.llm)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- P1 ----------
    def generate_cqs(self, domain_desc: str, n_cq: int = 30, save_path: Optional[Path] = None) -> List[CQ]:
        """从领域说明生成 CQ 列表。"""
        user_prompt = P1_CQ_PROMPT.format(domain_desc=domain_desc, n_cq=n_cq)
        res = self.client.call("只输出 JSON，字段按提示填写。", user_prompt)
        raw_cqs = res.get("cqs", []) or []
        cqs: List[CQ] = []

        for i, item in enumerate(raw_cqs, start=1):
            q = item.get("question")
            if not q:
                continue
            cqs.append(
                CQ(
                    id=str(item.get("id", i)),
                    question=q,
                    category=item.get("category", ""),
                )
            )
        if save_path:
            self._dump_json({"cqs": [asdict(cq) for cq in cqs]}, save_path)
        return cqs

    # ---------- P2 ----------

    def cq_to_schema(self, cqs: List[CQ], save_path: Optional[Path] = None) -> TBoxSchema:
        """根据 CQ 归纳初始 TBox。"""
        cq_json = json.dumps(
            {"cqs": [asdict(c) for c in cqs]}, ensure_ascii=False, indent=2)
        user_prompt = P2_SCHEMA_PROMPT.format(cq_json=cq_json)
        res = self.client.call("你是本体工程师，请严格输出 JSON。", user_prompt)
        schema = self._parse_tbox(res)
        if save_path:
            self._dump_json(schema.to_dict(), save_path)
        return schema

    # ---------- P3 ----------
    def refine_schema(self, schema: TBoxSchema, save_path: Optional[Path] = None) -> Dict[str, Any]:
        """对初始模式进行合并、层次化整理。"""
        schema_json = json.dumps(
            schema.to_dict(), ensure_ascii=False, indent=2)
        user_prompt = P3_REFINEMENT_PROMPT.format(schema_json=schema_json)
        res = self.client.call("请清洗模式并输出 JSON。", user_prompt)
        if save_path:
            self._dump_json(res, save_path)
        return res

    def normalize_tbox_with_p3(
        self,
        schema: TBoxSchema,
        p3_result: Dict[str, Any],
        save_path: Optional[Path] = None,
    ) -> TBoxSchema:
        """
        根据 P3 输出结果，对 P2 生成的 TBox 进行规范化处理：
        - 统一类名：根据 merged_class_aliases，把别名类映射到 canonical 类；
        - 合并类定义：按 canonical 维度合并 classes；
        - 清洗关系：使用 P3 中 relations 字段作为新的关系列表，并将 domain/range 映射为 canonical 类名；
        - 规范属性：将 attributes.owner 映射为 canonical 类名，过滤掉指向不存在类的属性。
        """

        alias_map: Dict[str, str] = {}

        merged_aliases = p3_result.get("merged_class_aliases", []) or []
        for item in merged_aliases:
            canonical = item.get("canonical")
            aliases = item.get("aliases") or []
            if not canonical:
                continue
            alias_map.setdefault(canonical, canonical)
            for alias in aliases:
                if not alias:
                    continue
                alias_map[alias] = canonical

        # schema 中出现过但未在 alias_map 的类，映射到自身
        for cls in schema.classes:
            alias_map.setdefault(cls.name, cls.name)

        # ---- 合并类定义 ----
        normalizer = EntityNormalizer()
        merged_classes: Dict[str, ClassDef] = {}
        for cls in schema.classes:
            canonical_name = alias_map.get(cls.name, cls.name)
            # 简单标准化：地名别名等做归一
            canonical_name = normalizer.normalize(
                canonical_name, "location") if canonical_name else canonical_name

            if canonical_name not in merged_classes:
                merged_classes[canonical_name] = ClassDef(
                    name=canonical_name,
                    cn_name=cls.cn_name,
                    definition=cls.definition,
                    examples=list(cls.examples) if cls.examples else [],
                )
            else:
                exist = merged_classes[canonical_name]
                if (not exist.cn_name) and cls.cn_name:
                    exist.cn_name = cls.cn_name
                if (not exist.definition) and cls.definition:
                    exist.definition = cls.definition

                ex_set = set(exist.examples)
                for ex in cls.examples or []:
                    if ex not in ex_set:
                        exist.examples.append(ex)
                        ex_set.add(ex)

        # ---- 使用 P3 清洗关系 ----
        new_relations: List[RelationDef] = []
        p3_relations = p3_result.get("relations", []) or []
        for rel in p3_relations:
            name = rel.get("name")
            cn_name = rel.get("cn_name")
            domain = rel.get("domain")
            range_ = rel.get("range")
            definition = rel.get("definition")
            functional = rel.get("functional", False)

            if not name or not domain or not range_:
                continue

            canonical_domain = alias_map.get(domain, domain)
            canonical_range = alias_map.get(range_, range_)
            canonical_domain = normalizer.normalize(
                canonical_domain, "location") if canonical_domain else canonical_domain
            canonical_range = normalizer.normalize(
                canonical_range, "location") if canonical_range else canonical_range

            if canonical_domain not in merged_classes or canonical_range not in merged_classes:
                continue

            new_relations.append(
                RelationDef(
                    name=name,
                    cn_name=cn_name or "",
                    domain=canonical_domain,
                    range=canonical_range,
                    definition=definition or "",
                    functional=bool(functional),
                )
            )

        # ---- 规范属性 owner ----
        new_attributes: List[AttributeDef] = []
        for attr in schema.attributes:
            owner = attr.owner
            canonical_owner = alias_map.get(owner, owner)
            canonical_owner = normalizer.normalize(
                canonical_owner, "location") if canonical_owner else canonical_owner
            if canonical_owner not in merged_classes:
                continue
            new_attributes.append(
                AttributeDef(
                    owner=canonical_owner,
                    name=attr.name,
                    cn_name=attr.cn_name,
                    value_type=attr.value_type,
                )
            )

        normalized_schema = TBoxSchema(
            classes=list(merged_classes.values()),
            relations=new_relations,
            attributes=new_attributes,
        )

        if save_path:
            self._dump_json(normalized_schema.to_dict(), save_path)

        return normalized_schema

    # ---------- P4 ----------
    def enhance_schema(self, schema: TBoxSchema, doc_text: str, save_path: Optional[Path] = None) -> Dict[str, Any]:
        """基于文献补充缺失概念/关系。"""
        schema_json = json.dumps(
            schema.to_dict(), ensure_ascii=False, indent=2)
        user_prompt = P4_AUGMENT_PROMPT.format(
            schema_json=schema_json, doc_text=doc_text.strip())
        res = self.client.call("请返回补充建议的 JSON。", user_prompt)
        if save_path:
            self._dump_json(res, save_path)
        return res

    def run_p4_over_corpus(
        self,
        base_schema: TBoxSchema,
        corpus_dir: str,
        pattern: str = "*.txt",
        max_docs: Optional[int] = None,
        save_suggestions_path: Optional[Path] = None,
        save_aug_tbox_path: Optional[Path] = None,
        *,
        min_support: int = 2,
        allow_new_classes: bool = False,
        align_names: bool = False,
        dedup_new: bool = False,
        dedup_threshold: float = 0.8,
    ) -> TBoxSchema:
        """
        在一个文献文件夹上执行“两阶段”P4：
        1) 仅收集所有文献的 suggestions，并统计 _support（出现次数）；
        2) 按支持度/是否允许新增类过滤一次性合入 TBox。
        """
        corpus_path = Path(corpus_dir)
        all_files = sorted(corpus_path.glob(pattern))
        if max_docs is not None:
            all_files = all_files[:max_docs]

        collected: List[Dict[str, Any]] = []
        for idx, fp in enumerate(all_files, start=1):
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                print(f"[WARN] 读取文件失败，跳过: {fp}")
                continue
            if not text.strip():
                print(f"[INFO] 空文件，跳过: {fp}")
                continue
            print(f"[P4] 收集文献 {idx}/{len(all_files)}: {fp.name}")
            try:
                res = self.enhance_schema(base_schema, text)
                sug = res.get("suggestions", []) or []
                for s in sug:
                    s["_source"] = fp.name
                collected.extend(sug)
            except Exception as e:
                print(f"[P4][ERROR] {fp.name}: {e}")
                continue

        # 聚合 _support
        buckets: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
        for s in collected:
            s_type = s.get("type")
            name = s.get("name")
            if not s_type or not name:
                continue
            parent_or_owner = s.get("parent_or_domain_range_or_owner") or s.get(
                "owner") or s.get("domain") or ""
            range_ = s.get("range") or ""
            key = (s_type, name, parent_or_owner, range_)
            if key not in buckets:
                s["_support"] = 1
                buckets[key] = s
            else:
                buckets[key]["_support"] += 1
        aggregated = list(buckets.values())

        if save_suggestions_path:
            save_suggestions_path.parent.mkdir(parents=True, exist_ok=True)
            with save_suggestions_path.open("w", encoding="utf-8") as f:
                json.dump({"suggestions": aggregated},
                          f, ensure_ascii=False, indent=2)

        # 名称对齐（同义归一）
        if align_names:
            aligner = SchemaAligner()
            for s in aggregated:
                if s.get("type") == "class":
                    s["name"] = aligner.align_class_name(s.get("name", ""))
                elif s.get("type") == "relation":
                    s["name"] = aligner.align_relation_name(s.get("name", ""))
                # 仅归一 name；domain/range/owner 不做强映射，避免误对齐

        # 过滤再合并
        filtered: List[Dict[str, Any]] = []
        for s in aggregated:
            sup = int(s.get("_support", 1))
            if sup < min_support:
                continue
            if s.get("type") == "class" and not allow_new_classes:
                continue
            filtered.append(s)

        # 去重：对新增类/关系做向量相似过滤，减少模式膨胀
        if dedup_new and filtered:
            dedup = EmbeddingDeduplicator(threshold=dedup_threshold)
            base_dict = base_schema.to_dict()
            existing_classes = base_dict.get("classes", [])
            existing_rels = base_dict.get("relations", [])
            cand_classes = [s for s in filtered if s.get("type") == "class"]
            cand_rels = [s for s in filtered if s.get("type") == "relation"]
            class_res = dedup.deduplicate_classes(
                existing_classes, cand_classes)
            rel_res = dedup.deduplicate_relations(existing_rels, cand_rels)
            print(
                f"[P4] 去重后保留类 {len(class_res.accepted)} / {len(cand_classes)}，关系 {len(rel_res.accepted)} / {len(cand_rels)}")
            filtered = class_res.accepted + rel_res.accepted + \
                [s for s in filtered if s.get("type") == "attribute"]

        if not filtered:
            if save_aug_tbox_path:
                self._dump_json(base_schema.to_dict(), save_aug_tbox_path)
            return base_schema

        merged = apply_p4_suggestions(base_schema, {"suggestions": filtered})
        if save_aug_tbox_path:
            self._dump_json(merged.to_dict(), save_aug_tbox_path)
        return merged

    # ---------- P5 ----------
    def extract_events(
        self,
        paragraph: str,
        schema: TBoxSchema,
        save_path: Optional[Path] = None,
        favor_existing_classes: bool = True,
        use_cot: bool = False,
    ) -> Dict[str, Any]:
        """
        在 TBox 约束下抽取事件与三元组。
        favor_existing_classes=True 时，提示尽量复用已有类；False 时鼓励使用新增细粒度类。
        use_cot=True 时，使用 CoT Prompt 并解析思维链结果。
        """
        schema_json = json.dumps(
            schema.to_dict(), ensure_ascii=False, indent=2)
        if favor_existing_classes:
            class_usage_hint = "优先使用 TBox 中已有的类名，不要随意创造新的事件类型；倾向用已有类 + 属性表达。"
        else:
            class_usage_hint = "允许充分使用 TBox 中新增的细粒度类（如新补充的 HazardFactor 子类等），鼓励细分事件类型。"

        thought = ""
        if use_cot:
            user_prompt = P5_COT_EXTRACTION_PROMPT.format(
                schema_json=schema_json,
                event_schema=EVENT_SCHEMA_HINT,
                input_text=paragraph.strip(),
                class_usage_hint=class_usage_hint,
            )
            messages = [
                {"role": "system", "content": "你是水旱灾害知识图谱构建专家，请按照思维链格式输出。"},
                {"role": "user", "content": user_prompt},
            ]
            raw_response = self.llm.chat_messages(messages, json_mode=False)
            thought = extract_cot_thought(raw_response)
            res = parse_cot_response(raw_response)
            if res is None:
                logger.warning("[P5] CoT 响应解析失败，返回空结果")
                res = {"events": [], "triples": []}
        else:
            user_prompt = P5_EXTRACTION_PROMPT.format(
                schema_json=schema_json,
                event_schema=EVENT_SCHEMA_HINT,
                input_text=paragraph.strip(),
                class_usage_hint=class_usage_hint,
            )
            res = self.client.call("仅输出 JSON，不要解释。", user_prompt)

        res = self._sanitize_p5_result(res, schema)
        if use_cot and thought:
            res["thought"] = thought
        if save_path:
            self._dump_json(res, save_path)
        return res

    @staticmethod
    def _sanitize_p5_result(res: Any, schema: TBoxSchema) -> Dict[str, Any]:
        """
        对 P5 抽取结果做最小化清洗与约束校验：
        - 保证顶层包含 events/triples
        - 过滤非 dict 元素
        - event_type 不在类集合时回退到 DisasterEvent/首个类（并记录 warning）
        - predicate 不在关系集合时标记 _invalid_predicate=True（不直接丢弃）
        - 补齐关键字段，避免下游评测 KeyError
        """
        if not isinstance(res, dict):
            logger.warning("[P5] LLM 返回非 dict，已置空。")
            return {"events": [], "triples": [], "error": "invalid_response_type"}

        events = res.get("events") if isinstance(res.get("events"), list) else []
        triples = res.get("triples") if isinstance(res.get("triples"), list) else []

        allowed_event_types = {c.name for c in schema.classes if c.name}
        allowed_predicates = {r.name for r in schema.relations if r.name}

        invalid_event_type_count = 0
        cleaned_events: List[Dict[str, Any]] = []
        for event_item in events:
            if not isinstance(event_item, dict):
                continue
            ev = dict(event_item)
            ev.setdefault("event_id", "")
            ev.setdefault("event_type", "")
            ev.setdefault("name", "")
            ev.setdefault("source", "")

            raw_event_type = ev.get("event_type", "")
            ev["original_event_type"] = raw_event_type
            if allowed_event_types and raw_event_type not in allowed_event_types:
                invalid_event_type_count += 1
                ev["_invalid_event_type"] = True
                ev["_is_fallback"] = True
            else:
                ev["_is_fallback"] = False

            time_block = ev.get("time")
            if not isinstance(time_block, dict):
                time_block = {}
            time_block.setdefault("start_time", "")
            time_block.setdefault("end_time", "")
            ev["time"] = time_block

            space_block = ev.get("space")
            if not isinstance(space_block, dict):
                space_block = {}
            for key in ["main_stream", "tributaries", "provinces"]:
                value = space_block.get(key)
                if not isinstance(value, list):
                    space_block[key] = []
            ev["space"] = space_block

            ev.setdefault("causes", [])
            if not isinstance(ev["causes"], list):
                ev["causes"] = []
            impacts_block = ev.get("impacts")
            if not isinstance(impacts_block, dict):
                impacts_block = {}
            impacts_block.setdefault("affected_population", "")
            impacts_block.setdefault("deaths", "")
            impacts_block.setdefault("direct_economic_loss", "")
            ev["impacts"] = impacts_block

            responses_block = ev.get("responses")
            if not isinstance(responses_block, list):
                responses_block = []
            ev["responses"] = responses_block

            cleaned_events.append(ev)

        invalid_predicate_count = 0
        cleaned_triples: List[Dict[str, Any]] = []
        for triple_item in triples:
            if not isinstance(triple_item, dict):
                continue
            tr = dict(triple_item)
            for key in ["subject", "predicate", "object", "event_id", "evidence"]:
                tr.setdefault(key, "")
            if allowed_predicates and tr["predicate"] not in allowed_predicates:
                invalid_predicate_count += 1
                tr["_invalid_predicate"] = True
            cleaned_triples.append(tr)

        if invalid_event_type_count:
            logger.warning(f"[P5] 发现不在 TBox 中的 event_type: {invalid_event_type_count} 个，已标记 _invalid_event_type=True。")
        if invalid_predicate_count:
            logger.warning(f"[P5] 发现不在 TBox 中的 predicate: {invalid_predicate_count} 个，已标记 _invalid_predicate=True。")

        return {"events": cleaned_events, "triples": cleaned_triples}

    # ---------- 工具函数 ----------
    @staticmethod
    def _parse_tbox(data: Dict[str, Any]) -> TBoxSchema:
        """从 LLM 返回的 dict 构造 TBoxSchema（带字段过滤，避免多余键导致报错）。"""

        def pick(d: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
            return {k: d.get(k) for k in keys if k in d}

        class_keys = ["name", "cn_name", "definition", "examples", "parent"]
        rel_keys = ["name", "cn_name", "domain",
                    "range", "definition", "functional"]
        attr_keys = ["owner", "name", "cn_name", "value_type"]

        classes = [
            ClassDef(**pick(c, class_keys))
            for c in data.get("classes", []) or []
            if c.get("name") and c.get("cn_name")
        ]
        relations = [
            RelationDef(**pick(r, rel_keys))
            for r in data.get("relations", []) or []
            if r.get("name") and r.get("domain") and r.get("range")
        ]
        attributes = [
            AttributeDef(**pick(a, attr_keys))
            for a in data.get("attributes", []) or []
            if a.get("owner") and a.get("name")
        ]

        return TBoxSchema(classes=classes, relations=relations, attributes=attributes)

    def _dump_json(self, obj: Any, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    # ---------- 去重辅助 ----------
    @staticmethod
    def deduplicate_tbox(
        schema: TBoxSchema, *, threshold: float = 0.75
    ) -> TBoxSchema:
        """
        使用 embedding 相似度对类/关系去重，减少模式碎片。
        默认仅用于 P2/P3 后的去重，可根据需要调用。
        """
        dedup = EmbeddingDeduplicator(threshold=threshold)
        base_dict = schema.to_dict()
        class_res = dedup.deduplicate_classes([], base_dict.get("classes", []))
        rel_res = dedup.deduplicate_relations(
            [], base_dict.get("relations", []))
        return TBoxSchema(
            classes=[ClassDef(**c) for c in class_res.accepted],
            relations=[RelationDef(**r) for r in rel_res.accepted],
            attributes=schema.attributes,
        )

    # ---------- P5+ 带校验的抽取 ----------
    def extract_events_with_verification(
        self,
        paragraph: str,
        schema: TBoxSchema,
        context_before: str = "",
        context_after: str = "",
        save_path: Optional[Path] = None,
        favor_existing_classes: bool = True,
        use_cot: bool = True,
        strict_filter: bool = True,
        fuzzy_threshold: float = UNIFIED_VERIFICATION_THRESHOLD,
    ) -> Dict[str, Any]:
        """
        带原文回溯校验的知识抽取（P5 + 幻觉过滤）。

        整合 CoT 约束抽取和原文回溯校验，一步完成高质量抽取。
        使用统一的 Prompt 和阈值，确保与 Gold 标注一致。

        流程：
        1. P5: 使用统一的 CoT Prompt 进行分步抽取（或普通 Prompt）
        2. 清洗: 对抽取结果进行基础清洗
        3. 幻觉过滤: 原文回溯校验，过滤不在原文中的实体
        4. 标准化: 对保留的结果进行格式标准化

        Args:
            paragraph: 待抽取文本
            schema: TBox Schema
            context_before: 前文上下文（可选）
            context_after: 后文上下文（可选）
            save_path: 保存路径（可选）
            favor_existing_classes: 是否优先使用现有类
            use_cot: 是否使用 CoT Prompt（默认 True）
            strict_filter: 是否使用严格过滤模式（仅精确匹配）
            fuzzy_threshold: 模糊匹配阈值（默认使用统一阈值 UNIFIED_VERIFICATION_THRESHOLD）

        Returns:
            包含抽取结果和验证统计的字典：
            {
                "events": [...],
                "triples": [...],
                "filtered_triples": [...],
                "hallucination_rate": float,
                "thought": str (CoT 模式下的思考过程),
                "stats": {...}
            }
        """
        logger.info("[P5+] 开始带校验的知识抽取...")

        # 构建输入文本（带上下文标记）
        input_text = self._format_context_input(paragraph, context_before, context_after)

        # 构建 TBox Schema 文本（使用 format_schema_for_prompt）
        tbox_schema = format_schema_for_prompt(schema.to_dict(), style="markdown")

        # 选择 Prompt 模板
        thought = ""
        if use_cot:
            # 使用统一的 CoT Prompt（与 Gold 标注一致）
            user_prompt = UNIFIED_USER_PROMPT_COT.format(
                tbox_schema=tbox_schema,
                text=input_text,
            )
            # CoT 模式需要特殊处理响应
            messages = [
                {"role": "system", "content": UNIFIED_SYSTEM_PROMPT_COT},
                {"role": "user", "content": user_prompt},
            ]
            raw_response = self.llm.chat_messages(messages, json_mode=False)

            # 提取思考过程
            thought = extract_cot_thought(raw_response)

            # 解析 JSON 结果
            res = parse_cot_response(raw_response)
            if res is None:
                logger.warning("[P5+] CoT 响应解析失败，返回空结果")
                res = {"events": [], "triples": []}
        else:
            # 非 CoT 模式使用原有的 P5_EXTRACTION_PROMPT
            schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)
            if favor_existing_classes:
                class_usage_hint = "优先使用 TBox 中已有的类名，不要随意创造新的事件类型；倾向用已有类 + 属性表达。"
            else:
                class_usage_hint = "允许充分使用 TBox 中新增的细粒度类（如新补充的 HazardFactor 子类等），鼓励细分事件类型。"
            user_prompt = P5_EXTRACTION_PROMPT.format(
                schema_json=schema_json,
                event_schema=EVENT_SCHEMA_HINT,
                input_text=input_text,
                class_usage_hint=class_usage_hint,
            )
            res = self.client.call("仅输出 JSON，不要解释。", user_prompt)

        # 清洗 P5 结果
        res = self._sanitize_p5_result(res, schema)

        # 幻觉过滤
        logger.info("[P5+] 执行原文回溯校验...")
        halluc_filter = HallucinationFilter(
            strict_mode=strict_filter,
            fuzzy_threshold=fuzzy_threshold,
            verbose=True
        )

        # 合并主文本和上下文用于验证
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
            "hallucination_rate": verified.hallucination_rate / 100.0,  # 转为 0-1
            "thought": thought,
            "stats": {
                "total_triples": verified.total_triples,
                "valid_triples": verified.valid_count,
                "filtered_triples": verified.filtered_count,
                "hallucination_rate_pct": f"{verified.hallucination_rate:.2f}%",
            },
            "verification_log": verified.verification_log,
        }

        if save_path:
            self._dump_json(result, save_path)

        logger.info(
            f"[P5+] 完成: 事件 {len(result['events'])} 个, "
            f"有效三元组 {verified.valid_count}/{verified.total_triples}, "
            f"幻觉率 {verified.hallucination_rate:.2f}%"
        )

        return result

    def extract_and_fuse(
        self,
        paragraph: str,
        schema: TBoxSchema,
        context_before: str = "",
        context_after: str = "",
        save_path: Optional[Path] = None,
        favor_existing_classes: bool = True,
        use_cot: bool = True,
        strict_filter: bool = True,
        fuzzy_threshold: float = 0.8,
        alias_dict: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        完整的知识抽取与融合流程（P5 + 幻觉过滤 + 知识融合）。

        在 extract_events_with_verification 基础上增加：
        - 实体归一化（使用别名字典）
        - 关系去重（合并相同三元组，统计支持度）

        Args:
            paragraph: 待抽取文本
            schema: TBox Schema
            context_before: 前文上下文
            context_after: 后文上下文
            save_path: 保存路径
            favor_existing_classes: 是否优先使用现有类
            use_cot: 是否使用 CoT Prompt
            strict_filter: 是否严格过滤
            fuzzy_threshold: 模糊匹配阈值
            alias_dict: 自定义别名字典（可选，默认使用内置字典）

        Returns:
            包含融合结果和统计信息的字典：
            {
                "events": [...],
                "triples": [...],  # 融合后的三元组（含 support 字段）
                "filtered_triples": [...],
                "hallucination_rate": float,
                "fusion_stats": {...},
                ...
            }
        """
        # 1. 执行带校验的抽取
        extraction_result = self.extract_events_with_verification(
            paragraph=paragraph,
            schema=schema,
            context_before=context_before,
            context_after=context_after,
            save_path=None,  # 不单独保存中间结果
            favor_existing_classes=favor_existing_classes,
            use_cot=use_cot,
            strict_filter=strict_filter,
            fuzzy_threshold=fuzzy_threshold,
        )

        # 2. 知识融合
        logger.info("[P6] 执行知识融合...")
        valid_triples = extraction_result.get("triples", [])

        if valid_triples:
            fused_triples, fusion_stats = fuse_knowledge(valid_triples, alias_dict)
        else:
            fused_triples = []
            fusion_stats = {
                "entity_merges": 0,
                "original_triple_count": 0,
                "final_triple_count": 0,
                "reduction_rate": 0.0,
            }

        # 3. 组装最终结果
        result = {
            "events": extraction_result.get("events", []),
            "triples": fused_triples,
            "filtered_triples": extraction_result.get("filtered_triples", []),
            "hallucination_rate": extraction_result.get("hallucination_rate", 0.0),
            "thought": extraction_result.get("thought", ""),
            "stats": extraction_result.get("stats", {}),
            "fusion_stats": fusion_stats,
            "verification_log": extraction_result.get("verification_log", []),
        }

        if save_path:
            self._dump_json(result, save_path)

        logger.info(
            f"[P6] 知识融合完成: "
            f"三元组 {fusion_stats.get('original_triple_count', 0)} -> {fusion_stats.get('final_triple_count', 0)}, "
            f"缩减率 {fusion_stats.get('reduction_rate', 0):.1%}"
        )

        return result

    def _format_context_input(self, main: str, before: str, after: str) -> str:
        """
        格式化带上下文标记的输入文本。

        Args:
            main: 主文本（待抽取）
            before: 前文上下文
            after: 后文上下文

        Returns:
            格式化后的文本，包含【前文参考】【待抽取文本】【后文参考】标记
        """
        parts = []

        if before and before.strip():
            parts.append(f"【前文参考】\n{before.strip()}")

        parts.append(f"【待抽取文本】\n{main.strip()}")

        if after and after.strip():
            parts.append(f"【后文参考】\n{after.strip()}")

        return "\n\n".join(parts)


# =========================
# P4 补丁应用函数
# =========================
def apply_p4_suggestions(schema: TBoxSchema, p4_result: Dict[str, Any]) -> TBoxSchema:
    """
    根据 P4_AUGMENT_PROMPT 得到的 suggestions，对现有 TBoxSchema 进行增量补充：
    - 对 type = "class" 的建议：在 classes 中新增或补全类定义；
    - 对 type = "relation" 的建议：在 relations 中新增或补全关系定义；
    - 对 type = "attribute" 的建议：在 attributes 中新增或补全属性定义。
    """
    suggestions: List[Dict[str, Any]] = p4_result.get("suggestions", []) or []

    class_map: Dict[str, ClassDef] = {c.name: c for c in schema.classes}
    rel_map: Dict[str, RelationDef] = {r.name: r for r in schema.relations}
    attr_map: Dict[Tuple[str, str], AttributeDef] = {
        (a.owner, a.name): a for a in schema.attributes}

    def _s(s: Any) -> str:
        return s.strip() if isinstance(s, str) else ""

    for item in suggestions:
        s_type = _s(item.get("type")).lower()
        name = _s(item.get("name"))
        cn_name = _s(item.get("cn_name"))
        definition = _s(item.get("definition"))
        extra = _s(item.get("parent_or_domain_range_or_owner"))
        value_type = _s(item.get("value_type"))

        if not s_type or not name:
            continue

        # ---- 类补充 ----
        if s_type == "class":
            if name in class_map:
                cls = class_map[name]
                if (not cls.cn_name) and cn_name:
                    cls.cn_name = cn_name
                if (not cls.definition) and definition:
                    cls.definition = definition
                # 支持通过 P4 建议补充 parent
                if extra and (not cls.parent):
                    cls.parent = extra
            else:
                class_map[name] = ClassDef(
                    name=name,
                    cn_name=cn_name or name,
                    definition=definition or "",
                    examples=[],
                    parent=extra if extra else None,
                )

        # ---- 关系补充 ----
        elif s_type == "relation":
            domain = ""
            range_ = ""
            if "->" in extra:
                parts = [p.strip() for p in extra.split("->", 1)]
                if len(parts) == 2:
                    domain, range_ = parts[0], parts[1]

            if not domain or not range_:
                continue

            if domain not in class_map:
                class_map[domain] = ClassDef(
                    name=domain, cn_name=domain, definition="", examples=[])
            if range_ not in class_map:
                class_map[range_] = ClassDef(
                    name=range_, cn_name=range_, definition="", examples=[])

            if name in rel_map:
                rel = rel_map[name]
                if (not rel.cn_name) and cn_name:
                    rel.cn_name = cn_name
                if (not rel.definition) and definition:
                    rel.definition = definition
                if (not rel.domain) and domain:
                    rel.domain = domain
                if (not rel.range) and range_:
                    rel.range = range_
            else:
                rel_map[name] = RelationDef(
                    name=name,
                    cn_name=cn_name or name,
                    domain=domain,
                    range=range_,
                    definition=definition or "",
                    functional=False,
                )

        # ---- 属性补充 ----
        elif s_type == "attribute":
            owner = extra
            if not owner:
                continue

            if owner not in class_map:
                class_map[owner] = ClassDef(
                    name=owner, cn_name=owner, definition="", examples=[])

            key = (owner, name)
            if key in attr_map:
                attr = attr_map[key]
                if (not attr.cn_name) and cn_name:
                    attr.cn_name = cn_name
                if (not attr.value_type) and value_type and value_type.lower() != "null":
                    attr.value_type = value_type
            else:
                vt = value_type if value_type and value_type.lower() != "null" else "string"
                attr_map[key] = AttributeDef(
                    owner=owner,
                    name=name,
                    cn_name=cn_name or name,
                    value_type=vt,
                )

    new_schema = TBoxSchema(
        classes=list(class_map.values()),
        relations=list(rel_map.values()),
        attributes=list(attr_map.values()),
    )
    return new_schema


def load_segments_with_context(
    jsonl_path: Path,
    corpus_root: Path,
    context_chars: int = 500,
) -> List[Dict[str, Any]]:
    """
    加载过滤后的片段，并补充上下文。

    Args:
        jsonl_path: light_pool.jsonl 路径
        corpus_root: 原始语料根目录
        context_chars: 上下文字符数

    Returns:
        包含上下文的片段列表
    """
    segments = []
    context_loader = ContextLoader(corpus_root, context_chars)

    # 第一遍：加载所有片段
    with jsonl_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            seg_data = json.loads(line)
            segments.append(seg_data)

    # 构建索引
    # ...（根据需要实现）

    # 第二遍：补充上下文
    enriched = []
    for seg in segments:
        # 如果已有上下文，直接使用
        if seg.get("context_before") or seg.get("context_after"):
            enriched.append(seg)
            continue

        # 否则尝试从文件加载
        # ...
        enriched.append(seg)

    return enriched


def build_extraction_text(
    segment: Dict[str, Any],
    include_context: bool = True,
    max_total_chars: int = 4000,
) -> str:
    """
    构建用于 P5 抽取的文本。

    Args:
        segment: 片段数据
        include_context: 是否包含上下文
        max_total_chars: 最大总字符数

    Returns:
        用于抽取的文本
    """
    main_text = segment.get("text", "")

    if not include_context:
        return main_text[:max_total_chars]

    context_before = segment.get("context_before", "")
    context_after = segment.get("context_after", "")

    # 计算可用空间
    main_len = len(main_text)
    remaining = max_total_chars - main_len

    if remaining <= 0:
        return main_text[:max_total_chars]

    # 分配给前后文
    half = remaining // 2
    before_part = context_before[-half:] if context_before else ""
    after_part = context_after[:half] if context_after else ""

    # 组装
    parts = []
    if before_part:
        parts.append(f"【前文参考】\n{before_part}\n")
    parts.append(f"【待抽取文本】\n{main_text}\n")
    if after_part:
        parts.append(f"【后文参考】\n{after_part}")

    return "\n".join(parts)


# =========================
# 快速演示（与 CQ_Summary 中的示例对应）
# =========================
DEMO_DOMAIN_DESC = """
- 灾害类型：直接影响流域的洪水（流域性洪水、局地暴雨洪水）、干旱、枯水等；
- 灾害阶段：事前预防、监测预警、灾前准备、应急处置、灾后恢复与重建；
- 致灾因子：降水异常、气候背景（水汽条件、厄尔尼诺/拉尼娜等）、水库调度、人类活动等；
- 受灾区域：长江干流与主要支流流域，洞庭湖、鄱阳湖等重要湖泊，沿江省市县及重点功能区（如城市建成区、工业园区）；
- 灾害影响：人员伤亡、经济损失、农田受灾、基础设施和电力供应中断、航运受阻等；
- 脆弱性因素：人口密度、产业结构、防洪（抗旱）工程标准、抗御能力、应急保障水平等；
- 防治与应急措施：预案编制与启动、水库群联合调度、分洪蓄滞洪区运用、堤防加固、人员转移、应急供水与供电等；
- 典型灾害事件：如 1998 年长江特大洪水、2016 年流域性洪水过程、2022 年长江流域特大干旱等。
"""


DEMO_PARAGRAPH_1998 = """
1998年，受流域范围内持续性强降雨和上游来水偏多影响，长江中下游干流水位长期高于警戒，
洞庭湖、鄱阳湖来水显著增加，导致两湖与干流洪水叠加。长江流域发生特大洪水过程，沿江多段堤防超警甚至超保证水位。
此次洪水造成全国受灾人口 2.23 亿人，死亡 4150 人，倒塌房屋 680 万间，直接经济损失约 1660 亿元。
国家先后启动防汛Ⅱ级和Ⅰ级应急响应，启用部分分洪蓄滞洪区，组织数百万人次参与巡堤查险和抢险救援。
"""


def run_quick_demo() -> None:
    """
    演示从已生成文件开始的完整链路：
    P1(已完成) -> P2(已完成) -> P3(已完成) ->
    P3-Norm 规范化 -> P4 文献增强 -> P5 抽取事件。
    """
    pipeline = CQLLMPipeline()
    out_dir = Path("outputs/cq_pipeline/final")

    # ---------- 1. 读取已生成的文件 ----------
    # P1 训练 CQ（仅用于统计）
    with (out_dir / "p1_cqs_train.json").open("r", encoding="utf-8") as f:
        cqs_data = json.load(f).get("cqs", [])
    cqs = [
        CQ(
            id=str(item.get("id", i + 1)),
            question=item["question"],
            category=item.get("category", ""),
        )
        for i, item in enumerate(cqs_data)
        if "question" in item
    ]

    # P2 初始 TBox
    with (out_dir / "p2_tbox_init.json").open("r", encoding="utf-8") as f:
        p2_data = json.load(f)
    tbox_init = CQLLMPipeline._parse_tbox(p2_data)

    # P3 模式整理结果
    with (out_dir / "p3_tbox_refinement.json").open("r", encoding="utf-8") as f:
        p3_result = json.load(f)

    # ---------- 2. P3-Norm：基于 P3 结果规范化 P2 ----------
    tbox_final_before_p4 = pipeline.normalize_tbox_with_p3(
        tbox_init,
        p3_result,
        save_path=out_dir / "p3_tbox_normalized.json",
    )

    # ---------- 3. P4：文献驱动增强 TBox ----------
    # p4_result = pipeline.enhance_schema(
    #     tbox_final_before_p4,
    #     DEMO_PARAGRAPH_1998,
    #     save_path=out_dir / "p4_tbox_enhancement.json",
    # )
    # tbox_final_after_p4 = apply_p4_suggestions(tbox_final_before_p4, p4_result)

    # pipeline._dump_json(
    #     tbox_final_after_p4.to_dict(),
    #     out_dir / "p4_tbox_augmented.json",
    # )

    # ---------- 4. P5：在增强后的 TBox 下抽取事件 ----------
    extraction = pipeline.extract_events(
        DEMO_PARAGRAPH_1998,
        tbox_final_before_p4,
        save_path=out_dir / "p5_events_1998.json",
    )
    # 我的对比实验包括了
    # ---------- 5. 打印信息 ----------
    print(f"P1 训练 CQ 数量: {len(cqs)} 条")

    print(
        f"P2 初始 TBox：类 {len(tbox_init.classes)} 个，关系 {len(tbox_init.relations)} 条")
    print(
        f"P3-Norm 规范化后 TBox：类 {len(tbox_final_before_p4.classes)} 个，关系 {len(tbox_final_before_p4.relations)} 条")
    # print(
    #     f"P4 增强后 TBox：类 {len(tbox_final_after_p4.classes)} 个，关系 {len(tbox_final_after_p4.relations)} 条")
    print(
        f"P5 抽取事件 {len(extraction.get('events', []))} 个，三元组 {len(extraction.get('triples', []))} 条")


if __name__ == "__main__":
    run_quick_demo()
