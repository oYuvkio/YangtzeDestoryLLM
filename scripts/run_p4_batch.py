# scripts/run_p4_batch.py
import json
from datetime import datetime
from pathlib import Path
from kg.cq_pipeline import CQLLMPipeline, TBoxSchema, ClassDef, RelationDef, AttributeDef
from experiments.exp_kg_Onto import apply_p4_suggestions, run_p4_over_corpus, load_tbox_file


def build_tbox(path: Path) -> TBoxSchema:
    data = json.loads(path.read_text(encoding="utf-8"))
    return TBoxSchema(
        classes=[ClassDef(**c) for c in data["classes"]],
        relations=[RelationDef(**r) for r in data["relations"]],
        attributes=[AttributeDef(**a) for a in data["attributes"]],
    )


def write_json_with_backup(path: Path, data: dict, version_tag: str) -> None:
    """
    落盘时自动生成带时间戳的备份文件，避免多轮实验覆盖历史产物。
    例：p4_tbox_augmented_supp1_20250310_1530.json
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False,
                    indent=2), encoding="utf-8")
    backup = path.with_name(f"{path.stem}_{version_tag}{path.suffix}")
    backup.write_text(json.dumps(data, ensure_ascii=False,
                      indent=2), encoding="utf-8")
    print(f"[SAVE] 主文件: {path.name}，备份: {backup.name}")


def main():
    """
    P4 批处理：
    - process_dir：存放按文献拆分的 suggestions 以及聚合建议
    - final_dir  ：存放最终/基线 TBox（带时间戳备份）
    """
    version_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_dir = Path("outputs/cq_pipeline/final")
    process_dir = Path("outputs/cq_pipeline/process")
    final_dir.mkdir(parents=True, exist_ok=True)
    process_dir.mkdir(parents=True, exist_ok=True)

    base_path = final_dir / "p3_tbox_normalized.json"
    if not base_path.exists():
        print(f"未找到基线 TBox：{base_path}，请先完成 P1-P3。")
        return
    base = build_tbox(base_path)

    pipeline = CQLLMPipeline()
    corpus_dir = Path("data/enhancing_onto_corpus_docs")

    files = sorted(corpus_dir.glob("*.txt"))
    if not files:
        print(f"未找到语料文件，目录为空：{corpus_dir}")
        return
    print(f"[P4] 发现语料 {len(files)} 篇，开始逐篇生成 suggestions（存储在 {process_dir}）...")

    # 逐篇调用 P4，按文献保存
    raw_suggestions = []
    for fp in files:
        doc_text = fp.read_text(encoding="utf-8")
        res = pipeline.enhance_schema(base, doc_text)
        # 标记来源文件名，便于追溯
        sug = res.get("suggestions", [])
        for s in sug:
            s["_source"] = fp.name
        raw_suggestions.extend(sug)
        per_doc_path = process_dir / f"{fp.stem}_suggestions.json"
        per_doc_path.write_text(
            json.dumps({"suggestions": sug}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[P4] {fp.name} -> {per_doc_path.name}，共 {len(sug)} 条建议")

    # 聚合与频次统计（_support）
    print("[P4] 开始聚合建议并统计支持度...")
    suggestion_buckets = {}
    for s in raw_suggestions:
        s_type = s.get("type")
        name = s.get("name")
        if not s_type or not name:
            continue
        parent_or_owner = s.get("parent_or_domain_range_or_owner") or s.get(
            "owner") or s.get("domain") or ""
        range_ = s.get("range") or ""
        key = (s_type, name, parent_or_owner, range_)
        if key not in suggestion_buckets:
            s["_support"] = 1
            suggestion_buckets[key] = s
        else:
            suggestion_buckets[key]["_support"] += 1

    aggregated = list(suggestion_buckets.values())
    agg_path = process_dir / "p4_corpus_suggestions_agg.json"
    agg_path.write_text(
        json.dumps({"suggestions": aggregated}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[P4] 聚合建议已写入：{agg_path}，总计 {len(aggregated)} 条")

    # 使用统一的 min_support=2 生成增强 TBox
    tbox_aug = apply_p4_suggestions(
        base,
        aggregated,
        allow_new_classes=False,
        min_support=2,
    )
    write_json_with_backup(
        final_dir / "p4_tbox_augmented.json",
        tbox_aug.to_dict(),
        version_tag,
    )
    print("[P4] 已生成增强 TBox (min_support=2) 及备份。")
    print("[P4] 处理完成。")


if __name__ == "__main__":
    main()
