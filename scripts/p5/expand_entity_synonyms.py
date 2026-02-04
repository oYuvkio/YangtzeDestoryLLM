#!/usr/bin/env python3
"""
基于“向量相似度”的自动扩展同义词库。

思路：
- 从输入 jsonl 中抽取实体（entities + triples 的 subject/object）
- 通过相似度匹配到现有 canonical，作为候选同义词追加

模式：
1) tfidf（默认）：字符 n-gram TF-IDF + 余弦相似度（无需外部依赖）
2) embedding：SentenceTransformer 向量（可用 BAAI/bge-base-zh-v1.5）

输出：
- 新的同义词库 JSON（在原库基础上追加）
- 报告 JSON（匹配明细 + 统计）
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


def normalize_text(text: str) -> str:
    text = str(text).strip().lower()
    text = re.sub(r"（[^）]*）|\([^\)]*\)", "", text)
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。、\"'：；（）【】《》/\\\\-]", "", text)
    return text


def extract_entities_from_record(record: Dict[str, Any]) -> List[str]:
    entities: List[str] = []

    # entities 字段（兼容分组/扁平格式）
    raw_entities = record.get("entities", []) or []
    if isinstance(raw_entities, list):
        for item in raw_entities:
            if isinstance(item, dict) and "name" in item:
                name = str(item.get("name", "")).strip()
                if name:
                    entities.append(name)
                continue
            if isinstance(item, dict):
                for _, values in item.items():
                    if isinstance(values, list):
                        for v in values:
                            v = str(v).strip()
                            if v:
                                entities.append(v)
                    elif values:
                        v = str(values).strip()
                        if v:
                            entities.append(v)

    # triples 的 subject/object
    for t in record.get("triples", []) or []:
        if not isinstance(t, dict):
            continue
        s = str(t.get("subject", "")).strip()
        o = str(t.get("object", "")).strip()
        if s:
            entities.append(s)
        if o:
            entities.append(o)

    return entities


def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            items.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return items


def load_entities(paths: List[Path]) -> List[str]:
    all_entities: List[str] = []
    for path in paths:
        data = load_jsonl(path)
        for rec in data:
            if isinstance(rec, dict):
                all_entities.extend(extract_entities_from_record(rec))
    return all_entities


def load_synonyms(path: Path) -> Dict[str, Dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def build_canonical_map(synonyms: Dict[str, Dict[str, Any]]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for _, entry in synonyms.items():
        canonical = str(entry.get("canonical", "")).strip()
        if canonical:
            mapping[normalize_text(canonical)] = canonical
        for syn in entry.get("synonyms", []) or []:
            mapping[normalize_text(syn)] = canonical
    return mapping


def char_ngrams(text: str, n_min: int, n_max: int) -> List[str]:
    grams: List[str] = []
    if not text:
        return grams
    length = len(text)
    for n in range(n_min, n_max + 1):
        if length < n:
            continue
        for i in range(length - n + 1):
            grams.append(text[i : i + n])
    return grams


def build_tfidf_vectors(
    texts: List[str],
    n_min: int,
    n_max: int,
) -> Tuple[List[Dict[str, float]], Dict[str, float]]:
    docs = [char_ngrams(t, n_min, n_max) for t in texts]
    df = Counter()
    for grams in docs:
        df.update(set(grams))
    idf = {g: math.log((1 + len(docs)) / (1 + c)) + 1.0 for g, c in df.items()}

    vectors: List[Dict[str, float]] = []
    for grams in docs:
        tf = Counter(grams)
        vec = {g: tf[g] * idf[g] for g in tf}
        vectors.append(vec)
    return vectors, idf


def cosine_sim(a: Dict[str, float], b: Dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = 0.0
    for k, v in a.items():
        if k in b:
            dot += v * b[k]
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def build_embedding_vectors(
    texts: List[str],
    model_name: str,
    device: str,
    batch_size: int,
) -> List[List[float]]:
    from sentence_transformers import SentenceTransformer  # local import to avoid hard dependency

    model = SentenceTransformer(model_name, device=device)
    return model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=batch_size,
        show_progress_bar=True,
    ).tolist()


def main() -> None:
    parser = argparse.ArgumentParser(description="自动扩展实体同义词库（向量相似度）")
    parser.add_argument("--synonyms", required=True, help="现有同义词库 JSON")
    parser.add_argument("--input", action="append", required=True, help="输入 jsonl（可多次传入）")
    parser.add_argument("--output", required=True, help="输出扩展后的同义词库 JSON")
    parser.add_argument("--report", default="", help="报告输出 JSON（可选）")
    parser.add_argument("--mode", choices=["tfidf", "embedding"], default="tfidf", help="向量相似度模式")
    parser.add_argument("--threshold", type=float, default=0.88, help="相似度阈值")
    parser.add_argument("--top-k", type=int, default=3, help="每个实体最多匹配多少 canonical")
    parser.add_argument("--ngram-min", type=int, default=2, help="字符 n-gram 最小长度")
    parser.add_argument("--ngram-max", type=int, default=4, help="字符 n-gram 最大长度")
    parser.add_argument("--min-len", type=int, default=2, help="实体最短长度过滤")
    parser.add_argument("--max-candidates", type=int, default=200000, help="最多处理实体数")
    parser.add_argument("--embedding-model", default="BAAI/bge-base-zh-v1.5", help="Embedding 模型名称")
    parser.add_argument("--embedding-device", default="cpu", help="Embedding 模型设备（cpu/cuda）")
    parser.add_argument("--embedding-batch-size", type=int, default=128, help="Embedding 编码 batch size")
    parser.add_argument("--sim-batch-size", type=int, default=512, help="相似度计算 batch size")
    args = parser.parse_args()

    synonyms_path = Path(args.synonyms)
    inputs = [Path(p) for p in args.input]
    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else None

    synonyms = load_synonyms(synonyms_path)
    canonical_map = build_canonical_map(synonyms)

    entities_raw = load_entities(inputs)
    entities_norm = [normalize_text(e) for e in entities_raw]
    entities = []
    for raw, norm in zip(entities_raw, entities_norm):
        if not norm or len(norm) < args.min_len:
            continue
        entities.append((raw, norm))

    # 去重并限制数量
    seen = set()
    candidates: List[Tuple[str, str]] = []
    for raw, norm in entities:
        if norm in seen:
            continue
        seen.add(norm)
        candidates.append((raw, norm))
        if len(candidates) >= args.max_candidates:
            break

    canonical_texts = []
    canonical_keys = []
    for key, entry in synonyms.items():
        canonical = str(entry.get("canonical", "")).strip()
        if canonical:
            canonical_texts.append(normalize_text(canonical))
            canonical_keys.append(key)

    if not canonical_texts:
        raise SystemExit("[ERROR] 同义词库中未找到 canonical，无法扩展。")

    # 仅保留不在已有同义词库中的候选
    filtered_candidates = [(raw, norm) for raw, norm in candidates if norm not in canonical_map]

    suggestions: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    if args.mode == "tfidf":
        all_texts = canonical_texts + [norm for _, norm in filtered_candidates]
        vectors, _ = build_tfidf_vectors(all_texts, args.ngram_min, args.ngram_max)
        canonical_vecs = vectors[: len(canonical_texts)]
        candidate_vecs = vectors[len(canonical_texts) :]

        for (raw, _), vec in zip(filtered_candidates, candidate_vecs):
            sims: List[Tuple[int, float]] = []
            for i, cvec in enumerate(canonical_vecs):
                sim = cosine_sim(vec, cvec)
                if sim >= args.threshold:
                    sims.append((i, sim))
            sims.sort(key=lambda x: x[1], reverse=True)
            sims = sims[: args.top_k]
            for idx, score in sims:
                key = canonical_keys[idx]
                suggestions[key].append({"entity": raw, "score": round(score, 4)})
    else:
        import numpy as np

        canonical_vecs = build_embedding_vectors(
            canonical_texts,
            model_name=args.embedding_model,
            device=args.embedding_device,
            batch_size=args.embedding_batch_size,
        )
        candidate_texts = [norm for _, norm in filtered_candidates]
        candidate_vecs = build_embedding_vectors(
            candidate_texts,
            model_name=args.embedding_model,
            device=args.embedding_device,
            batch_size=args.embedding_batch_size,
        )

        canonical_mat = np.asarray(canonical_vecs, dtype="float32")
        cand_mat = np.asarray(candidate_vecs, dtype="float32")

        for start in range(0, len(cand_mat), args.sim_batch_size):
            end = min(start + args.sim_batch_size, len(cand_mat))
            scores = np.matmul(cand_mat[start:end], canonical_mat.T)  # cosine (normalized)
            for row_idx in range(scores.shape[0]):
                row = scores[row_idx]
                if args.top_k >= len(row):
                    best_idx = np.argsort(-row)
                else:
                    best_idx = np.argpartition(row, -args.top_k)[-args.top_k:]
                    best_idx = best_idx[np.argsort(-row[best_idx])]
                raw = filtered_candidates[start + row_idx][0]
                for idx in best_idx:
                    score = float(row[idx])
                    if score < args.threshold:
                        continue
                    key = canonical_keys[int(idx)]
                    suggestions[key].append({"entity": raw, "score": round(score, 4)})

    # 生成输出
    updated = json.loads(synonyms_path.read_text(encoding="utf-8"))
    added_count = 0
    for key, items in suggestions.items():
        entry = updated.get(key, {})
        syns = entry.get("synonyms", []) or []
        existing = {normalize_text(s) for s in syns}
        for item in items:
            if normalize_text(item["entity"]) in existing:
                continue
            syns.append(item["entity"])
            existing.add(normalize_text(item["entity"]))
            added_count += 1
        entry["synonyms"] = syns
        updated[key] = entry

    updated["_auto_expand"] = {
        "source_inputs": [str(p) for p in inputs],
        "mode": args.mode,
        "threshold": args.threshold,
        "top_k": args.top_k,
        "ngram_min": args.ngram_min,
        "ngram_max": args.ngram_max,
        "min_len": args.min_len,
        "added_synonyms": added_count,
        "embedding_model": args.embedding_model if args.mode == "embedding" else "",
        "embedding_device": args.embedding_device if args.mode == "embedding" else "",
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "added_synonyms": added_count,
            "candidate_count": len(filtered_candidates),
            "suggestions": suggestions,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] 输出扩展后的同义词库: {output_path}")
    if report_path:
        print(f"[OK] 输出报告: {report_path}")
    print(f"[INFO] 新增同义词: {added_count}")


if __name__ == "__main__":
    main()
