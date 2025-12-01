"""
从规范化后的 TBox 直接启动 P5 事件抽取。

使用场景：
1) 已完成 P1/P2/P3，拿到了最终的 TBox JSON（包含 classes/relations/attributes）。
2) 希望跳过前置步骤，直接在 TBox 约束下对文本段落抽取事件与三元组。

关键特性：
- 支持单文件 & 批量（递归目录）两种模式。
- 断点续跑：跳过已存在的结果；可选择仅重跑空/错误文件。
- 配额保护：检测配额/429 报错后停止，已完成结果与进度落盘。

示例：
    # 单文件
    python scripts/p5_from_tbox.py \
        --tbox-file outputs/cq_pipeline/final/p4_tbox_augmented.json \
        --paragraph-file data/raw/sample_paragraph.txt \
        --provider openai --model gpt-4o-mini \
        --out outputs/cq_pipeline/final/p5_from_tbox.json

    # 批量目录（递归），带进度与断点续跑
    python scripts/p5_from_tbox.py \
        --tbox-file outputs/cq_pipeline/final/p4_tbox_augmented.json \
        --corpus-dir data/raw_paragraphs_for_p5 \
        --output-dir outputs/cq_pipeline/final/p5_batch \
        --rerun-empty
"""
import argparse
import json
from pathlib import Path
from typing import Optional, List, Dict

from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
)


def load_tbox(tbox_path: Path) -> TBoxSchema:
    """从 JSON 文件加载 TBox（三个键：classes/relations/attributes）。"""
    data = json.loads(tbox_path.read_text(encoding="utf-8"))
    return TBoxSchema(
        classes=[ClassDef(**c) for c in data.get("classes", [])],
        relations=[RelationDef(**r) for r in data.get("relations", [])],
        attributes=[AttributeDef(**a) for a in data.get("attributes", [])],
    )


def read_paragraph(path: Optional[str]) -> str:
    """读取待抽取文本；未指定文件时从标准输入读取。"""
    if path:
        return Path(path).read_text(encoding="utf-8")
    print("未指定 --paragraph-file，请粘贴待抽取文本，结束后 Ctrl+D：")
    return "".join(iter(input, ""))  # 逐行读入直到 EOF


def main() -> None:
    parser = argparse.ArgumentParser(
        description="在规范化 TBox 约束下执行 P5 事件与三元组抽取（支持批量与断点续跑）")
    parser.add_argument(
        "--tbox-file",
        default="outputs/kg/final/p4_tbox_augmented.json",
        help="包含 classes/relations/attributes 的 TBox JSON 路径（默认使用 outputs/kg/final/p4_tbox_augmented.json）",
    )
    parser.add_argument("--paragraph-file", help="待抽取文本文件路径；缺省时从 stdin 读取")
    parser.add_argument("--corpus-dir", help="批量处理的目录（递归扫描 *.txt）")
    parser.add_argument("--provider", default="openai",
                        choices=["openai", "zhipu", "gemini"], help="LLM 提供商")
    parser.add_argument("--model", default=None,
                        help="模型名称，不填则使用各 provider 推荐默认值")
    parser.add_argument("--temperature", type=float,
                        default=0.1, help="采样温度，建议 JSON 模式保持较低")
    parser.add_argument(
        "--out",
        default="outputs/kg/final/p5_from_tbox.json",
        help="输出 JSON 路径（默认写入 outputs/kg/final）",
    )
    parser.add_argument("--output-dir", default="outputs/kg/final/p5_batch",
                        help="批量模式下的输出目录（默认 outputs/kg/final/p5_batch）")
    parser.add_argument("--overwrite", action="store_true",
                        help="覆盖已存在的 per-file 输出（默认跳过已完成文件）")
    parser.add_argument("--rerun-empty", action="store_true",
                        help="仅对已存在但 events/triples 为空或含 error 的文件重跑")
    parser.add_argument("--max-files", type=int, default=None,
                        help="批量模式下最多处理的文件数（用于小样本/配额控制）")
    args = parser.parse_args()

    tbox_path = Path(args.tbox_file)
    if not tbox_path.exists():
        raise FileNotFoundError(f"TBox 文件不存在：{tbox_path}")

    llm_config = {
        "provider": args.provider,
        "model_name": args.model or ("gpt-4o-mini" if args.provider == "openai" else "glm-4.5-flash"),
        "temperature": args.temperature,
    }

    print(f"加载 TBox: {tbox_path}")
    print(f"[LLM][P5] provider={llm_config['provider']}, model={llm_config['model_name']}, temperature={llm_config['temperature']}")
    tbox = load_tbox(tbox_path)

    def is_quota_error(msg: str) -> bool:
        lower = msg.lower()
        return ("quota" in lower) or ("insufficient" in lower) or ("429" in lower)

    # 单文件模式
    if not args.corpus_dir:
        paragraph = read_paragraph(args.paragraph_file)
        pipeline = CQLLMPipeline(
            llm_config=llm_config, output_dir=Path(args.out).parent.as_posix())
        print("执行 P5 抽取...")
        try:
            res = pipeline.extract_events(
                paragraph, schema=tbox, save_path=Path(args.out))
            print(
                f"完成：事件 {len(res.get('events', []))} 个，三元组 {len(res.get('triples', []))} 条，"
                f"已保存到 {args.out}"
            )
        except Exception as e:
            Path(args.out).write_text(json.dumps({"events": [], "triples": [], "error": str(e)}, ensure_ascii=False, indent=2),
                                      encoding="utf-8")
            print(f"[P5][ERROR] {e}")
        return

    # 批量模式
    corpus_dir = Path(args.corpus_dir)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(corpus_dir.rglob("*.txt"))
    if not files:
        print(f"未找到语料文件：{corpus_dir}")
        return

    pipeline = CQLLMPipeline(llm_config=llm_config,
                             output_dir=out_dir.as_posix())
    processed, skipped_existing, failed = [], [], []
    processed_src, skipped_src = [], []
    quota_exhausted = False

    for idx, fp in enumerate(files, start=1):
        if args.max_files and idx > args.max_files:
            print(f"[P5] 已达到 max-files={args.max_files} 限制，提前结束。")
            break
        if quota_exhausted:
            break
        rel = fp.relative_to(corpus_dir)
        rel_dir = rel.parent
        stem = rel.stem
        target_dir = out_dir / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        out_path = target_dir / f"{stem}_p5.json"

        # 跳过逻辑
        if out_path.exists() and not args.overwrite:
            try:
                existing_json = json.loads(
                    out_path.read_text(encoding="utf-8"))
                events = existing_json.get("events", [])
                triples = existing_json.get("triples", [])
                has_error = "error" in existing_json
                need_rerun = False
                if args.rerun_empty and (has_error or (len(events) == 0 and len(triples) == 0)):
                    need_rerun = True
                if not need_rerun:
                    skipped_existing.append(str(out_path))
                    skipped_src.append(str(fp))
                    print(
                        f"[P5] 跳过已存在: {out_path} (events={len(events)}, triples={len(triples)}, error={has_error})")
                    continue
                else:
                    print(f"[P5] 重跑空/错误文件: {out_path}")
            except Exception:
                pass  # 解析失败则重跑

        text = fp.read_text(encoding="utf-8")
        try:
            res = pipeline.extract_events(
                text, schema=tbox, save_path=out_path)
            processed.append(str(out_path))
            processed_src.append(str(fp))
            print(
                f"[P5] {idx}/{len(files)} {fp.name} -> {out_path}，事件 {len(res.get('events', []))}，三元组 {len(res.get('triples', []))}")
        except Exception as e:
            msg = str(e)
            failed.append((str(fp), msg))
            out_path.write_text(json.dumps({"events": [], "triples": [], "error": msg}, ensure_ascii=False, indent=2),
                                encoding="utf-8")
            print(f"[P5][ERROR] {fp.name}: {msg}")
            if is_quota_error(msg):
                quota_exhausted = True
                print("[P5] 检测到配额/429错误，停止后续任务。")
                break

    # 进度文件
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
    progress_path = out_dir / "_p5_progress.json"
    progress_path.write_text(json.dumps(
        progress, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[P5] 处理完成。进度已保存：{progress_path}")


if __name__ == "__main__":
    main()
