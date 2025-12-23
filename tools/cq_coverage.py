"""
CQ 覆盖度评估：基于句向量计算 TBox 对能力问题的覆盖程度。
增强点：
- 类/关系文本描述包含 name/cn_name/definition 及 domain→range，语义更完整。
- 支持传入 dict/list/字符串混合的 CQ，自动提取 question 字段。
- 多阈值统计覆盖率，同时返回平均最大相似度与未覆盖样例。
- 概念覆盖评估（按概念列表而非整问句），便于细粒度分析。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

try:
    from sentence_transformers import SentenceTransformer

    HAS_ST = True
except ImportError:
    HAS_ST = False


class CQCoverageEvaluator:
    """基于 CQ 的本体覆盖度评估器。"""

    def __init__(self, model_name: str = "BAAI/bge-base-zh-v1.5", device: str = "cpu"):
        if not HAS_ST:
            raise ImportError("请安装 sentence-transformers: pip install sentence-transformers")
        self.model = SentenceTransformer(model_name, device=device)
        self.model_name = model_name

    @staticmethod
    def _extract_question(item: Any) -> str:
        """从 dict/list/str 中提取 question 文本。"""
        if isinstance(item, dict):
            return str(item.get("question", "") or item.get("text", "")).strip()
        return str(item).strip()

    def _build_tbox_texts(
        self,
        tbox: Dict[str, Any],
        *,
        text_mode: str = "full",
        include_relations: bool = True,
        include_attributes: bool = True,
        include_parent: bool = True,
        include_relation_signature: bool = True,
        include_attribute_owner_type: bool = True,
    ) -> List[str]:
        """
        将 TBox 类/关系/属性转为文本，用于向量化。

        Args:
            text_mode:
              - "label": 仅标签（cn_name/name）
              - "definition": 仅定义（definition）
              - "label+definition": 标签+定义
              - "full": 保持向后兼容的“富语义”表示（默认）
            include_relations: 是否纳入 relations
            include_attributes: 是否纳入 attributes
            include_parent: 类文本中是否附带 parent（full 默认开启）
            include_relation_signature: 关系文本中是否附带 domain→range（full 默认开启）
            include_attribute_owner_type: 属性文本中是否附带 owner/type（full 默认开启）
        """

        mode = (text_mode or "full").strip().lower()
        if mode not in {"label", "definition", "label+definition", "full"}:
            mode = "full"

        def build_label(name: str, cn_name: str) -> str:
            if cn_name and name:
                return f"{cn_name}（{name}）"
            return cn_name or name

        texts: List[str] = []
        for c in tbox.get("classes", []) or []:
            name = c.get("name", "")
            cn_name = c.get("cn_name", "")
            definition = c.get("definition", "")
            parent = c.get("parent") or c.get("parent_class") or ""
            label = build_label(name, cn_name)

            if mode == "label":
                text = label
            elif mode == "definition":
                text = definition
            elif mode == "label+definition":
                text = f"{label}: {definition}".strip(": ").strip()
            else:
                parent_part = f" [parent={parent}]" if (include_parent and parent) else ""
                text = f"{label}: {definition}{parent_part}".strip()

            if text and text.strip() and text.strip() != ":":
                texts.append(text)

        if include_relations:
            for r in tbox.get("relations", []) or []:
                name = r.get("name", "")
                cn_name = r.get("cn_name", "")
                definition = r.get("definition", "")
                domain = r.get("domain", "")
                range_ = r.get("range", "")
                label = build_label(name, cn_name)

                if mode == "label":
                    text = label
                elif mode == "definition":
                    text = definition
                elif mode == "label+definition":
                    text = f"{label}: {definition}".strip(": ").strip()
                else:
                    sig = f" [{domain}→{range_}]" if (include_relation_signature and (domain or range_)) else ""
                    text = f"{label}: {definition}{sig}".strip()

                if text and text.strip() and text.strip() != ":":
                    texts.append(text)

        if include_attributes:
            for a in tbox.get("attributes", []) or []:
                owner = a.get("owner", "")
                name = a.get("name", "")
                cn_name = a.get("cn_name", "")
                vtype = a.get("value_type", "")
                label = build_label(name, cn_name)

                if mode == "label":
                    text = label
                elif mode == "definition":
                    text = ""
                elif mode == "label+definition":
                    text = label
                else:
                    suffix = f": owner={owner}, type={vtype}" if include_attribute_owner_type else ""
                    text = f"{label}{suffix}".strip()

                if text and text.strip() and text.strip() != ":":
                    texts.append(text)
        return texts

    def evaluate(
        self,
        test_cqs: Any,
        tbox: Dict[str, Any],
        thresholds: Optional[List[float]] = None,
        *,
        text_mode: str = "full",
        include_relations: bool = True,
        include_attributes: bool = True,
        include_parent: bool = True,
        include_relation_signature: bool = True,
        include_attribute_owner_type: bool = True,
    ) -> Dict[float, Dict[str, Any]]:
        """
        评估 TBox 对测试 CQ 的覆盖度。
        Args:
            test_cqs: 可以是 list[dict|str] 或 dict 含 cqs 字段
            tbox: TBox 字典
            thresholds: 相似度阈值列表
        """
        if thresholds is None:
            thresholds = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]

        # 标准化 CQ 列表
        if isinstance(test_cqs, dict) and "cqs" in test_cqs:
            test_cqs = test_cqs.get("cqs", [])
        if not isinstance(test_cqs, list):
            test_cqs = [test_cqs]

        questions = [self._extract_question(cq) for cq in test_cqs if self._extract_question(cq)]

        tbox_texts = self._build_tbox_texts(
            tbox,
            text_mode=text_mode,
            include_relations=include_relations,
            include_attributes=include_attributes,
            include_parent=include_parent,
            include_relation_signature=include_relation_signature,
            include_attribute_owner_type=include_attribute_owner_type,
        )
        if not tbox_texts or not questions:
            return {
                t: {
                    "cq_coverage": 0.0,
                    "avg_max_similarity": 0.0,
                    "covered_count": 0,
                    "total_count": len(questions),
                }
                for t in thresholds
            }

        tbox_embs = self.model.encode(tbox_texts, normalize_embeddings=True, show_progress_bar=False)

        all_max_sims: List[float] = []
        cq_details: List[Dict[str, Any]] = []

        for q in questions:
            q_emb = self.model.encode([q], normalize_embeddings=True, show_progress_bar=False)[0]
            similarities = np.dot(tbox_embs, q_emb)
            max_idx = int(similarities.argmax())
            max_sim = float(similarities[max_idx])
            all_max_sims.append(max_sim)
            cq_details.append(
                {
                    "question": q,
                    "max_similarity": round(max_sim, 4),
                    "best_match": tbox_texts[max_idx] if tbox_texts else "",
                }
            )

        if not all_max_sims:
            return {
                t: {
                    "cq_coverage": 0.0,
                    "avg_max_similarity": 0.0,
                    "covered_count": 0,
                    "total_count": 0,
                }
                for t in thresholds
            }

        avg_sim = float(np.mean(all_max_sims))
        results: Dict[float, Dict[str, Any]] = {}
        total = len(cq_details)
        for t in thresholds:
            covered = [d for d in cq_details if d["max_similarity"] >= t]
            uncovered = [d for d in cq_details if d["max_similarity"] < t]
            results[t] = {
                "cq_coverage": round(len(covered) / total, 4),
                "avg_max_similarity": round(avg_sim, 4),
                "covered_count": len(covered),
                "total_count": total,
                "uncovered_samples": uncovered[:5],
            }
        return results

    def evaluate_concepts(
        self, concepts: List[str], tbox: Dict[str, Any], threshold: float = 0.5
    ) -> Dict[str, Any]:
        """
        针对概念列表评估覆盖度（细粒度分析）。
        """
        tbox_texts = self._build_tbox_texts(tbox)
        if not tbox_texts or not concepts:
            return {"coverage": 0.0, "covered": [], "uncovered": concepts}

        tbox_embs = self.model.encode(tbox_texts, normalize_embeddings=True, show_progress_bar=False)
        covered, uncovered = [], []
        for concept in concepts:
            c_emb = self.model.encode([concept], normalize_embeddings=True, show_progress_bar=False)[0]
            max_sim = float(np.dot(tbox_embs, c_emb).max())
            if max_sim >= threshold:
                covered.append({"concept": concept, "similarity": round(max_sim, 4)})
            else:
                uncovered.append({"concept": concept, "similarity": round(max_sim, 4)})

        return {
            "coverage": round(len(covered) / len(concepts), 4) if concepts else 0.0,
            "covered": covered,
            "uncovered": uncovered,
        }
