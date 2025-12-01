"""
CQ 驱动的长江灾害知识图谱构建流水线（P1~P5）。

核心思想：以能力问题 (CQ) 反推 TBox，再在 TBox 约束下抽取 ABox。
Prompt 设计、伪代码与示例均与 ``summary/CQ_Summary.txt`` 对齐，方便论文复现。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .llm_core import LLMFactory, LLMBackend
from .prompts import (
    P1_CQ_PROMPT,
    P2_SCHEMA_PROMPT,
    P3_REFINEMENT_PROMPT,
    P4_AUGMENT_PROMPT,
    P5_EXTRACTION_PROMPT,
    EVENT_SCHEMA_HINT,
)


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
        cleaned = self._strip_code_fence(raw)
        if not cleaned:
            return {}
        try:
            obj = json.loads(cleaned)
        except Exception:
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
        merged_classes: Dict[str, ClassDef] = {}
        for cls in schema.classes:
            canonical_name = alias_map.get(cls.name, cls.name)

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
    ) -> TBoxSchema:
        """
        在一个文献文件夹上迭代执行 P4：
        - corpus_dir: 文献所在目录，每个文件视为一篇文献（建议事先切好段落/摘要）；
        - pattern: 文件通配符，如 '*.txt'；
        - max_docs: 若不为 None，则只处理前 max_docs 个文件，用于快速实验。

        返回：增强后的 TBoxSchema。
        """
        corpus_path = Path(corpus_dir)
        all_files = sorted(corpus_path.glob(pattern))
        if max_docs is not None:
            all_files = all_files[:max_docs]

        current_schema = base_schema
        all_suggestions: List[Dict[str, Any]] = []

        for idx, fp in enumerate(all_files, start=1):
            try:
                text = fp.read_text(encoding="utf-8")
            except Exception:
                print(f"[WARN] 读取文件失败，跳过: {fp}")
                continue

            if not text.strip():
                print(f"[INFO] 空文件，跳过: {fp}")
                continue

            print(f"[P4] 处理文献 {idx}/{len(all_files)}: {fp.name}")

            # 对当前 schema + 单篇文献做 P4
            p4_result = self.enhance_schema(current_schema, text)
            suggestions = p4_result.get("suggestions", []) or []
            if not suggestions:
                continue

            all_suggestions.extend(suggestions)

            # 把本篇文献的补充合入当前 schema（迭代进化）
            current_schema = apply_p4_suggestions(current_schema, p4_result)

        # 统一保存 suggestions 和增强后的 TBox
        if save_suggestions_path:
            save_suggestions_path.parent.mkdir(parents=True, exist_ok=True)
            with save_suggestions_path.open("w", encoding="utf-8") as f:
                json.dump({"suggestions": all_suggestions},
                          f, ensure_ascii=False, indent=2)

        if save_aug_tbox_path:
            self._dump_json(current_schema.to_dict(), save_aug_tbox_path)

        return current_schema

    # ---------- P5 ----------
    def extract_events(self, paragraph: str, schema: TBoxSchema, save_path: Optional[Path] = None) -> Dict[str, Any]:
        """在 TBox 约束下抽取事件与三元组。"""
        schema_json = json.dumps(
            schema.to_dict(), ensure_ascii=False, indent=2)
        user_prompt = P5_EXTRACTION_PROMPT.format(
            schema_json=schema_json,
            event_schema=EVENT_SCHEMA_HINT,
            paragraph=paragraph.strip(),
        )
        res = self.client.call("仅输出 JSON，不要解释。", user_prompt)
        if save_path:
            self._dump_json(res, save_path)
        return res

    # ---------- 工具函数 ----------
    @staticmethod
    def _parse_tbox(data: Dict[str, Any]) -> TBoxSchema:
        """从 LLM 返回的 dict 构造 TBoxSchema（带字段过滤，避免多余键导致报错）。"""

        def pick(d: Dict[str, Any], keys: List[str]) -> Dict[str, Any]:
            return {k: d.get(k) for k in keys if k in d}

        class_keys = ["name", "cn_name", "definition", "examples"]
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
            else:
                class_map[name] = ClassDef(
                    name=name,
                    cn_name=cn_name or name,
                    definition=definition or "",
                    examples=[],
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
