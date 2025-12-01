# scripts/run_p4_batch.py
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Dict
from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
)


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


def merge_suggestions(
    base: TBoxSchema,
    suggestions: List[Dict],
    *,
    allow_new_classes: bool = False,
    min_support: int = 2,
) -> TBoxSchema:
    """
    根据聚合建议生成增强 TBox（兼容旧版 apply_p4_suggestions 的需求）。

    规则：
    - 默认不新增类；允许时也需满足 support 阈值；
    - 关系必须有 domain/range 且存在于类集合；
    - 属性必须挂在现有 owner 上。
    """
    class_names = {c.name for c in base.classes}
    rel_keys = {(r.name, r.domain, r.range) for r in base.relations}
    attr_keys = {(a.owner, a.name) for a in base.attributes}

    new_classes = list(base.classes)
    new_relations = list(base.relations)
    new_attrs = list(base.attributes)

    for s in suggestions:
        s_type = s.get("type")
        name = s.get("name")
        cn_name = s.get("cn_name", "")
        definition = s.get("definition", "")
        support = int(s.get("_support", 1))
        if not name or support < min_support:
            continue

        if s_type == "class":
            if not allow_new_classes or name in class_names:
                continue
            new_classes.append(
                ClassDef(name=name, cn_name=cn_name, definition=definition, examples=[]))
            class_names.add(name)
        elif s_type == "relation":
            domain = s.get("parent_or_domain_range_or_owner") or s.get(
                "domain") or ""
            range_ = s.get("range") or ""
            if not domain or not range_ or domain not in class_names or range_ not in class_names:
                continue
            key = (name, domain, range_)
            if key in rel_keys:
                continue
            new_relations.append(
                RelationDef(
                    name=name,
                    cn_name=cn_name,
                    domain=domain,
                    range=range_,
                    definition=definition,
                    functional=s.get("functional"),
                )
            )
            rel_keys.add(key)
        elif s_type == "attribute":
            owner = s.get("parent_or_domain_range_or_owner") or s.get(
                "owner") or ""
            if not owner or owner not in class_names:
                continue
            key = (owner, name)
            if key in attr_keys:
                continue
            new_attrs.append(AttributeDef(
                owner=owner, name=name, cn_name=cn_name, value_type=s.get("value_type", "string")))
            attr_keys.add(key)

    return TBoxSchema(classes=new_classes, relations=new_relations, attributes=new_attrs)


def main():
    """
    P4 批处理：
    - process_dir：存放按文献拆分的 suggestions 以及聚合建议
    - final_dir  ：存放最终/基线 TBox（带时间戳备份）
    """
    parser = argparse.ArgumentParser(description="P4 文献增强 TBox 批处理")
    parser.add_argument("--base-tbox", default="outputs/cq_pipeline/final/p3_tbox_normalized.json",
                        help="基线 TBox 路径（默认 final/p3_tbox_normalized.json）")
    parser.add_argument("--corpus-dir", default="data/enhancing_onto_corpus_docs",
                        help="增强语料目录（默认 data/enhancing_onto_corpus_docs）")
    parser.add_argument("--process-dir", default="outputs/cq_pipeline/process",
                        help="中间结果输出目录（默认 outputs/cq_pipeline/process）")
    parser.add_argument("--final-dir", default="outputs/cq_pipeline/final",
                        help="最终 TBox 输出目录（默认 outputs/cq_pipeline/final）")
    parser.add_argument("--min-support", type=int, default=2,
                        help="建议合并的最小支持度，默认 2")
    parser.add_argument("--overwrite", action="store_true",
                        help="覆盖已存在的 per-file 建议（默认跳过已完成文件）")
    parser.add_argument("--rerun-empty", action="store_true",
                        help="对已存在但建议为空或包含 error 的文件重跑（不全量覆盖）")
    parser.add_argument("--allow-new-classes", action="store_true",
                        help="合并阶段是否允许新增类（默认不允许）")
    parser.add_argument("--extra-supports", default="",
                        help="额外的 min_support 列表，用逗号分隔，如 1,3")
    parser.add_argument("--agg-file", default=None,
                        help="直接指定聚合建议文件（默认 process_dir/p4_corpus_suggestions_agg.json）")
    parser.add_argument("--merge-only", action="store_true",
                        help="仅基于已有聚合文件做合并，不重新调用 LLM 生成建议")
    args = parser.parse_args()

    version_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    final_dir = Path(args.final_dir)
    process_dir = Path(args.process_dir)
    final_dir.mkdir(parents=True, exist_ok=True)
    process_dir.mkdir(parents=True, exist_ok=True)

    base_path = Path(args.base_tbox)
    if not base_path.exists():
        print(f"未找到基线 TBox：{base_path}，请先完成 P1-P3。")
        return
    base = build_tbox(base_path)

    pipeline = CQLLMPipeline()
    if hasattr(pipeline, "llm_config"):
        cfg_llm = pipeline.llm_config
    print(f"[LLM][P4] provider={cfg_llm.get('provider')}, model={cfg_llm.get('model_name')}, temperature={cfg_llm.get('temperature')}")
    corpus_dir = Path(args.corpus_dir)
    agg_path = Path(args.agg_file) if args.agg_file else process_dir / \
        "p4_corpus_suggestions_agg.json"

    aggregated: List[Dict] = []
    processed, skipped_existing, failed = [], [], []
    processed_src, skipped_src = [], []
    quota_exhausted = False

    def is_quota_error(msg: str) -> bool:
        lower = msg.lower()
        return ("quota" in lower) or ("insufficient" in lower) or ("429" in lower)

    if args.merge_only and agg_path.exists():
        print(f"[P4] merge-only 模式，读取已有聚合文件：{agg_path}")
        aggregated = json.loads(agg_path.read_text(
            encoding="utf-8")).get("suggestions", [])
        files = []
    else:
        files = sorted(corpus_dir.rglob("*.txt"))
        if not files:
            print(f"未找到语料文件，目录为空：{corpus_dir}")
            return
        print(
            f"[P4] 发现语料 {len(files)} 篇，开始逐篇生成 suggestions（存储在 {process_dir}）...")

        raw_suggestions = []
        for fp in files:
            if quota_exhausted:
                break
            doc_text = fp.read_text(encoding="utf-8")
            try:
                rel = fp.relative_to(corpus_dir).with_suffix("")
                rel_dir = rel.parent
                stem = rel.name
            except ValueError:
                rel_dir = None
                stem = fp.stem

            per_doc_dir = process_dir / rel_dir if rel_dir else process_dir
            per_doc_dir.mkdir(parents=True, exist_ok=True)
            per_doc_path = per_doc_dir / f"{stem}_suggestions.json"
            # 若文件已存在且不覆盖，判断是否需要重跑
            if per_doc_path.exists() and not args.overwrite:
                try:
                    existing_json = json.loads(
                        per_doc_path.read_text(encoding="utf-8"))
                    existing = existing_json.get("suggestions", [])
                    has_error = "error" in existing_json
                    need_rerun = False
                    if args.rerun_empty and (has_error or len(existing) == 0):
                        need_rerun = True
                    if not need_rerun:
                        raw_suggestions.extend(existing)
                        skipped_existing.append(str(per_doc_path))
                        skipped_src.append(str(fp))
                        print(
                            f"[P4] 跳过已存在: {per_doc_path} (建议 {len(existing)} 条，error={has_error})")
                        continue
                    else:
                        print(f"[P4] 重跑空/错误文件: {per_doc_path}")
                except Exception:
                    # 解析失败则继续重跑
                    pass

            try:
                res = pipeline.enhance_schema(base, doc_text)
                sug = res.get("suggestions", [])
                for s in sug:
                    s["_source"] = fp.name
                raw_suggestions.extend(sug)
                per_doc_path.write_text(
                    json.dumps({"suggestions": sug},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                processed.append(str(per_doc_path))
                processed_src.append(str(fp))
                print(f"[P4] {fp.name} -> {per_doc_path}，共 {len(sug)} 条建议")
            except Exception as e:
                msg = str(e)
                failed.append((str(fp), msg))
                per_doc_path.write_text(
                    json.dumps({"suggestions": [], "error": msg},
                               ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(f"[P4][ERROR] {fp.name}: {msg}")
                if is_quota_error(msg):
                    quota_exhausted = True
                    print("[P4] 检测到配额/429错误，停止后续任务。")
                    break

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
        agg_path.write_text(
            json.dumps({"suggestions": aggregated},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[P4] 聚合建议已写入：{agg_path}，总计 {len(aggregated)} 条")

    # 使用多组配置生成增强 TBox
    supports = {args.min_support}
    if args.extra_supports:
        for s in args.extra_supports.split(","):
            s = s.strip()
            if s.isdigit():
                supports.add(int(s))

    configs = []
    for sup in sorted(supports):
        configs.append((sup, args.allow_new_classes,
                        f"s{sup}_allow{int(args.allow_new_classes)}"))
        if not args.allow_new_classes:
            configs.append((sup, True, f"s{sup}_allow1"))

    for sup, allow_cls, suffix in configs:
        tbox_aug = merge_suggestions(
            base,
            aggregated,
            allow_new_classes=allow_cls,
            min_support=sup,
        )
        out_path = final_dir / f"p4_tbox_augmented_{suffix}.json"
        write_json_with_backup(out_path, tbox_aug.to_dict(), version_tag)
        print(
            f"[P4] 已生成增强 TBox (allow_new_classes={allow_cls}, min_support={sup}) -> {out_path.name}")
    # 保存进度
    seen_src = set(processed_src) | set(skipped_src) | {p for p, _e in failed}
    not_processed = [str(f) for f in files if str(f) not in seen_src]
    progress = {
        "processed": processed,
        "skipped_existing": skipped_existing,
        "failed": failed,
        "total_files": len(files),
        "quota_exhausted": quota_exhausted,
        "not_processed": not_processed,
    }
    progress_path = process_dir / "_p4_progress.json"
    progress_path.write_text(json.dumps(
        progress, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[P4] 处理完成。进度已保存：{progress_path}")


if __name__ == "__main__":
    main()
