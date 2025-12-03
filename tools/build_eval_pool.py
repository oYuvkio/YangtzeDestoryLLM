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
from typing import Dict, List, Tuple, Iterable
import sys
import yaml

# 确保脚本运行时能找到项目根下的 kg 包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.llm_core import LLMFactory, AccountBlockedError, RateLimitError  # noqa: E402
from kg.prompts import (  # noqa: E402
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

KEYWORDS_CORE = ["长江", "流域", "洪水", "干旱", "水旱",
                 "防汛", "抗旱", "蓄滞洪区", "应急响应", "防洪", "枯水"]
KEYWORDS_LAW = ["防汛", "抗旱", "应急", "预案", "响应"]


@dataclass
class Segment:
    id: str
    source_type: str
    doc_title: str
    year: int | None
    text: str
    rel_path: str
    filter_decision: dict | None = None


def cn_ratio(text: str) -> float:
    if not text:
        return 0.0
    cn = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cn / len(text)


def weird_ratio(text: str) -> float:
    if not text:
        return 0.0
    allowed = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ，。！？；：、“”‘’（）()《》<>-———…·%/\\ \n\r\t")
    weird = sum(1 for ch in text if ch not in allowed and not ("\u4e00" <= ch <= "\u9fff"))
    return weird / len(text)


def has_keywords(text: str, keywords: Iterable[str]) -> bool:
    return any(k in text for k in keywords)


def coarse_filter_segment(
    seg: Segment,
    *,
    min_cn_ratio: float = 0.3,
    max_weird_ratio: float = 0.3,
    require_keyword: bool = True,
) -> tuple[bool, str]:
    """
    规则级粗过滤：先挡掉明显乱码/无关文本，减少 LLM 调用。
    """
    cn_r = cn_ratio(seg.text)
    if cn_r < min_cn_ratio:
        return False, f"cn_ratio<{min_cn_ratio:.2f}"
    w_r = weird_ratio(seg.text)
    if w_r > max_weird_ratio:
        return False, f"weird_ratio>{max_weird_ratio:.2f}"
    if require_keyword:
        kws = KEYWORDS_CORE + (KEYWORDS_LAW if seg.source_type == "law_plan" else [])
        if not has_keywords(seg.text, kws):
            return False, "no_keyword"
    return True, "ok"


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


def _get_score(decision: dict, key: str) -> int:
    labels = decision.get("labels", {}) if isinstance(decision, dict) else {}
    val = labels.get(key)
    try:
        return int(val)
    except Exception:
        return -1


def keep_by_eval_rule(decision: dict) -> bool:
    """
    严格规则：relevance>=1 & kg_potential>=1 & cleanliness>=1 且 text_quality 非 garbled。
    与旧版字段兼容。
    """
    labels = decision.get("labels", {}) if isinstance(decision, dict) else {}
    domain = labels.get("is_water_disaster_domain")
    text_quality = labels.get("text_quality")
    if not domain:
        return False
    if text_quality == "garbled":
        return False
    relevance = _get_score(decision, "relevance_yangtze")
    kg_potential = _get_score(decision, "kg_potential")
    cleanliness = _get_score(decision, "cleanliness")
    if relevance >= 1 and kg_potential >= 1 and cleanliness >= 1:
        return True
    # 兼容旧 keep_for_eval 字段
    return bool(decision.get("keep_for_eval")) and text_quality in {"good", "noisy"}


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
        if keep_by_eval_rule(decision):
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


def _get_topic(seg: Segment) -> str:
    if seg.filter_decision and isinstance(seg.filter_decision, dict):
        labels = seg.filter_decision.get("labels", {})
        topic = labels.get("topic_label") or labels.get("main_topic")
        if topic:
            return str(topic)
    return "unknown"


def sample_by_category(segments: List[Segment], target: Dict[str, int]) -> List[Segment]:
    """
    分层随机采样：先按 source_type，再尽量覆盖不同 topic_label。
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
        topic_buckets: Dict[str, List[Segment]] = {}
        for s in pool:
            topic_buckets.setdefault(_get_topic(s), []).append(s)
        for lst in topic_buckets.values():
            random.shuffle(lst)

        picked: List[Segment] = []
        topics = list(topic_buckets.keys())
        # 轮询 topic，保证覆盖
        while len(picked) < num and topics:
            topics = [t for t in topics if topic_buckets.get(t)]
            if not topics:
                break
            for t in list(topics):
                if len(picked) >= num:
                    break
                if topic_buckets[t]:
                    picked.append(topic_buckets[t].pop())
        # 兜底：如仍不足，直接补齐
        if len(picked) < num:
            remaining = [s for lst in topic_buckets.values() for s in lst]
            random.shuffle(remaining)
            picked.extend(remaining[: max(0, num - len(picked))])

        sampled.extend(picked)
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
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="默认配置文件，命令行优先级更高")
    parser.add_argument("--root", default=None, help="源语料根目录，默认读 cfg.paths.corpus_full")
    parser.add_argument("--out-dir", default=None, help="输出目录，默认读 cfg.paths.eval_pool_dir")
    parser.add_argument("--min-chars", type=int, default=None, help="段落最小字符数，默认 150 或 cfg.filtering.eval.min_chars")
    parser.add_argument("--max-chars", type=int, default=None, help="段落最大字符数，默认 400 或 cfg.filtering.eval.max_chars")
    parser.add_argument("--target", nargs="+", default=None,
                        help="各类别抽取目标，如 law_plan=60 gazette_yearbook=80 ...，默认读 cfg.eval_pool.target")
    parser.add_argument("--dev-ratio", type=float, default=None, help="Dev 比例，默认 0.6 或 cfg.eval_pool.dev_ratio")
    parser.add_argument("--no-filter", action="store_true", help="跳过 LLM 质量过滤，保留全部段落")
    parser.add_argument("--refilter", action="store_true", help="忽略缓存，强制重新调用 LLM 过滤")
    parser.add_argument("--filter-cache", default=None, help="LLM 过滤缓存文件路径，默认在 out-dir/_eval_filter_cache.jsonl")
    parser.add_argument("--llm-provider", default=None, help="LLM provider（zhipu/openai/gemini），默认读取 cfg.llm.provider")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名，默认读取 cfg.llm.model_name")
    parser.add_argument("--llm-temperature", type=float, default=None, help="LLM 温度，默认读取 cfg.llm.temperature 或 0.0")
    parser.add_argument("--min-cn-ratio", type=float, default=None, help="汉字占比阈值，默认读 cfg.filtering.eval.min_cn_ratio")
    parser.add_argument("--max-weird-ratio", type=float, default=None, help="异常字符比例阈值，默认读 cfg.filtering.eval.max_weird_ratio")
    parser.add_argument("--no-keyword-filter", action="store_true", help="不强制关键词命中（默认启用关键词粗筛）")
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
    cfg_filter = cfg.get("filtering", {}).get("eval", {}) if isinstance(cfg, dict) else {}
    cfg_evalpool = cfg.get("eval_pool", {}) if isinstance(cfg, dict) else {}
    root = Path(pick(args.root, cfg_paths.get("corpus_full"), "data/corpus_for_kg/handled_all_kg_corpus"))
    out_dir = Path(pick(args.out_dir, cfg_paths.get("eval_pool_dir"), "data/p5_eval_pool"))
    if not root.exists():
        raise FileNotFoundError(f"源目录不存在：{root}")

    target_cfg = cfg_evalpool.get("target") or {}
    if args.target:
        target = parse_target(args.target)
    elif target_cfg:
        target = {k: int(v) for k, v in target_cfg.items()}
    else:
        target = {"law_plan": 60, "gazette_yearbook": 80, "case_paper": 100, "news_popular": 60}
    print(f"[EVAL] 扫描源目录: {root}")
    min_chars = pick(args.min_chars, cfg_filter.get("min_chars"), 150)
    max_chars = pick(args.max_chars, cfg_filter.get("max_chars"), 400)
    segs = collect_segments(root, min_chars, max_chars)
    print(f"[EVAL] 收集段落 {len(segs)} 条")
    # 粗过滤
    min_cn = pick(args.min_cn_ratio, cfg_filter.get("min_cn_ratio"), 0.3)
    max_weird = pick(args.max_weird_ratio, cfg_filter.get("max_weird_ratio"), 0.3)
    use_kw = not args.no_keyword_filter if args.no_keyword_filter else cfg.get("filtering", {}).get("keyword_filter", True)
    kept_coarse: List[Segment] = []
    dropped = 0
    for s in segs:
        ok, reason = coarse_filter_segment(
            s,
            min_cn_ratio=min_cn,
            max_weird_ratio=max_weird,
            require_keyword=use_kw,
        )
        if ok:
            kept_coarse.append(s)
        else:
            dropped += 1
    segs = kept_coarse
    print(f"[EVAL] 粗过滤后 {len(segs)} 条（丢弃 {dropped} 条明显无关/乱码）")

    # LLM 过滤
    if args.no_filter:
        filtered = segs
        print(f"[EVAL] 跳过 LLM 过滤，直接使用 {len(filtered)} 条")
    else:
        cache_path = Path(args.filter_cache) if args.filter_cache else out_dir / "_eval_filter_cache.jsonl"
        llm_conf: dict = {"temperature": pick(args.llm_temperature, cfg.get("llm", {}).get("temperature"), 0.0)}
        if args.llm_provider or cfg.get("llm", {}).get("provider"):
            llm_conf["provider"] = pick(args.llm_provider, cfg.get("llm", {}).get("provider"))
        if args.llm_model or cfg.get("llm", {}).get("model_name"):
            llm_conf["model_name"] = pick(args.llm_model, cfg.get("llm", {}).get("model_name"))
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
