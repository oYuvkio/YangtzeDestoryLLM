"""
对处理后的整库语料做“轻量级 LLM 裁判”过滤：
- 目标：快速剔除严重乱码或完全非水旱灾害领域的段落，避免后续 P5 抽取浪费配额。
- 规则（相对 eval_pool 更宽）：
  * 仅当 labels.is_water_disaster_domain = true 且 text_quality != "garbled" 才保留；
  * 不强制 contains_event_or_rule。
- 断点续跑：缓存每个段落的判定结果，避免重复调用 LLM。

输出：
  * 默认写入 data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl，字段同 Segment，附带 filter_decision。

使用示例：
python tools/filter_corpus_light.py \
  --root data/corpus_for_kg/handled_all_kg_corpus \
  --out data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl \
  --min-chars 80 --max-chars 600 \
  --llm-provider zhipu --llm-model glm-4.5-flash
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional
import sys
import os

import yaml

# 确保可以作为脚本运行时找到 kg 包
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.llm_core import LLMFactory, RateLimitError, AccountBlockedError  # noqa: E402
from kg.prompts import (  # noqa: E402
    EVAL_SEGMENT_FILTER_SYSTEM,
    EVAL_SEGMENT_FILTER_USER_TEMPLATE,
)
from tools.build_eval_pool import (  # noqa: E402
    collect_segments,
    load_filter_cache,
    save_filter_cache,
    Segment,
    coarse_filter_segment,
)


def judge_segment_light(seg: Segment, backend) -> dict:
    """
    调用 LLM 对段落做轻量过滤。
    失败或解析异常时，返回 keep_for_eval=False 的占位结果。
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
    except RateLimitError:
        raise
    except AccountBlockedError:
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


def keep_by_light_rule(decision: dict) -> bool:
    labels = decision.get("labels", {}) if isinstance(decision, dict) else {}
    domain = labels.get("is_water_disaster_domain")
    quality = labels.get("text_quality")
    cleanliness = labels.get("cleanliness")
    try:
        cleanliness_score = int(cleanliness)
    except Exception:
        cleanliness_score = -1
    return bool(domain) and quality != "garbled" and cleanliness_score != 0


def filter_corpus(
    segments: List[Segment],
    llm_conf: dict,
    cache_path: Path,
    refilter: bool = False,
    sleep_secs: float = 0.0,
    flush_every: int = 500,
    out_path: Path | None = None,
) -> List[Segment]:
    cache = {} if refilter else load_filter_cache(cache_path)
    print(f"[LIGHT] 已加载缓存 {len(cache)} 条（{cache_path}）")
    kept: List[Segment] = []
    updated_cache: Dict[str, dict] = dict(cache)

    # 已写出的段落 id，避免重复写入
    written_ids: set[str] = set()
    if out_path and out_path.exists():
        try:
            for line in out_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                obj = json.loads(line)
                seg_id = obj.get("id")
                if seg_id:
                    written_ids.add(seg_id)
        except Exception:
            pass

    # 确保输出目录存在
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    def process_one(seg: Segment):
        if not refilter and seg.id in cache:
            return seg, cache[seg.id], False
        backend_local = LLMFactory.create(llm_conf)
        decision = judge_segment_light(seg, backend_local)
        return seg, decision, True

    def maybe_flush_cache(force: bool = False):
        if not force and flush_every > 0 and len(updated_cache) % flush_every != 0:
            return
        save_filter_cache(updated_cache, cache_path)
        print(f"[LIGHT] 已刷新缓存 {len(updated_cache)} 条到 {cache_path}")

    def append_keep(seg_obj: Segment):
        if not out_path:
            return
        if seg_obj.id in written_ids:
            return
        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(seg_obj), ensure_ascii=False) + "\n")
        written_ids.add(seg_obj.id)
        print(
            f"[LIGHT] 已追加 keep 段落 {seg_obj.id}，累计写入 {len(written_ids)} 条 -> {out_path}")

    for seg in segments:
        if not refilter and seg.id in cache:
            decision = cache[seg.id]
            from_cache = True
        else:
            try:
                decision = judge_segment_light(
                    seg, LLMFactory.create(llm_conf))
            except RateLimitError as e:
                save_filter_cache(updated_cache, cache_path)
                print(f"⚠️ 遇到限流，已保存进度到缓存：{cache_path}，错误信息：{e}")
                return kept
            except AccountBlockedError as e:
                save_filter_cache(updated_cache, cache_path)
                raise RuntimeError(f"❌ LLM 账号或 Key 可能被封禁，需要人工检查：{e}")
            from_cache = False
            updated_cache[seg.id] = decision
        seg.filter_decision = decision
        if keep_by_light_rule(decision):
            kept.append(seg)
            append_keep(seg)
        maybe_flush_cache()
        keep_flag = decision.get("keep_for_eval")
        reason = decision.get("reason") or decision.get(
            "labels", {}).get("text_quality")
        print(
            f"[LIGHT] segment={seg.id} keep={keep_flag} cached={from_cache} reason={reason}")
        if sleep_secs > 0:
            import time
            time.sleep(sleep_secs)

    # 结束时确保至少写一次缓存与输出文件存在
    save_filter_cache(updated_cache, cache_path)
    if out_path and not out_path.exists():
        out_path.touch()
    print(f"[LIGHT] 已写入缓存 {len(updated_cache)} 条到 {cache_path}")
    return kept


def save_jsonl(objs: List[Segment], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for obj in objs:
            f.write(json.dumps(asdict(obj), ensure_ascii=False) + "\n")


def load_cfg_llm(cfg_path: Path) -> Dict[str, any]:
    if not cfg_path.exists():
        return {}
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return data.get("llm", {}) or {}
    except Exception:
        return {}


def resolve_llm_conf(
    args,
    cfg_path: Path = Path("configs/cfg.yaml"),
) -> Dict[str, any]:
    """
    按优先级选择 LLM 配置：CLI args > .env > cfg.yaml。
    """
    cfg_llm = load_cfg_llm(cfg_path)
    env_provider = os.getenv("LLM_PROVIDER")
    env_model = os.getenv("LLM_MODEL_NAME") or os.getenv("OPENAI_MODEL_API")
    env_temp = os.getenv("LLM_TEMPERATURE")
    env_thinking = os.getenv("LLM_THINKING_TYPE")
    env_api_key = os.getenv("LLM_API_KEY")
    env_base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")

    def pick(*vals, default=None):
        for v in vals:
            if v not in [None, ""]:
                return v
        return default

    provider = pick(args.llm_provider, env_provider,
                    cfg_llm.get("provider"), default="zhipu")
    model_name = pick(args.llm_model, env_model, cfg_llm.get(
        "model_name"), default="glm-4.5-flash")
    temp_val = pick(args.llm_temperature, env_temp, cfg_llm.get("temperature"))
    try:
        temperature = float(temp_val)
    except Exception:
        temperature = 0.0
    thinking_type = pick(args.llm_thinking, env_thinking,
                         cfg_llm.get("thinking_type"))
    api_key = pick(args.llm_api_key, env_api_key, cfg_llm.get("api_key"))
    base_url = pick(args.llm_base_url, env_base_url, cfg_llm.get("base_url"))

    llm_conf: Dict[str, any] = {
        "provider": provider,
        "model_name": model_name,
        "temperature": temperature,
    }
    if thinking_type:
        llm_conf["thinking_type"] = thinking_type
    if api_key:
        llm_conf["api_key"] = api_key
    if base_url:
        llm_conf["base_url"] = base_url
    return llm_conf


def main():

    # python tools/filter_corpus_light.py \
    #   --root data/corpus_for_kg/handled_all_kg_corpus \
    #   --out data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl \
    #   --num-workers 2 \
    #   --sleep-secs 4.0 \
    #   --llm-provider zhipu --llm-model "GLM-4.5-Air" \
    #   --llm-thinking enabled
    # # 如需临时 Key 或自定义 Base URL：
    # # --llm-api-key <your_key> --llm-base-url <your_base_url>

    parser = argparse.ArgumentParser(description="轻量级 LLM 过滤整库语料，剔除乱码或非水旱灾害内容")
    parser.add_argument(
        "--root", default="data/corpus_for_kg/handled_all_kg_corpus", help="源语料根目录")
    parser.add_argument(
        "--out", default="data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl", help="过滤后输出 jsonl 文件")
    parser.add_argument("--cfg", default="configs/cfg.yaml", help="默认配置文件，命令行优先级更高")
    parser.add_argument("--min-chars", type=int,
                        default=None, help="段落最小字符数，默认读 cfg.filtering.light 或 80")
    parser.add_argument("--max-chars", type=int,
                        default=None, help="段落最大字符数，默认读 cfg.filtering.light 或 600")
    parser.add_argument("--max-files", type=int, default=None,
                        help="仅处理前 N 个 txt 文件，便于小规模测试")
    parser.add_argument("--filter-cache", default=None,
                        help="LLM 过滤缓存文件路径，默认与 out 同目录下 _light_filter_cache.jsonl")
    parser.add_argument("--refilter", action="store_true",
                        help="忽略缓存，强制重跑 LLM 过滤")
    parser.add_argument("--llm-provider", default=None,
                        help="LLM provider（zhipu/openai/gemini），默认读取环境变量或 zhipu")
    parser.add_argument("--llm-model", default=None, help="LLM 模型名，默认读取环境变量")
    parser.add_argument("--llm-api-key", default=None,
                        help="LLM API Key，推荐从 .env 注入；仅测试/特例时通过命令行传入")
    parser.add_argument("--llm-base-url", default=None,
                        help="LLM Base URL，可用于 OpenAI 兼容自部署接口")
    parser.add_argument("--llm-temperature", type=float,
                        default=0.0, help="LLM 温度，默认 0.0（更稳定）")
    parser.add_argument("--llm-thinking", default=None, choices=["enabled", "disabled"],
                        help="仅对 zhipu 有效，控制 GLM 深度思考模式（enabled/disabled），默认跟随后端动态策略")
    parser.add_argument("--sleep-secs", type=float, default=0.0,
                        help="每次调用 LLM 后休眠秒数，用于手动控制 QPS")
    parser.add_argument("--flush-every", type=int, default=500,
                        help="每处理多少条刷新一次缓存/输出（<=1 表示每条都刷新）")
    parser.add_argument("--min-cn-ratio", type=float, default=None, help="汉字占比阈值，默认读 cfg.filtering.light")
    parser.add_argument("--max-weird-ratio", type=float, default=None, help="异常字符比例阈值，默认读 cfg.filtering.light")
    parser.add_argument("--no-keyword-filter", action="store_true", help="不强制关键词命中（默认启用关键词粗筛）")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise FileNotFoundError(f"源目录不存在：{root}")

    # 读取 cfg
    cfg = {}
    if args.cfg:
        cfg_path = Path(args.cfg)
        if cfg_path.exists():
            try:
                import yaml

                cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            except Exception:
                cfg = {}

    def pick(*vals, default=None):
        for v in vals:
            if v not in [None, ""]:
                return v
        return default

    cfg_paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}
    cfg_filter = cfg.get("filtering", {}).get("light", {}) if isinstance(cfg, dict) else {}
    out_path = Path(pick(args.out, cfg_paths.get("light_pool"), "data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl"))
    cache_path = (
        Path(args.filter_cache)
        if args.filter_cache
        else out_path.parent / "_light_filter_cache.jsonl"
    )

    llm_conf = resolve_llm_conf(args)

    print(f"[LIGHT] 扫描源目录: {root}")
    min_chars = pick(args.min_chars, cfg_filter.get("min_chars"), 80)
    max_chars = pick(args.max_chars, cfg_filter.get("max_chars"), 600)
    segs = collect_segments(root, min_chars, max_chars)
    if args.max_files:
        # 仅保留来自前 N 个文件的段落，便于快速验证流程
        seen_files = set()
        limited = []
        for seg in segs:
            if seg.rel_path not in seen_files:
                if len(seen_files) >= args.max_files:
                    continue
                seen_files.add(seg.rel_path)
            limited.append(seg)
        segs = limited
        print(f"[LIGHT] 收集段落 {len(segs)} 条（来源前 {len(seen_files)} 个文件）")
    else:
        print(f"[LIGHT] 收集段落 {len(segs)} 条")
    # 粗过滤
    min_cn = pick(args.min_cn_ratio, cfg_filter.get("min_cn_ratio"), 0.2)
    max_weird = pick(args.max_weird_ratio, cfg_filter.get("max_weird_ratio"), 0.4)
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
    print(f"[LIGHT] 粗过滤后 {len(segs)} 条（丢弃 {dropped} 条明显无关/乱码）")

    print(f"[LIGHT] 使用 LLM 过滤（缓存: {cache_path}）...")
    kept = filter_corpus(
        segs,
        llm_conf,
        cache_path=cache_path,
        refilter=args.refilter,
        sleep_secs=args.sleep_secs,
        flush_every=max(args.flush_every, 1),
        out_path=out_path,
    )
    print(f"[LIGHT] 过滤后保留 {len(kept)} 条（剔除 {len(segs) - len(kept)} 条）")

    # 末尾再写一份完整文件（防止中途只写部分 keep）
    save_jsonl(kept, out_path)
    if not out_path.exists():
        print(f"⚠️ 未找到输出文件，请检查路径/权限：{out_path}")
    else:
        print(f"[LIGHT] 输出文件已生成：{out_path}")


if __name__ == "__main__":
    main()
