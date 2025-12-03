"""
Embedding 去重模块（类/关系）：
- 作用：在 P3/P4 规范化或合并阶段，基于向量相似度过滤“重复/同义”候选，减少模式膨胀。
- 用法示例：
    dedup = EmbeddingDeduplicator(threshold=0.75)
    res = dedup.deduplicate_classes(existing_classes, candidate_classes)
    print(res.accepted, res.rejected, res.merge_map)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer


@dataclass
class DeduplicationResult:
    accepted: List[dict]      # 通过去重的候选
    rejected: List[dict]      # 被过滤的候选
    merge_map: Dict[str, str]  # 合并映射 {alias: canonical}


class EmbeddingDeduplicator:
    """基于向量相似度的概念/关系去重器。"""

    def __init__(
        self,
        model_name: str = "BAAI/bge-base-zh-v1.5",
        threshold: float = 0.75,
        device: str = "cpu",
    ):
        self.model = SentenceTransformer(model_name, device=device)
        self.threshold = threshold

    def _encode_texts(self, texts: List[str]):
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)

    def deduplicate_classes(
        self, existing_classes: List[dict], candidate_classes: List[dict]
    ) -> DeduplicationResult:
        """
        对候选类进行去重过滤。
        existing_classes/candidate_classes 元素需至少包含 cn_name / definition / name。
        """
        if not candidate_classes:
            return DeduplicationResult([], [], {})

        accepted, rejected, merge_map = [], [], {}
        base_classes = list(existing_classes) if existing_classes else []
        existing_texts = [f"{c.get('cn_name','')}: {c.get('definition','')}" for c in base_classes]
        existing_embs = self._encode_texts(existing_texts) if existing_texts else None

        for cand in candidate_classes:
            cand_text = f"{cand.get('cn_name','')}: {cand.get('definition','')}"
            cand_emb = self._encode_texts([cand_text])[0]

            if existing_embs is None:
                accepted.append(cand)
                base_classes.append(cand)
                existing_embs = np.expand_dims(cand_emb, axis=0)
                continue

            sims = np.dot(existing_embs, cand_emb)
            max_idx = int(sims.argmax())
            max_sim = float(sims[max_idx])
            if max_sim >= self.threshold:
                canonical = base_classes[max_idx].get("name") or base_classes[max_idx].get("cn_name")
                rejected.append(
                    {**cand, "_rejected_reason": "duplicate", "_similar_to": canonical, "_similarity": max_sim}
                )
                if cand.get("name") and canonical:
                    merge_map[cand["name"]] = canonical
            else:
                accepted.append(cand)
                base_classes.append(cand)
                existing_embs = np.vstack([existing_embs, cand_emb])

        return DeduplicationResult(accepted, rejected, merge_map)

    def deduplicate_relations(
        self, existing_rels: List[dict], candidate_rels: List[dict]
    ) -> DeduplicationResult:
        """
        对候选关系进行去重（考虑 name+domain+range）。
        关系元素应包含 name/cn_name/definition/domain/range。
        """
        if not candidate_rels:
            return DeduplicationResult([], [], {})

        accepted, rejected, merge_map = [], [], {}
        base_rels = list(existing_rels) if existing_rels else []
        existing_texts = [
            f"{r.get('cn_name','')}: {r.get('definition','')} ({r.get('domain','')}->{r.get('range','')})"
            for r in base_rels
        ]
        existing_embs = self._encode_texts(existing_texts) if existing_texts else None

        for cand in candidate_rels:
            cand_text = f"{cand.get('cn_name','')}: {cand.get('definition','')} ({cand.get('domain','')}->{cand.get('range','')})"
            cand_emb = self._encode_texts([cand_text])[0]

            if existing_embs is None:
                accepted.append(cand)
                base_rels.append(cand)
                existing_embs = np.expand_dims(cand_emb, axis=0)
                continue

            sims = np.dot(existing_embs, cand_emb)
            max_idx = int(sims.argmax())
            max_sim = float(sims[max_idx])
            if max_sim >= self.threshold:
                canonical = base_rels[max_idx].get("name")
                rejected.append(
                    {**cand, "_rejected_reason": "duplicate", "_similar_to": canonical, "_similarity": max_sim}
                )
                if cand.get("name") and canonical:
                    merge_map[cand["name"]] = canonical
            else:
                accepted.append(cand)
                base_rels.append(cand)
                existing_embs = np.vstack([existing_embs, cand_emb])

        return DeduplicationResult(accepted, rejected, merge_map)
