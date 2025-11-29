"""
CQ 驱动的长江灾害知识图谱构建流水线（P1~P5）。

核心思想：以能力问题 (CQ) 反推 TBox，再在 TBox 约束下抽取 ABox。
Prompt 设计、伪代码与示例均与 ``summary/CQ_Summary.txt`` 对齐，方便论文复现。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional

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
    theme: str
    question: str


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
        try:
            return json.loads(cleaned) if cleaned else {}
        except Exception:
            # 解析失败时返回空 dict，避免上游崩溃
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

    def __init__(self, llm_config: Optional[Dict[str, Any]] = None, output_dir: str = "outputs/cq_pipeline"):
        config = llm_config or {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "temperature": 0.1,
        }
        self.llm = LLMFactory.create(config)
        self.client = LLMJsonClient(self.llm)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ---------- P1 ----------
    def generate_cqs(self, domain_desc: str, n_cq: int = 30, save_path: Optional[Path] = None) -> List[CQ]:
        """从领域说明生成 CQ 列表。"""
        user_prompt = P1_CQ_PROMPT.format(domain_desc=domain_desc, n_cq=n_cq)
        res = self.client.call("只输出 JSON，字段按提示填写。", user_prompt)
        cqs = [CQ(**item) for item in res.get("cqs", [])]
        if save_path:
            self._dump_json({"cqs": [asdict(cq) for cq in cqs]}, save_path)
        return cqs

    # ---------- P2 ----------
    def cq_to_schema(self, cqs: List[CQ], save_path: Optional[Path] = None) -> TBoxSchema:
        """根据 CQ 归纳初始 TBox。"""
        cq_json = json.dumps({"cqs": [asdict(c) for c in cqs]}, ensure_ascii=False, indent=2)
        user_prompt = P2_SCHEMA_PROMPT.format(cq_json=cq_json)
        res = self.client.call("你是本体工程师，请严格输出 JSON。", user_prompt)
        schema = self._parse_tbox(res)
        if save_path:
            self._dump_json(schema.to_dict(), save_path)
        return schema

    # ---------- P3 ----------
    def refine_schema(self, schema: TBoxSchema, save_path: Optional[Path] = None) -> Dict[str, Any]:
        """对初始模式进行合并、层次化整理。"""
        schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)
        user_prompt = P3_REFINEMENT_PROMPT.format(schema_json=schema_json)
        res = self.client.call("请清洗模式并输出 JSON。", user_prompt)
        if save_path:
            self._dump_json(res, save_path)
        return res

    # ---------- P4 ----------
    def enhance_schema(self, schema: TBoxSchema, doc_text: str, save_path: Optional[Path] = None) -> Dict[str, Any]:
        """基于文献补充缺失概念/关系。"""
        schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)
        user_prompt = P4_AUGMENT_PROMPT.format(schema_json=schema_json, doc_text=doc_text.strip())
        res = self.client.call("请返回补充建议的 JSON。", user_prompt)
        if save_path:
            self._dump_json(res, save_path)
        return res

    # ---------- P5 ----------
    def extract_events(self, paragraph: str, schema: TBoxSchema, save_path: Optional[Path] = None) -> Dict[str, Any]:
        """在 TBox 约束下抽取事件与三元组。"""
        schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)
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
        """从 LLM 返回的 dict 构造 TBoxSchema。"""
        classes = [ClassDef(**c) for c in data.get("classes", [])]
        relations = [RelationDef(**r) for r in data.get("relations", [])]
        attributes = [AttributeDef(**a) for a in data.get("attributes", [])]
        return TBoxSchema(classes=classes, relations=relations, attributes=attributes)

    def _dump_json(self, obj: Any, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)


# =========================
# 快速演示（与 CQ_Summary 中的示例对应）
# =========================
DEMO_DOMAIN_DESC = """
长江流域是我国重要的水资源与生态安全屏障，也是水旱灾害的高风险区。
典型灾害事件包括：1954、1998 特大洪水，2011 大旱，2022“伏秋连旱”等。
致灾因子包括：流域尺度持续性强降雨、上游来水偏多、厄尔尼诺/拉尼娜事件、河道侵占、湖泊萎缩等。
防治措施包括：水库群联合调度、预报预警、分洪蓄滞洪区运用、堤防加固、预案启动和应急响应。
管理体系包括：水利部、长江水利委员会、地方防汛抗旱指挥部、水文局等。
"""

DEMO_PARAGRAPH_1998 = """
1998年，受流域范围内持续性强降雨和上游来水偏多影响，长江中下游干流水位长期高于警戒，
洞庭湖、鄱阳湖来水显著增加，导致两湖与干流洪水叠加。长江流域发生特大洪水过程，沿江多段堤防超警甚至超保证水位。
此次洪水造成全国受灾人口 2.23 亿人，死亡 4150 人，倒塌房屋 680 万间，直接经济损失约 1660 亿元。
国家先后启动防汛Ⅱ级和Ⅰ级应急响应，启用部分分洪蓄滞洪区，组织数百万人次参与巡堤查险和抢险救援。
"""


def run_quick_demo() -> None:
    """
    演示最小链路：P1 -> P2 -> P5。
    说明：
    * 默认使用 OpenAI 兼容接口，需提前设置 OPENAI_API_KEY；
    * 输出会写入 outputs/cq_pipeline 目录。
    """
    pipeline = CQLLMPipeline()
    out_dir = Path("outputs/cq_pipeline")

    cqs = pipeline.generate_cqs(DEMO_DOMAIN_DESC, n_cq=10, save_path=out_dir / "p1_cqs.json")
    tbox = pipeline.cq_to_schema(cqs, save_path=out_dir / "p2_tbox_init.json")
    extraction = pipeline.extract_events(
        DEMO_PARAGRAPH_1998,
        tbox,
        save_path=out_dir / "p5_events_1998.json",
    )
    print(f"P1 生成 {len(cqs)} 条 CQ，TBox 类 {len(tbox.classes)} 个，关系 {len(tbox.relations)} 条。")
    print(f"P5 抽取事件 {len(extraction.get('events', []))} 个，三元组 {len(extraction.get('triples', []))} 条。")


if __name__ == "__main__":
    run_quick_demo()
