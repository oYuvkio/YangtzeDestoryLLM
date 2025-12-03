"""
从处理后的语料目录中抽取评估子集（Eval Pool），并按类别划分 Dev/Test。

目标：
- 从四类语料中抽若干段落（默认约 300 段，每段 150~400 字），覆盖主要概念（洪水/干旱/致灾因子/影响/应对）。
- 分类来源（约配置）：
  * law_plan（法案&预案&制度） ~60
  * gazette_yearbook（公报&年鉴） ~80
  * case_paper（案例&论文） ~100
  * news_popular（科普&新闻） ~60
- 输出：
  * data/p5_eval_pool/pool.jsonl （全部样本）
  * data/p5_eval_pool/dev.jsonl   （分层抽样 60%）
  * data/p5_eval_pool/test.jsonl  （分层抽样 40%）

使用示例：
python tools/build_eval_pool.py \
  --root data/corpus_for_kg/handled_all_kg_corpus \
  --out-dir data/p5_eval_pool \
  --min-chars 150 --max-chars 400 \
  --target law_plan=60 gazette_yearbook=80 case_paper=100 news_popular=60
"""
from __future__ import annotations

import argparse
import json
import random
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Tuple

from kg.llm_core import LLMFactory, AccountBlockedError, RateLimitError
from kg.prompts import (
    EVAL_SEGMENT_FILTER_SYSTEM,
    EVAL_SEGMENT_FILTER_USER_TEMPLATE,
)


CategoryMap = {
    "法案": "law_plan",
    "预案": "law_plan",
    "制度": "law_plan",
    "应急预案": "law_plan",
    "公报": "gazette_yearbook",
    "年鉴": "gazette_yearbook",
    "年报": "gazette_yearbook",
    "案例": "case_paper",
    "论文": "case_paper",
    "科普": "news_popular",
    "新闻": "news_popular",
}


@dataclass
class Segment:
    id: str
    source_type: str
    doc_title: str
    year: int | None
    text: str
    rel_path: str
    filter_decision: dict | None = None


def detect_source_type(path: Path) -> str:
    """
    基于父目录名或文件名的中文关键词粗略映射 source_type。
    """
    names = [path.name] + [p.name for p in path.parents]
    for name in names:
        for k, v in CategoryMap.items():
            if k in name:
                return v
    return "unknown"


def detect_year_from_name(name: str) -> int | None:
    m = re.search(r"(19|20)\d{2}", name)
    return int(m.group(0)) if m else None


def split_paragraphs(text: str, min_chars: int, max_chars: int) -> List[str]:
    """
    按空行分段后合并，控制长度在 [min_chars, max_chars]；过长则硬切。
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
    return parts


def load_filter_cache(path: Path) -> Dict[str, dict]:
    if not path.exists():
        return {}
    cache: Dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
                seg_id = item.get("id")
                if seg_id:
                    cache[seg_id] = item
            except Exception:
                continue
    return cache


def save_filter_cache(cache: Dict[str, dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for seg_id, item in cache.items():
            row = {"id": seg_id, **item}
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def judge_segment(seg: Segment, backend) -> dict:
    """
    调用 LLM 按提示词评估段落质量与相关性。
    返回 JSON dict，失败时返回 keep_for_eval=False 的占位结果。
    """
    # 使用简单替换避免模板中的大括号冲突
    user_prompt = EVAL_SEGMENT_FILTER_USER_TEMPLATE.replace(
        "{segment_text}", seg.text)
    try:
        resp = backend.chat_messages(
            [
                {"role": "system", "content": EVAL_SEGMENT_FILTER_SYSTEM},
                {"role": "user", "content": user_prompt},
            ],
            json_mode=True,
            response_format={"type": "json_object"},
        )
    except (RateLimitError, AccountBlockedError):
        raise
    except Exception as e:
        print(f"⚠️ LLM 调用异常（{seg.id}）：{e}")
        resp = ""

    if not resp:
        return {
            "keep_for_eval": False,
            "reason": "llm_empty_response",
            "labels": {},
        }
    try:
        parsed = json.loads(resp)
        if not isinstance(parsed, dict):
            raise ValueError("not a dict")
        return parsed
    except Exception:
        return {
            "keep_for_eval": False,
            "reason": "llm_parse_error",
            "raw": resp,
            "labels": {},
        }


def filter_segments_with_llm(
    segments: List[Segment],
    llm_config: dict,
    cache_path: Path,
    refilter: bool = False,
) -> List[Segment]:
    """
    使用 LLM 过滤段落；支持基于缓存的断点续跑。
    """
    backend = LLMFactory.create(llm_config)
    cache = {} if refilter else load_filter_cache(cache_path)
    kept: List[Segment] = []
    updated_cache: Dict[str, dict] = dict(cache)

    for seg in segments:
        if not refilter and seg.id in cache:
            decision = cache[seg.id]
        else:
            decision = judge_segment(seg, backend)
            updated_cache[seg.id] = decision
        seg.filter_decision = decision
        if decision.get("keep_for_eval"):
            kept.append(seg)

    save_filter_cache(updated_cache, cache_path)
    return kept


def collect_segments(root: Path, min_chars: int, max_chars: int) -> List[Segment]:
    segments: List[Segment] = []
    for fp in root.rglob("*.txt"):
        if fp.name.endswith(".meta.txt") or fp.name.endswith(".meta.json"):
            continue
        src_type = detect_source_type(fp)
        year = detect_year_from_name(fp.name)
        title = fp.stem
        rel_path = fp.relative_to(root).as_posix()
        text = fp.read_text(encoding="utf-8", errors="ignore")
        parts = split_paragraphs(text, min_chars, max_chars)
        for idx, p in enumerate(parts, start=1):
            if len(p) < min_chars:
                continue
            seg_id = f"{src_type}_{fp.stem}_para_{idx}"
            segments.append(Segment(
                id=seg_id,
                source_type=src_type,
                doc_title=title,
                year=year,
                text=p,
                rel_path=rel_path,
            ))
    return segments


def sample_by_category(segments: List[Segment], target: Dict[str, int]) -> List[Segment]:
    """
    按 source_type 分层随机采样（不足则全取）。
    """
    by_cat: Dict[str, List[Segment]] = {}
    for seg in segments:
        by_cat.setdefault(seg.source_type, []).append(seg)

    sampled: List[Segment] = []
    for cat, num in target.items():
        pool = by_cat.get(cat, [])
        if not pool:
            continue
        random.shuffle(pool)
        sampled.extend(pool[:num])
    return sampled


def split_dev_test(sampled: List[Segment], dev_ratio: float = 0.6) -> Tuple[List[Segment], List[Segment]]:
    """
    在每个 source_type 组内随机划分 Dev/Test，保持分布。
    """
    by_cat: Dict[str, List[Segment]] = {}
    for seg in sampled:
        by_cat.setdefault(seg.source_type, []).append(seg)

    dev, test = [], []
    for cat, segs in by_cat.items():
        random.shuffle(segs)
        cutoff = int(len(segs) * dev_ratio)
        dev.extend(segs[:cutoff])
        test.extend(segs[cutoff:])
    return dev, test


def save_jsonl(objs: List[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in objs:
            f.write(json.dumps(asdict(obj), ensure_ascii=False) + "\n")


def parse_target(target_args: List[str]) -> Dict[str, int]:
    """
    解析 --target 形如 law_plan=60 的列表。
    """
    target: Dict[str, int] = {}
    for item in target_args:
        if "=" in item:
            k, v = item.split("=", 1)
            if v.isdigit():
                target[k] = int(v)
    return target


def main():
    parser = argparse.ArgumentParser(description="构建 P5 Eval Pool，并按类别分层切分 Dev/Test")
    parser.add_argument("--root", default="data/corpus_for_kg/handled_all_kg_corpus", help="源语料根目录")
    parser.add_argument("--out-dir", default="data/p5_eval_pool", help="输出目录")
    parser.add_argument("--min-chars", type=int, default=150, help="段落最小字符数，默认 150")
    parser.add_argument("--max-chars", type=int, default=400, help="段落最大字符数，默认 400")
    parser.add_argument("--target", nargs="+",
                        default=["law_plan=60", "gazette_yearbook=80", "case_paper=100", "news_popular=60"],
                        help="各类别抽取目标，如 law_plan=60 gazette_yearbook=80 ...")
    parser.add_argument("--dev-ratio", type=float, default=0.6, help="Dev 比例，默认 0.6")
    parser.add_argument("--no-filter", action="store_true", help="跳过 LLM 质量过滤，保留全部段落")
    parser.add_argument("--refilter", action="store_true", help="忽略缓存，强制重新调用 LLM 过滤")
    parser.add_argument("--filter-cache", default=None, help="LLM 过滤缓存文件路径，默认在 out-dir/_eval_filter_cache.jsonl")
    parser.add_argument("--llm-provider", default=None, help="LLM provider（zhipu/openai/gemini），默认读取环境变量或 zhipu")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名，默认读取环境变量")
    parser.add_argument("--llm-temperature", type=float, default=0.0, help="LLM 温度，默认 0.0（更稳定）")
    args = parser.parse_args()

    root = Path(args.root)
    out_dir = Path(args.out_dir)
    if not root.exists():
        raise FileNotFoundError(f"源目录不存在：{root}")

    target = parse_target(args.target)
    print(f"[EVAL] 扫描源目录: {root}")
    segs = collect_segments(root, args.min_chars, args.max_chars)
    print(f"[EVAL] 收集段落 {len(segs)} 条")

    # LLM 过滤
    if args.no_filter:
        filtered = segs
        print(f"[EVAL] 跳过 LLM 过滤，直接使用 {len(filtered)} 条")
    else:
        cache_path = Path(args.filter_cache) if args.filter_cache else out_dir / "_eval_filter_cache.jsonl"
        llm_conf: dict = {"temperature": args.llm_temperature}
        if args.llm_provider:
            llm_conf["provider"] = args.llm_provider
        if args.llm_model:
            llm_conf["model_name"] = args.llm_model
        print(f"[EVAL] 使用 LLM 过滤段落，缓存: {cache_path}")
        try:
            filtered = filter_segments_with_llm(
                segs,
                llm_conf,
                cache_path=cache_path,
                refilter=args.refilter,
            )
        except AccountBlockedError as e:
            raise RuntimeError(f"❌ LLM 账号/Key 可能被封禁或权限异常：{e}")
        except RateLimitError as e:
            raise RuntimeError(f"⚠️ LLM 触发限流：{e}")
        print(f"[EVAL] 过滤后保留 {len(filtered)} 条（原始 {len(segs)}）")

    sampled = sample_by_category(filtered, target)
    print(f"[EVAL] 按类别采样 {len(sampled)} 条（目标: {target}）")

    dev, test = split_dev_test(sampled, args.dev_ratio)
    print(f"[EVAL] 划分 Dev/Test -> Dev {len(dev)} | Test {len(test)}")

    out_dir.mkdir(parents=True, exist_ok=True)
    save_jsonl(sampled, out_dir / "pool.jsonl")
    save_jsonl(dev, out_dir / "dev.jsonl")
    save_jsonl(test, out_dir / "test.jsonl")
    print(f"[EVAL] 已保存到 {out_dir}")


if __name__ == "__main__":
    main()
