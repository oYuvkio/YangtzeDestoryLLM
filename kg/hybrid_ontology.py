"""
专家引导 + 语料聚类的混合本体构建模块。

流程：
1) 加载专家骨架（anchor）
2) 语料挖掘 + 聚类发现新类/关系
3) 聚类结果与专家骨架融合
4) 支持度 / 置信度筛选
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from sentence_transformers import SentenceTransformer
import jieba

from kg.llm_core import LLMFactory
from kg.cq_pipeline import LLMJsonClient
from kg.prompts import (
    HYBRID_VOCAB_MINING_PROMPT,
    HYBRID_CLUSTER_LABEL_PROMPT,
    HYBRID_RELATION_LABEL_PROMPT,
)

logger = logging.getLogger(__name__)


def _safe_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _normalize_type_list(value: Any) -> List[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(v).strip() for v in value if str(v).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


@dataclass
class ClusterResult:
    entity_clusters: Dict[str, Dict[str, Any]]
    relation_clusters: Dict[str, Dict[str, Any]]
    entity_freq: Dict[str, int]
    relation_freq: Dict[str, int]


class CorpusClusteringMiner:
    """语料聚类挖掘器"""

    def __init__(
        self,
        llm_client: LLMJsonClient,
        embedding_model: SentenceTransformer,
        config: Dict[str, Any],
        class_candidates: Optional[List[str]] = None,
    ):
        self.client = llm_client
        self.embedding_model = embedding_model
        self.class_candidates = class_candidates or []

        self.min_freq = int(config.get("min_freq", 3))
        self.n_clusters_entity = int(config.get("n_clusters_entity", 15))
        self.n_clusters_relation = int(config.get("n_clusters_relation", 12))
        self.dice_threshold = float(config.get("dice_threshold", 0.5))
        self.batch_size = int(config.get("batch_size", 5))
        self.max_label_members = int(config.get("max_label_members", 15))

    def mine_and_cluster(
        self,
        texts: List[str],
        doc_ids: Optional[List[str]] = None,
        progress_path: Optional[Path] = None,
        resume: bool = False,
    ) -> ClusterResult:
        """挖掘词汇并聚类"""
        vocab = self._mine_vocabulary(
            texts,
            doc_ids=doc_ids,
            progress_path=progress_path,
            resume=resume,
        )
        entities = vocab["entities"]
        relations = vocab["relations"]

        entity_embeddings = self._get_embeddings(entities)
        relation_embeddings = self._get_embeddings(relations)

        entity_clusters = self._cluster(entities, entity_embeddings, self.n_clusters_entity)
        relation_clusters = self._cluster(relations, relation_embeddings, self.n_clusters_relation)

        entity_clusters = self._merge_similar_clusters(entity_clusters)
        relation_clusters = self._merge_similar_clusters(relation_clusters)

        labeled_entities = self._label_clusters(entity_clusters, "entity")
        labeled_relations = self._label_clusters(relation_clusters, "relation")

        return ClusterResult(
            entity_clusters=labeled_entities,
            relation_clusters=labeled_relations,
            entity_freq=vocab["entity_freq"],
            relation_freq=vocab["relation_freq"],
        )

    def _mine_vocabulary(
        self,
        texts: List[str],
        doc_ids: Optional[List[str]] = None,
        progress_path: Optional[Path] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        """基于 LLM 的词汇挖掘"""
        entity_freq: Counter = Counter()
        relation_freq: Counter = Counter()

        if doc_ids is None or len(doc_ids) != len(texts):
            doc_ids = [f"doc_{idx}" for idx in range(len(texts))]

        if progress_path:
            progress_path = Path(progress_path)
            progress_path.parent.mkdir(parents=True, exist_ok=True)

            processed_ids: set[str] = set()
            if resume and progress_path.exists():
                with progress_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        doc_id = str(record.get("doc_id", "")).strip()
                        if not doc_id or record.get("error"):
                            continue
                        processed_ids.add(doc_id)
                        entity_freq.update(_safe_list(record.get("entities")))
                        relation_freq.update(_safe_list(record.get("relations")))

                logger.info("词汇挖掘断点续跑启用，已处理样本数: %d", len(processed_ids))

            write_mode = "a" if resume and progress_path.exists() else "w"
            with progress_path.open(write_mode, encoding="utf-8") as out_f:
                for idx, (doc_id, text) in enumerate(zip(doc_ids, texts), start=1):
                    if resume and doc_id in processed_ids:
                        continue
                    if not text:
                        continue

                    user_prompt = HYBRID_VOCAB_MINING_PROMPT.format(batch_text=text)
                    try:
                        res = self.client.call("仅输出 JSON。", user_prompt)
                        entities = _safe_list(res.get("entities"))
                        relations = _safe_list(res.get("relations"))
                        entity_freq.update(entities)
                        relation_freq.update(relations)
                        record = {
                            "doc_id": doc_id,
                            "text_len": len(text),
                            "entities": entities,
                            "relations": relations,
                        }
                    except Exception as exc:
                        logger.warning("词汇挖掘失败: %s", exc)
                        record = {
                            "doc_id": doc_id,
                            "text_len": len(text),
                            "entities": [],
                            "relations": [],
                            "error": str(exc),
                        }

                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_f.flush()

                    if idx % 50 == 0:
                        logger.info("词汇挖掘进度: %d/%d", idx, len(texts))
        else:
            all_entities: List[str] = []
            all_relations: List[str] = []

            for i in range(0, len(texts), self.batch_size):
                batch = texts[i:i + self.batch_size]
                batch_text = "\n---\n".join(batch)
                user_prompt = HYBRID_VOCAB_MINING_PROMPT.format(batch_text=batch_text)
                try:
                    res = self.client.call("仅输出 JSON。", user_prompt)
                except Exception as exc:
                    logger.warning("词汇挖掘失败，跳过该批次: %s", exc)
                    continue

                all_entities.extend(_safe_list(res.get("entities")))
                all_relations.extend(_safe_list(res.get("relations")))

            entity_freq = Counter(all_entities)
            relation_freq = Counter(all_relations)

        entities = [w for w, c in entity_freq.items() if c >= self.min_freq]
        relations = [w for w, c in relation_freq.items() if c >= self.min_freq]

        return {
            "entities": entities,
            "relations": relations,
            "entity_freq": dict(entity_freq),
            "relation_freq": dict(relation_freq),
        }

    def _get_embeddings(self, words: List[str]) -> np.ndarray:
        if not words:
            return np.array([])
        return self.embedding_model.encode(words, normalize_embeddings=True, show_progress_bar=False)

    def _cluster(self, words: List[str], embeddings: np.ndarray, n_clusters: int) -> Dict[int, List[str]]:
        if not words:
            return {}
        if len(words) <= n_clusters:
            return {idx: [word] for idx, word in enumerate(words)}

        best_k = self._find_optimal_k(embeddings, min(n_clusters, len(words) - 1))
        kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)

        clusters: Dict[int, List[str]] = {}
        for word, label in zip(words, labels):
            clusters.setdefault(int(label), []).append(word)
        return clusters

    def _find_optimal_k(self, embeddings: np.ndarray, max_k: int) -> int:
        if len(embeddings) <= 2:
            return min(2, len(embeddings))
        best_k = 2
        best_score = -1.0
        for k in range(2, min(max_k + 1, len(embeddings))):
            try:
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = kmeans.fit_predict(embeddings)
                score = silhouette_score(embeddings, labels)
                if score > best_score:
                    best_score = score
                    best_k = k
            except Exception:
                continue
        return best_k

    def _build_token_set(self, members: List[str]) -> set:
        tokens = set()
        for m in members:
            try:
                tokens.update([t for t in jieba.lcut(m) if t.strip()])
            except Exception:
                tokens.update([c for c in m if c.strip()])
        return tokens

    def _merge_similar_clusters(self, clusters: Dict[int, List[str]]) -> Dict[int, List[str]]:
        if not clusters:
            return {}
        cluster_ids = list(clusters.keys())
        merged: Dict[int, List[str]] = {}
        used = set()

        for i, cid1 in enumerate(cluster_ids):
            if cid1 in used:
                continue
            members = list(clusters[cid1])
            token_set = self._build_token_set(members)
            used.add(cid1)

            for cid2 in cluster_ids[i + 1:]:
                if cid2 in used:
                    continue
                token_set_2 = self._build_token_set(clusters[cid2])
                if not token_set or not token_set_2:
                    continue
                intersection = len(token_set & token_set_2)
                dice = (2 * intersection) / (len(token_set) + len(token_set_2))
                if dice >= self.dice_threshold:
                    members.extend(clusters[cid2])
                    token_set.update(token_set_2)
                    used.add(cid2)

            merged[len(merged)] = members

        return merged

    def _label_clusters(self, clusters: Dict[int, List[str]], cluster_type: str) -> Dict[str, Dict[str, Any]]:
        labeled: Dict[str, Dict[str, Any]] = {}
        type_hint = "实体类型" if cluster_type == "entity" else "关系类型"

        for cluster_id, members in clusters.items():
            members_sample = ", ".join(members[: self.max_label_members])
            if cluster_type == "relation":
                prompt = HYBRID_RELATION_LABEL_PROMPT.format(
                    class_candidates=", ".join(self.class_candidates),
                    members=members_sample,
                )
            else:
                prompt = HYBRID_CLUSTER_LABEL_PROMPT.format(
                    type_hint=type_hint,
                    members=members_sample,
                )
            try:
                result = self.client.call("仅输出 JSON。", prompt)
            except Exception as exc:
                logger.warning("聚类标签生成失败: %s", exc)
                result = {}

            label = result.get("label") or f"CLUSTER_{cluster_id}"
            info = {
                "label_cn": result.get("label_cn", ""),
                "description": result.get("description", ""),
                "members": members,
                "source": "clustering",
            }

            if cluster_type == "relation":
                domain = _safe_list(result.get("domain"))
                range_ = _safe_list(result.get("range"))
                if self.class_candidates:
                    domain = [d for d in domain if d in self.class_candidates]
                    range_ = [r for r in range_ if r in self.class_candidates]
                info["domain"] = domain
                info["range"] = range_

            labeled[label] = info

        return labeled


class HybridFusion:
    """混合融合器"""

    def __init__(self, embedding_model: SentenceTransformer, similarity_threshold: float = 0.75):
        self.embedding_model = embedding_model
        self.similarity_threshold = similarity_threshold

    def fuse(self, expert_tbox: Dict[str, Any], clustering_result: ClusterResult) -> Dict[str, Any]:
        fused_classes = self._fuse_classes(expert_tbox.get("classes", []), clustering_result.entity_clusters)
        fused_relations = self._fuse_relations(expert_tbox.get("relations", []), clustering_result.relation_clusters)
        return {
            "classes": fused_classes,
            "relations": fused_relations,
            "attributes": expert_tbox.get("attributes", []),
        }

    def _fuse_classes(self, expert_classes: List[Dict[str, Any]], clustered_classes: Dict[str, Dict[str, Any]]):
        fused: List[Dict[str, Any]] = []
        used_clusters = set()

        for cls in expert_classes:
            cls = dict(cls)
            cls.setdefault("is_anchor", True)
            cls.setdefault("examples", [])

            for label, cluster in clustered_classes.items():
                if label in used_clusters:
                    continue
                sim = self._compute_similarity(
                    cls.get("name", ""),
                    cls.get("definition", ""),
                    cls.get("examples", []),
                    label,
                    cluster.get("description", ""),
                    cluster.get("members", []),
                )
                if sim >= self.similarity_threshold:
                    existing = set(cls.get("examples", []))
                    new_examples = cluster.get("members", [])[:10]
                    cls["examples"] = list(existing | set(new_examples))[:15]
                    cls["merged_from_clustering"] = label
                    used_clusters.add(label)
                    break

            fused.append(cls)

        for label, cluster in clustered_classes.items():
            if label in used_clusters:
                continue
            fused.append(
                {
                    "name": label,
                    "cn_name": cluster.get("label_cn", ""),
                    "definition": cluster.get("description", ""),
                    "examples": cluster.get("members", [])[:10],
                    "parent": None,
                    "is_anchor": False,
                    "source": "clustering",
                }
            )
        return fused

    def _fuse_relations(self, expert_relations: List[Dict[str, Any]], clustered_relations: Dict[str, Dict[str, Any]]):
        fused: List[Dict[str, Any]] = []
        used_clusters = set()

        for rel in expert_relations:
            rel = dict(rel)
            rel.setdefault("is_anchor", True)
            rel.setdefault("examples", [])

            for label, cluster in clustered_relations.items():
                if label in used_clusters:
                    continue
                sim = self._compute_relation_similarity(
                    rel.get("name", ""),
                    rel.get("definition", ""),
                    label,
                    cluster.get("description", ""),
                    cluster.get("members", []),
                )
                if sim >= self.similarity_threshold:
                    existing = set(rel.get("examples", []))
                    new_examples = cluster.get("members", [])[:5]
                    rel["examples"] = list(existing | set(new_examples))[:10]
                    rel["merged_from_clustering"] = label
                    used_clusters.add(label)
                    break

            fused.append(rel)

        for label, cluster in clustered_relations.items():
            if label in used_clusters:
                continue
            fused.append(
                {
                    "name": label,
                    "cn_name": cluster.get("label_cn", ""),
                    "definition": cluster.get("description", ""),
                    "domain": cluster.get("domain", []),
                    "range": cluster.get("range", []),
                    "examples": cluster.get("members", [])[:5],
                    "functional": False,
                    "is_anchor": False,
                    "source": "clustering",
                }
            )
        return fused

    def _compute_similarity(
        self,
        expert_name: str,
        expert_desc: str,
        expert_examples: List[str],
        cluster_label: str,
        cluster_desc: str,
        cluster_members: List[str],
    ) -> float:
        expert_text = f"{expert_name} {expert_desc} {' '.join(expert_examples[:5])}"
        cluster_text = f"{cluster_label} {cluster_desc} {' '.join(cluster_members[:5])}"
        embeddings = self.embedding_model.encode([expert_text, cluster_text], normalize_embeddings=True)
        return float(np.dot(embeddings[0], embeddings[1]))

    def _compute_relation_similarity(
        self,
        expert_name: str,
        expert_desc: str,
        cluster_label: str,
        cluster_desc: str,
        cluster_members: List[str],
    ) -> float:
        expert_text = f"{expert_name} {expert_desc}"
        cluster_text = f"{cluster_label} {cluster_desc} {' '.join(cluster_members[:3])}"
        embeddings = self.embedding_model.encode([expert_text, cluster_text], normalize_embeddings=True)
        return float(np.dot(embeddings[0], embeddings[1]))


class QualityFilter:
    """支持度 / 置信度筛选"""

    def __init__(self, config: Dict[str, Any]):
        self.min_support = int(config.get("min_support", 5))
        self.min_confidence = float(config.get("min_confidence", 0.3))
        self.protect_anchors = bool(config.get("protect_anchors", True))

    def filter_tbox(self, tbox: Dict[str, Any], stats: ClusterResult) -> Tuple[Dict[str, Any], Dict[str, Any]]:
        class_examples = {c.get("name"): c.get("examples", []) for c in tbox.get("classes", [])}
        filtered_classes, class_report = self._filter_classes(tbox.get("classes", []), stats.entity_freq)
        filtered_relations, relation_report = self._filter_relations(
            tbox.get("relations", []),
            stats.relation_freq,
            stats.entity_freq,
            class_examples,
        )

        filtered_tbox = {
            "classes": filtered_classes,
            "relations": filtered_relations,
            "attributes": tbox.get("attributes", []),
            "metadata": {
                "original_classes": len(tbox.get("classes", [])),
                "filtered_classes": len(filtered_classes),
                "original_relations": len(tbox.get("relations", [])),
                "filtered_relations": len(filtered_relations),
            },
        }

        report = {
            "class_report": class_report,
            "relation_report": relation_report,
        }
        return filtered_tbox, report

    def _filter_classes(self, classes: List[Dict[str, Any]], entity_freq: Dict[str, int]):
        filtered: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []

        for cls in classes:
            if self.protect_anchors and cls.get("is_anchor"):
                cls["support"] = -1
                filtered.append(cls)
                continue
            examples = cls.get("examples", [])
            support = sum(entity_freq.get(ex, 0) for ex in examples)
            cls["support"] = support
            if support >= self.min_support:
                filtered.append(cls)
            else:
                removed.append({
                    "name": cls.get("name"),
                    "support": support,
                    "reason": f"支持度 {support} < {self.min_support}",
                })

        report = {
            "total": len(classes),
            "kept": len(filtered),
            "removed": len(removed),
            "removed_details": removed,
        }
        return filtered, report

    def _filter_relations(
        self,
        relations: List[Dict[str, Any]],
        relation_freq: Dict[str, int],
        entity_freq: Dict[str, int],
        class_examples: Dict[str, List[str]],
    ):
        filtered: List[Dict[str, Any]] = []
        removed: List[Dict[str, Any]] = []

        for rel in relations:
            if self.protect_anchors and rel.get("is_anchor"):
                rel["confidence"] = -1
                filtered.append(rel)
                continue

            rel_name = rel.get("name", "")
            examples = rel.get("examples", [])
            support = sum(relation_freq.get(ex, 0) for ex in examples) if examples else relation_freq.get(rel_name, 0)

            domain_list = _normalize_type_list(rel.get("domain"))
            domain_count = 0
            for domain in domain_list:
                for ex in class_examples.get(domain, []):
                    domain_count += entity_freq.get(ex, 0)
            if domain_count <= 0:
                domain_count = max(support, 1)

            confidence = support / domain_count if domain_count else 0.0
            rel["support"] = support
            rel["confidence"] = round(confidence, 4)

            if confidence >= self.min_confidence and support >= self.min_support:
                filtered.append(rel)
            else:
                reason = (
                    f"置信度 {confidence:.2f} < {self.min_confidence} "
                    f"或 支持度 {support} < {self.min_support}"
                )
                removed.append({
                    "name": rel_name,
                    "support": support,
                    "confidence": confidence,
                    "reason": reason,
                })

        report = {
            "total": len(relations),
            "kept": len(filtered),
            "removed": len(removed),
            "removed_details": removed,
        }
        return filtered, report


class HybridOntologyBuilder:
    """混合本体构建器"""

    def __init__(
        self,
        llm_config: Optional[Dict[str, Any]] = None,
        embedding_model_name: str = "BAAI/bge-base-zh-v1.5",
        embedding_device: str = "cpu",
        config: Optional[Dict[str, Any]] = None,
    ):
        cfg = config or {}
        self.llm = LLMFactory.create(llm_config or {
            "provider": "openai",
            "model_name": "gpt-4o-mini",
            "temperature": 0.1,
        })
        self.client = LLMJsonClient(self.llm)
        self.embedding_model = SentenceTransformer(embedding_model_name, device=embedding_device)

        self.clustering_config = cfg.get("clustering", {})
        self.fusion_config = cfg.get("fusion", {})
        self.quality_config = cfg.get("quality_filter", {})

    def build(
        self,
        corpus_path: str,
        expert_skeleton_path: str,
        output_dir: Optional[str] = None,
        max_docs: Optional[int] = None,
        progress_path: Optional[str] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        records = self._load_corpus_records(corpus_path, max_docs=max_docs)
        texts = [r.get("text", "") for r in records if r.get("text")]
        doc_ids = [r.get("id", f"doc_{i}") for i, r in enumerate(records)]
        expert_tbox = self._load_expert_skeleton(expert_skeleton_path)

        class_candidates = [c.get("name") for c in expert_tbox.get("classes", []) if c.get("name")]
        miner = CorpusClusteringMiner(
            self.client,
            self.embedding_model,
            self.clustering_config,
            class_candidates=class_candidates,
        )
        progress_file = None
        if output_dir:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            progress_file = Path(progress_path) if progress_path else (out_dir / "vocab_mining.jsonl")
        elif progress_path:
            progress_file = Path(progress_path)

        clustering_result = miner.mine_and_cluster(
            texts,
            doc_ids=doc_ids,
            progress_path=progress_file,
            resume=resume,
        )

        fusion = HybridFusion(
            self.embedding_model,
            similarity_threshold=float(self.fusion_config.get("similarity_threshold", 0.75)),
        )
        fused_tbox = fusion.fuse(expert_tbox, clustering_result)

        quality_filter = QualityFilter(self.quality_config)
        filtered_tbox, filter_report = quality_filter.filter_tbox(fused_tbox, clustering_result)

        final_tbox = self._strip_extra_fields(filtered_tbox)
        final_tbox["metadata"] = {
            "build_method": "hybrid (expert + clustering)",
            "corpus_size": len(texts),
            "expert_classes": len(expert_tbox.get("classes", [])),
            "expert_relations": len(expert_tbox.get("relations", [])),
            "final_classes": len(final_tbox.get("classes", [])),
            "final_relations": len(final_tbox.get("relations", [])),
            "config": {
                "clustering": self.clustering_config,
                "fusion": self.fusion_config,
                "quality_filter": self.quality_config,
            },
        }

        if output_dir:
            out_dir = Path(output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "expert_skeleton_raw.json").write_text(
                json.dumps(expert_tbox, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (out_dir / "clustering_result.json").write_text(
                json.dumps({
                    "entity_clusters": clustering_result.entity_clusters,
                    "relation_clusters": clustering_result.relation_clusters,
                }, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            (out_dir / "fused_tbox_raw.json").write_text(
                json.dumps(fused_tbox, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (out_dir / "master_tbox.json").write_text(
                json.dumps(final_tbox, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (out_dir / "filter_report.json").write_text(
                json.dumps(filter_report, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        return final_tbox

    def _load_expert_skeleton(self, skeleton_path: str) -> Dict[str, Any]:
        data = json.loads(Path(skeleton_path).read_text(encoding="utf-8"))
        classes = []
        for cls in data.get("classes", []):
            classes.append({
                "name": cls.get("name", ""),
                "cn_name": cls.get("cn_name", ""),
                "definition": cls.get("definition", ""),
                "examples": cls.get("examples", []) or [],
                "parent": cls.get("parent"),
                "is_anchor": bool(cls.get("is_anchor", True)),
                "source": cls.get("source", "expert"),
            })
        relations = []
        for rel in data.get("relations", []):
            relations.append({
                "name": rel.get("name", ""),
                "cn_name": rel.get("cn_name", ""),
                "definition": rel.get("definition", ""),
                "domain": _normalize_type_list(rel.get("domain")),
                "range": _normalize_type_list(rel.get("range")),
                "functional": rel.get("functional", False),
                "is_anchor": bool(rel.get("is_anchor", True)),
                "source": rel.get("source", "expert"),
                "examples": rel.get("examples", []) or [],
            })
        return {
            "classes": classes,
            "relations": relations,
            "attributes": data.get("attributes", []),
            "metadata": {
                "description": data.get("description", ""),
                "version": data.get("version", ""),
            },
        }

    def _strip_extra_fields(self, tbox: Dict[str, Any]) -> Dict[str, Any]:
        clean_classes = []
        for cls in tbox.get("classes", []):
            clean_classes.append({
                "name": cls.get("name", ""),
                "cn_name": cls.get("cn_name", ""),
                "definition": cls.get("definition", ""),
                "examples": cls.get("examples", []) or [],
                "parent": cls.get("parent"),
            })

        clean_relations = []
        for rel in tbox.get("relations", []):
            clean_relations.append({
                "name": rel.get("name", ""),
                "cn_name": rel.get("cn_name", ""),
                "definition": rel.get("definition", ""),
                "domain": _normalize_type_list(rel.get("domain", [])),
                "range": _normalize_type_list(rel.get("range", [])),
                "functional": rel.get("functional", False),
            })

        return {
            "classes": clean_classes,
            "relations": clean_relations,
            "attributes": tbox.get("attributes", []),
        }

    def _load_corpus_records(self, corpus_path: str, max_docs: Optional[int] = None) -> List[Dict[str, Any]]:
        records: List[Dict[str, Any]] = []
        path = Path(corpus_path)

        def add_record(text: str, doc_id: str, context_before: str = "", context_after: str = ""):
            if text and len(text) >= 50:
                records.append({
                    "id": doc_id,
                    "text": text.strip(),
                    "context_before": context_before,
                    "context_after": context_after,
                })

        if path.is_dir():
            files = sorted(path.rglob("*.txt"))
            for fp in files:
                try:
                    content = fp.read_text(encoding="utf-8")
                except Exception:
                    continue
                add_record(content, fp.stem)
                if max_docs and len(records) >= max_docs:
                    break
            return records

        if path.suffix.lower() == ".jsonl":
            with path.open("r", encoding="utf-8") as f:
                for idx, line in enumerate(f, start=1):
                    if not line.strip():
                        continue
                    try:
                        doc = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    doc_id = doc.get("doc_id") or doc.get("id") or f"jsonl_{idx}"
                    text = doc.get("text") or doc.get("content") or doc.get("paragraph") or ""
                    add_record(
                        text,
                        str(doc_id),
                        context_before=doc.get("context_before", "") or "",
                        context_after=doc.get("context_after", "") or "",
                    )
                    if max_docs and len(records) >= max_docs:
                        break
            return records

        if path.exists():
            add_record(path.read_text(encoding="utf-8"), path.stem)

        return records
