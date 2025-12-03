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

import yaml

from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
)
from kg.utils.entity_linking import normalize_extraction_result


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


def split_text(text: str, min_chars: int, max_chars: int) -> List[str]:
    """
    简单段落切分：按空行分段后合并，控制单段长度在 [min_chars, max_chars]。
    若单段仍超过 max_chars，则硬切。
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    paras = [p.strip() for p in text.split("\n\n") if p.strip()]
    parts: List[str] = []
    buf: List[str] = []
    buf_len = 0

    def flush():
        nonlocal buf, buf_len
        if buf:
            parts.append("\n\n".join(buf).strip())
            buf = []
            buf_len = 0

    for para in paras:
        if len(para) > max_chars:
            flush()
            for i in range(0, len(para), max_chars):
                parts.append(para[i:i + max_chars].strip())
            continue
        if buf_len + len(para) + 2 <= max_chars:
            buf.append(para)
            buf_len += len(para) + 2
        else:
            if buf_len >= min_chars:
                flush()
                buf.append(para)
                buf_len = len(para)
            else:
                buf.append(para)
                buf_len += len(para) + 2
    flush()
    if len(parts) >= 2 and len(parts[-1]) < min_chars:
        parts[-2] = parts[-2] + "\n\n" + parts[-1]
        parts.pop()
    return parts or [text]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="在规范化 TBox 约束下执行 P5 事件与三元组抽取（支持批量与断点续跑）")
    parser.add_argument(
        "--cfg",
        default="configs/cfg.yaml",
        help="默认配置文件，命令行优先级最高",
    )
    parser.add_argument(
        "--tbox-file",
        default=None,
        help="包含 classes/relations/attributes 的 TBox JSON 路径（默认读 cfg.paths.p4_final_dir/p4_tbox_augmented.json）",
    )
    parser.add_argument("--paragraph-file", help="待抽取文本文件路径；缺省时从 stdin 读取")
    parser.add_argument("--corpus-dir", help="批量处理的目录（递归扫描 *.txt）")
    parser.add_argument("--provider", default=None,
                        choices=["openai", "zhipu", "gemini"], help="LLM 提供商（默认读 cfg.llm.provider）")
    parser.add_argument("--model", default=None,
                        help="模型名称，不填则读 cfg.llm.model_name 或 provider 默认值")
    parser.add_argument("--temperature", type=float,
                        default=None, help="采样温度，建议 JSON 模式保持较低（默认读 cfg.llm.temperature 或 0.1）")
    parser.add_argument(
        "--out",
        default=None,
        help="输出 JSON 路径（默认写入 cfg.paths.output_dir/p5_from_tbox.json）",
    )
    parser.add_argument("--output-dir", default=None,
                        help="批量模式下的输出目录（默认 cfg.paths.output_dir/p5_batch）")
    parser.add_argument("--overwrite", action="store_true",
                        help="覆盖已存在的 per-file 输出（默认跳过已完成文件）")
    parser.add_argument("--rerun-empty", action="store_true",
                        help="仅对已存在但 events/triples 为空或含 error 的文件重跑")
    parser.add_argument("--max-files", type=int, default=None,
                        help="批量模式下最多处理的文件数（用于小样本/配额控制）")
    parser.add_argument("--split-long", action="store_true",
                        help="自动切分过长文本（默认开启）")
    parser.add_argument("--min-chars", type=int, default=None,
                        help="切分后单段最小字符数，默认读 cfg.p5.min_chars 或 800")
    parser.add_argument("--max-chars", type=int, default=None,
                        help="切分后单段最大字符数，默认读 cfg.p5.max_chars 或 2500")
    parser.add_argument("--favor-existing-classes", action="store_true",
                        help="提示优先使用已有类（保守模式），默认读 cfg.p5.favor_existing_classes")
    parser.add_argument("--normalize-entities", action="store_true",
                        help="抽取后对事件/三元组做实体标准化，默认读 cfg.p5.normalize_entities")
    args = parser.parse_args()

    cfg = {}
    if args.cfg:
        cfg_path = Path(args.cfg)
        if cfg_path.exists():
            try:
                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            except Exception:
                cfg = {}

    def pick(*vals, default=None):
        for v in vals:
            if v not in [None, ""]:
                return v
        return default

    cfg_paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}
    cfg_llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
    cfg_p5 = cfg.get("p5", {}) if isinstance(cfg, dict) else {}

    provider = pick(args.provider, cfg_llm.get("provider"), "openai")
    model_name = pick(args.model, cfg_llm.get("model_name"),
                      "gpt-4o-mini" if provider == "openai" else "glm-4.5-flash")
    temperature = pick(args.temperature, cfg_llm.get("temperature"), 0.1)
    out_single = pick(args.out, cfg_paths.get("output_dir") and str(
        Path(cfg_paths.get("output_dir")) / "p5_from_tbox.json"), "outputs/kg/final/p5_from_tbox.json")
    out_dir_default = pick(args.output_dir, cfg_paths.get("output_dir") and str(
        Path(cfg_paths.get("output_dir")) / "p5_batch"), "outputs/kg/final/p5_batch")
    favor_existing = pick(args.favor_existing_classes,
                          cfg_p5.get("favor_existing_classes"), True)
    normalize_entities = pick(args.normalize_entities, cfg_p5.get("normalize_entities"), False)
    min_chars = pick(args.min_chars, cfg_p5.get("min_chars"), 800)
    max_chars = pick(args.max_chars, cfg_p5.get("max_chars"), 2500)
    tbox_default = Path(cfg_paths.get("p4_final_dir", cfg_paths.get(
        "output_dir", "outputs/cq_pipeline/final"))) / "p4_tbox_augmented.json"

    tbox_path = Path(args.tbox_file or tbox_default)
    if not tbox_path.exists():
        raise FileNotFoundError(f"TBox 文件不存在：{tbox_path}")

    llm_config = {
        "provider": provider,
        "model_name": model_name,
        "temperature": temperature,
        "thinking_type": cfg_llm.get("thinking_type"),
    }

    print(f"加载 TBox: {tbox_path}")
    print(
        f"[LLM][P5] provider={llm_config['provider']}, model={llm_config['model_name']}, temperature={llm_config['temperature']}")
    tbox = load_tbox(tbox_path)

    def is_quota_error(msg: str) -> bool:
        lower = msg.lower()
        return ("quota" in lower) or ("insufficient" in lower) or ("429" in lower)

    # 单文件模式
    if not args.corpus_dir:
        paragraph = read_paragraph(args.paragraph_file)
        pipeline = CQLLMPipeline(
            llm_config=llm_config, output_dir=Path(out_single).parent.as_posix())
        parts = split_text(paragraph, min_chars,
                           max_chars) if args.split_long else [paragraph]
        print(f"执行 P5 抽取...（分段 {len(parts)} 段）")
        for i, part in enumerate(parts, start=1):
            target = Path(out_single) if len(parts) == 1 else Path(
                out_single).with_name(f"{Path(out_single).stem}_part{i:02d}.json")
            try:
                res = pipeline.extract_events(
                    part, schema=tbox, save_path=None, favor_existing_classes=bool(favor_existing))
                if normalize_entities:
                    res = normalize_extraction_result(res)
                target.write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
                print(
                    f"[P5] 段{i}/{len(parts)} 完成：事件 {len(res.get('events', []))}，三元组 {len(res.get('triples', []))}，保存至 {target}")
            except Exception as e:
                target.write_text(json.dumps({"events": [], "triples": [], "error": str(e)}, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
                print(f"[P5][ERROR] 段{i}/{len(parts)}: {e}")
        return

    # 批量模式
    corpus_dir = Path(args.corpus_dir)
    out_dir = Path(out_dir_default)
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
        base_out = target_dir / f"{stem}_p5.json"
        text = fp.read_text(encoding="utf-8")
        parts = split_text(text, args.min_chars,
                           args.max_chars) if args.split_long else [text]
        for pidx, part in enumerate(parts, start=1):
            cur_out = base_out if len(
                parts) == 1 else target_dir / f"{stem}_part{pidx:02d}_p5.json"
            # 跳过逻辑（分段逐个判断）
            if cur_out.exists() and not args.overwrite:
                try:
                    existing_json = json.loads(
                        cur_out.read_text(encoding="utf-8"))
                    events = existing_json.get("events", [])
                    triples = existing_json.get("triples", [])
                    has_error = "error" in existing_json
                    need_rerun = False
                    if args.rerun_empty and (has_error or (len(events) == 0 and len(triples) == 0)):
                        need_rerun = True
                    if not need_rerun:
                        skipped_existing.append(str(cur_out))
                        skipped_src.append(f"{fp}#part{pidx}")
                        print(
                            f"[P5] 跳过已存在: {cur_out} (events={len(events)}, triples={len(triples)}, error={has_error})")
                        continue
                    else:
                        print(f"[P5] 重跑空/错误文件: {cur_out}")
                except Exception:
                    pass  # 解析失败则重跑

            try:
                res = pipeline.extract_events(
                    part, schema=tbox, save_path=cur_out)
                processed.append(str(cur_out))
                processed_src.append(f"{fp}#part{pidx}")
                print(
                    f"[P5] {idx}/{len(files)} {fp.name} part{pidx}/{len(parts)} -> {cur_out}，事件 {len(res.get('events', []))}，三元组 {len(res.get('triples', []))}")
            except Exception as e:
                msg = str(e)
                failed.append((f"{fp}#part{pidx}", msg))
                cur_out.write_text(json.dumps({"events": [], "triples": [], "error": msg}, ensure_ascii=False, indent=2),
                                   encoding="utf-8")
                print(f"[P5][ERROR] {fp.name} part{pidx}: {msg}")
                if is_quota_error(msg):
                    quota_exhausted = True
                    print("[P5] 检测到配额/429错误，停止后续任务。")
                    break
        if quota_exhausted:
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
