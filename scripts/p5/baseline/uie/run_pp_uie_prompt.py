#!/usr/bin/env python3
"""
PP-UIE（PaddleNLP）Prompt 批量抽取。

使用与 run_ablation_unified.sh 相同的 P5 Prompt（含示例），进行批量抽取。
"""
from __future__ import annotations

import inspect
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
import re

IMPORT_ERROR: Exception | None = None
paddle = None
AutoModelForCausalLM = None
AutoTokenizer = None
GenerationConfig = None
llm_utils = None


def _import_paddle_modules():
    global IMPORT_ERROR, paddle, AutoModelForCausalLM, AutoTokenizer, GenerationConfig, llm_utils
    if AutoModelForCausalLM is not None and AutoTokenizer is not None:
        return
    try:
        import paddle as _paddle
        from paddlenlp.transformers import AutoModelForCausalLM as _AutoModelForCausalLM
        from paddlenlp.transformers import AutoTokenizer as _AutoTokenizer
        from paddlenlp.generation import GenerationConfig as _GenerationConfig
        from paddlenlp.trl import llm_utils as _llm_utils
        paddle = _paddle
        AutoModelForCausalLM = _AutoModelForCausalLM
        AutoTokenizer = _AutoTokenizer
        GenerationConfig = _GenerationConfig
        llm_utils = _llm_utils
    except Exception as exc:  # pragma: no cover
        IMPORT_ERROR = exc

# 添加项目根目录到 Python 路径，确保可导入 kg 包
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from kg.extraction_output import build_extraction_record
from kg.graph_structure import get_graph_structure_for_text, get_graph_structure
from kg.prompts import (
    EVENT_SCHEMA_HINT,
    P5_EXTRACTION_PROMPT,
    P5_GRAPH_COT_EXTRACTION_PROMPT,
    parse_cot_response,
    extract_cot_thought,
    UNIFIED_SYSTEM_PROMPT_COT,
)
from kg.utils.text_source import load_text_lookup, resolve_doc_id, resolve_source_text


GRAPH_TYPE_CONFIDENCE_THRESHOLD = 0.3


def setup_logger(log_file: Optional[str], verbose: bool) -> logging.Logger:
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True,
    )
    return logging.getLogger(__name__)


def configure_paddlenlp_home(path: Optional[str]) -> None:
    if not path:
        return
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    os.environ["PPNLP_HOME"] = str(target)
    os.environ.setdefault("PADDLE_HOME", str(target))


def load_tbox_json(tbox_path: Path) -> Dict[str, Any]:
    return json.loads(tbox_path.read_text(encoding="utf-8"))


def build_prompt(
    schema_json: Dict[str, Any],
    input_text: str,
    *,
    use_cot: bool,
    use_graph: bool,
    allow_system_role: bool,
    include_example: bool = True,
) -> str:
    class_usage_hint = "优先使用 TBox 中已有的类名，不要随意创造新的事件类型；倾向用已有类 + 属性表达。"
    if use_cot:
        if use_graph:
            graph_structure, _, confidence = get_graph_structure_for_text(input_text)
            if confidence < GRAPH_TYPE_CONFIDENCE_THRESHOLD:
                graph_structure = get_graph_structure("general_disaster")
        else:
            graph_structure = get_graph_structure("general_disaster")
        graph_prompt = graph_structure.format_for_prompt()
        graph_steps = "\n\n".join(graph_structure.get_cot_steps())
        user_prompt = P5_GRAPH_COT_EXTRACTION_PROMPT.format(
            schema_json=json.dumps(schema_json, ensure_ascii=False, indent=2),
            event_schema=EVENT_SCHEMA_HINT,
            input_text=input_text.strip(),
            class_usage_hint=class_usage_hint,
            graph_prompt=graph_prompt,
            graph_steps=graph_steps,
        )
        if allow_system_role:
            return f"{UNIFIED_SYSTEM_PROMPT_COT}\n\n{user_prompt}"
        return f"{UNIFIED_SYSTEM_PROMPT_COT}\n\n{user_prompt}"
    user_prompt = P5_EXTRACTION_PROMPT.format(
        schema_json=json.dumps(schema_json, ensure_ascii=False, indent=2),
        event_schema=EVENT_SCHEMA_HINT,
        input_text=input_text.strip(),
        class_usage_hint=class_usage_hint,
    )
    if not include_example:
        marker = "参考输出结构示例"
        if marker in user_prompt:
            user_prompt = user_prompt.split(marker, 1)[0].rstrip()
        user_prompt = (
            user_prompt
            + "\n\n【严格输出要求】\n"
            + "1) 只输出一个 JSON 对象，必须以 { 开头、以 } 结束。\n"
            + "2) JSON 顶层必须包含 events 和 triples 两个字段。\n"
            + "3) 不要输出示例、解释或额外文本。\n"
        )
    return user_prompt


def build_ner_prompt(schema_json: Dict[str, Any], input_text: str, *, fewshot: bool = True) -> str:
    classes = schema_json.get("classes", []) or []
    type_list = [c.get("name") for c in classes if c.get("name")]
    type_lines = "\n".join([f"- {t}" for t in type_list[:200]])
    prompt = (
        "你是信息抽取系统。请从文本中抽取实体。\n"
        "【实体类型列表】（只能从列表中选择，禁止原样输出列表本身）\n"
        f"{type_lines}\n\n"
        "要求：实体必须是原文子串，不要改写；找不到就返回空列表。\n"
        "仅输出 JSON，格式如下：\n"
        "{\"entities\":[{\"name\":\"\",\"type\":\"\"}]}\n"
    )
    if fewshot:
        prompt += (
            "\n示例（仅展示格式，不要照抄示例内容或类型）：\n"
            "文本：示例文本\n"
            "输出：{\"entities\":[{\"name\":\"示例实体\",\"type\":\"示例类型\"}]}\n"
        )
    prompt += f"\n文本：{input_text}"
    return prompt


def build_re_prompt(schema_json: Dict[str, Any], input_text: str, *, fewshot: bool = True) -> str:
    relations = schema_json.get("relations", []) or []
    rel_list = [r.get("name") for r in relations if r.get("name")]
    rel_lines = "\n".join([f"- {r}" for r in rel_list[:200]])
    prompt = (
        "你是信息抽取系统。请从文本中抽取关系三元组。\n"
        "【关系类型列表】（只能从列表中选择，禁止原样输出列表本身）\n"
        f"{rel_lines}\n\n"
        "要求：subject/object 必须是原文子串；如果没有则返回空列表。\n"
        "仅输出 JSON，格式如下：\n"
        "{\"triples\":[{\"subject\":\"\",\"predicate\":\"\",\"object\":\"\"}]}\n"
    )
    if fewshot:
        prompt += (
            "\n示例（仅展示格式，不要照抄示例内容或关系）：\n"
            "文本：示例文本\n"
            "输出：{\"triples\":[{\"subject\":\"示例主体\",\"predicate\":\"示例关系\",\"object\":\"示例客体\"}]}\n"
        )
    prompt += f"\n文本：{input_text}"
    return prompt


def _strip_code_fence(text: str) -> str:
    cleaned = (text or "").strip()
    if cleaned.startswith("```") and cleaned.endswith("```"):
        lines = cleaned.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _has_p5_keys(obj: Any) -> bool:
    return isinstance(obj, dict) and ("events" in obj or "triples" in obj)


def safe_json_load(raw: str) -> Dict[str, Any]:
    cleaned = _strip_code_fence(raw)
    if not cleaned:
        return {}
    try:
        obj = json.loads(cleaned)
    except Exception:
        obj = None
    if obj is None:
        match = re.search(r"(\{[\s\S]*\}|\[[\s\S]*\])", cleaned)
        if match:
            snippet = match.group(1)
            try:
                obj = json.loads(snippet)
            except Exception:
                obj = None
    if isinstance(obj, dict):
        return obj
    if isinstance(obj, list):
        return {"events": obj}
    return {}


def _infer_tensor_parallel_param(tp_size: int) -> Dict[str, Any]:
    if tp_size <= 1:
        return {}
    if AutoModelForCausalLM is None:
        return {}
    params = inspect.signature(AutoModelForCausalLM.from_pretrained).parameters
    if "tensor_parallel_degree" in params:
        return {"tensor_parallel_degree": tp_size}
    if "tensor_parallel_size" in params:
        return {"tensor_parallel_size": tp_size}
    if "tensor_parallel" in params:
        return {"tensor_parallel": tp_size}
    return {}


def _init_distributed(tp_size: int, logger: logging.Logger) -> int:
    if tp_size <= 1 or paddle is None:
        return 1
    trainers_num = int(os.getenv("PADDLE_TRAINERS_NUM", "1"))
    if trainers_num <= 1:
        logger.warning(
            "tensor_parallel_size=%s 需要使用 paddle.distributed.launch 多进程启动，"
            "已回退为单卡。",
            tp_size,
        )
        return 1
    if not paddle.distributed.is_initialized():
        paddle.distributed.init_parallel_env()
    world_size = paddle.distributed.get_world_size()
    if world_size > 0 and tp_size > world_size:
        logger.warning("tensor_parallel_size=%s 大于 world_size=%s，已回退为 %s。", tp_size, world_size, world_size)
        return world_size
    return tp_size


def load_model(model_name: str, tp_size: int, logger: logging.Logger):
    _import_paddle_modules()
    if AutoModelForCausalLM is None or AutoTokenizer is None:
        detail = f"{IMPORT_ERROR!r}" if IMPORT_ERROR else "unknown import error"
        raise RuntimeError(f"未能导入 paddlenlp / paddle: {detail}")
    if paddle is not None:
        device = "gpu" if paddle.is_compiled_with_cuda() else "cpu"
        paddle.set_device(device)
    tp_size = _init_distributed(tp_size, logger)
    tp_kwargs = _infer_tensor_parallel_param(tp_size)
    if tp_size > 1 and not tp_kwargs:
        logger.warning("当前 paddlenlp 版本不支持 tensor parallel 参数，已回退单卡。")
        tp_size = 1
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        use_flash_attention=False,
        **tp_kwargs,
    )
    model.eval()
    tokenizer = AutoTokenizer.from_pretrained(model_name, padding_side="left")
    generation_config = GenerationConfig.from_pretrained(model_name)
    return model, tokenizer, generation_config


def generate_text(
    model: Any,
    tokenizer: Any,
    generation_config: Any,
    prompt: str,
    *,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
) -> str:
    if hasattr(tokenizer, "apply_chat_template"):
        try:
            prompt_text = tokenizer.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
            )
        except Exception:
            prompt_text = tokenizer.apply_chat_template(prompt, tokenize=False)
    else:
        prompt_text = prompt
    input_features = tokenizer(
        [prompt_text],
        max_length=4096,
        return_position_ids=False,
        truncation=True,
        truncation_side="left",
        padding=True,
        return_tensors="pd",
        add_special_tokens=False,
    )
    decode_strategy = "greedy_search" if temperature <= 0 else "sampling"
    outputs = model.generate(
        **input_features,
        max_new_tokens=max_new_tokens,
        bos_token_id=tokenizer.bos_token_id,
        eos_token_id=llm_utils.get_eos_token_id(tokenizer, generation_config),
        pad_token_id=tokenizer.pad_token_id,
        decode_strategy=decode_strategy,
        temperature=max(temperature, 0.0),
        top_k=1,
        top_p=top_p if top_p > 0 else 1.0,
        repetition_penalty=1.0,
    )
    results = tokenizer.batch_decode(outputs[0], skip_special_tokens=True, clean_up_tokenization_spaces=False)
    return results[0] if results else ""


def run_prompt_batch(
    *,
    model_name: str,
    tbox_path: Path,
    test_file: Path,
    output_path: Path,
    text_source: Optional[str],
    paddlenlp_home: Optional[str],
    tensor_parallel_size: int,
    max_new_tokens: int,
    temperature: float,
    top_p: float,
    use_cot: bool,
    use_graph: bool,
    allow_system_role: bool,
    cot_fallback: bool,
    debug_raw_output: bool,
    raw_output_file: Optional[str],
    prompt_task: str,
    fewshot: bool,
    limit: Optional[int],
    skip_existing: bool,
    interval: float,
    log_file: Optional[str],
    verbose: bool,
) -> None:
    logger = setup_logger(log_file, verbose)
    configure_paddlenlp_home(paddlenlp_home)
    if not tbox_path.exists():
        logger.error(f"TBox 文件不存在: {tbox_path}")
        return
    if not test_file.exists():
        logger.error(f"测试集文件不存在: {test_file}")
        return

    schema_json = load_tbox_json(tbox_path)
    model, tokenizer, generation_config = load_model(model_name, tensor_parallel_size, logger)
    rank = 0
    if paddle is not None and paddle.distributed.is_initialized():
        rank = paddle.distributed.get_rank()
    is_main = rank == 0
    if not is_main:
        logger.info("[Rank %s] 非主进程，仅参与计算不写输出。", rank)

    samples = []
    with test_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                samples.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    if limit:
        samples = samples[:limit]
    logger.info(f"样本数: {len(samples)}")

    text_lookup: Dict[str, str] = {}
    if text_source:
        logger.info(f"加载完整文本来源: {text_source}")
        try:
            text_lookup = load_text_lookup(Path(text_source), text_field="source_text")
            if not text_lookup:
                text_lookup = load_text_lookup(Path(text_source), text_field="text")
        except FileNotFoundError as exc:
            logger.error(str(exc))
            return
        logger.info(f"已加载 {len(text_lookup)} 条完整文本")

    existing_predictions: Dict[str, Dict[str, Any]] = {}
    if skip_existing and output_path.exists():
        for line in output_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                doc_id = obj.get("doc_id", "")
                if doc_id:
                    existing_predictions[doc_id] = obj
            except Exception:
                continue
        logger.info(f"已有预测: {len(existing_predictions)} 条")

    raw_f = None
    if is_main:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if debug_raw_output:
            raw_path = Path(raw_output_file) if raw_output_file else output_path.with_suffix(".raw.log")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_f = raw_path.open("a", encoding="utf-8")
            logger.info("RAW 输出日志: %s", raw_path)
    write_mode = "a" if skip_existing and output_path.exists() else "w"
    out_f = output_path.open(write_mode, encoding="utf-8") if is_main else None
    try:
        for idx, sample in enumerate(samples, start=1):
            doc_id = resolve_doc_id(sample, idx)
            source_text, source_tag = resolve_source_text(
                sample,
                doc_id,
                text_lookup,
                require_text_source=bool(text_source),
            )
            if doc_id in existing_predictions:
                if is_main:
                    logger.info(f"[{idx}/{len(samples)}] {doc_id}: 跳过已存在")
                continue
            if not source_text:
                error_reason = (
                    "missing_text_source"
                    if source_tag == "missing_text_source"
                    else "empty_source_text"
                )
                logger.warning(f"[{idx}/{len(samples)}] {doc_id}: 无有效文本({source_tag})")
                record = build_extraction_record(
                    doc_id=doc_id,
                    source_text="",
                    extraction_result=None,
                    use_cot=use_cot,
                    use_verify=False,
                    include_source_text=False,
                    error=error_reason,
                )
                if is_main and out_f is not None:
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_f.flush()
                continue

            if prompt_task == "ner":
                prompt = build_ner_prompt(schema_json, source_text, fewshot=fewshot)
            elif prompt_task == "re":
                prompt = build_re_prompt(schema_json, source_text, fewshot=fewshot)
            else:
                prompt = build_prompt(
                    schema_json=schema_json,
                    input_text=source_text,
                    use_cot=use_cot,
                    use_graph=use_graph,
                    allow_system_role=allow_system_role,
                )
            try:
                raw_text = generate_text(
                    model,
                    tokenizer,
                    generation_config,
                    prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p,
                )
                if debug_raw_output and is_main and raw_f is not None:
                    raw_f.write(f"\n===== {idx}/{len(samples)} doc_id={doc_id} mode=cot =====\n")
                    raw_f.write(str(raw_text))
                    raw_f.write("\n")
                    raw_f.flush()
                thought = ""
                record_use_cot = use_cot and prompt_task == "p5"
                if record_use_cot:
                    thought = extract_cot_thought(raw_text)
                    parsed = parse_cot_response(raw_text)
                    if (parsed is None or not _has_p5_keys(parsed)) and cot_fallback:
                        logger.warning(
                            "[%s/%s] %s: CoT 解析失败，回退到非 CoT JSON Prompt",
                            idx,
                            len(samples),
                            doc_id,
                        )
                        fallback_prompt = build_prompt(
                            schema_json=schema_json,
                            input_text=source_text,
                            use_cot=False,
                            use_graph=False,
                            allow_system_role=allow_system_role,
                            include_example=False,
                        )
                        raw_text = generate_text(
                            model,
                            tokenizer,
                            generation_config,
                            fallback_prompt,
                            max_new_tokens=max_new_tokens,
                            temperature=temperature,
                            top_p=top_p,
                        )
                        if debug_raw_output and is_main and raw_f is not None:
                            raw_f.write(f"\n===== {idx}/{len(samples)} doc_id={doc_id} mode=fallback =====\n")
                            raw_f.write(str(raw_text))
                            raw_f.write("\n")
                            raw_f.flush()
                        parsed = safe_json_load(raw_text)
                        record_use_cot = False
                    if parsed is None:
                        parsed = {"events": [], "triples": [], "error": "cot_parse_failed"}
                else:
                    parsed = safe_json_load(raw_text)
                    if not isinstance(parsed, dict):
                        parsed = {"events": [], "triples": [], "error": "invalid_response_type"}
                if prompt_task == "ner":
                    entities = parsed.get("entities", []) if isinstance(parsed, dict) else []
                    parsed = {"entities": entities, "events": [], "triples": []}
                elif prompt_task == "re":
                    triples = parsed.get("triples", []) if isinstance(parsed, dict) else []
                    parsed = {"entities": [], "events": [], "triples": triples}
                else:
                    if not _has_p5_keys(parsed):
                        parsed = {"events": [], "triples": [], "error": "missing_events_triples"}

                extraction_result = parsed if isinstance(parsed, dict) else {}
                if thought:
                    extraction_result["thought"] = thought
                record = build_extraction_record(
                    doc_id=doc_id,
                    source_text=source_text,
                    extraction_result=extraction_result,
                    use_cot=record_use_cot,
                    use_verify=False,
                    include_source_text=False,
                )
                if is_main and out_f is not None:
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_f.flush()
                    logger.info(
                        f"[{idx}/{len(samples)}] {doc_id}: 事件={len(record.get('events', []))}, "
                        f"三元组={len(record.get('triples', []))}"
                    )
            except Exception as exc:
                logger.warning(f"[{idx}/{len(samples)}] {doc_id}: 推理失败 - {exc}")
                record = build_extraction_record(
                    doc_id=doc_id,
                    source_text=source_text,
                    extraction_result=None,
                    use_cot=use_cot,
                    use_verify=False,
                    include_source_text=False,
                    error=str(exc),
                )
                if is_main and out_f is not None:
                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    out_f.flush()

            if interval > 0 and idx < len(samples):
                time.sleep(interval)
    finally:
        if out_f is not None:
            out_f.close()
        if raw_f is not None:
            raw_f.close()
