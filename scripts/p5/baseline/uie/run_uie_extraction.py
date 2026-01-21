#!/usr/bin/env python3
"""
UIE PyTorch 批量抽取入口。

用法示例：
    python -m scripts.p5.baseline.uie -v batch \
        --test-file data/test.jsonl \
        --text-source data/text.jsonl \
        --tbox outputs/kg_final/tbox_final.json \
        --task-type re \
        --output outputs/eval_models/uie/predictions_re.jsonl \
        --skip-existing
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        stream=sys.stdout,
        force=True,
    )


def cmd_batch(args: argparse.Namespace) -> None:
    from .run_uie_baseline import run_batch_extraction
    run_batch_extraction(
        model_path=args.model_path,
        tbox_path=Path(args.tbox),
        test_file=Path(args.test_file),
        output_path=Path(args.output),
        task_type=args.task_type,
        text_source=args.text_source,
        limit=args.limit,
        skip_existing=args.skip_existing,
        precision=args.precision,
        batch_size=args.batch_size,
        interval=args.interval,
        log_file=args.log_file or None,
        verbose=args.verbose,
    )


def _load_run_prompt_batch():
    try:
        from .run_pp_uie_prompt import run_prompt_batch
        return run_prompt_batch
    except Exception:
        prompt_path = Path(__file__).resolve().parent / "run_pp_uie_prompt.py"
        spec = importlib.util.spec_from_file_location("run_pp_uie_prompt", prompt_path)
        if spec is None or spec.loader is None:
            raise ImportError("无法加载 run_pp_uie_prompt.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.run_prompt_batch


def cmd_prompt_batch(args: argparse.Namespace) -> None:
    run_prompt_batch = _load_run_prompt_batch()
    run_prompt_batch(
        model_name=args.model_name,
        tbox_path=Path(args.tbox),
        test_file=Path(args.test_file),
        output_path=Path(args.output),
        text_source=args.text_source,
        paddlenlp_home=args.paddlenlp_home,
        tensor_parallel_size=args.tensor_parallel_size,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        top_p=args.top_p,
        use_cot=not args.no_cot,
        use_graph=not args.no_graph,
        allow_system_role=not args.no_system_role,
        cot_fallback=not args.no_cot_fallback,
        debug_raw_output=args.debug_raw_output,
        raw_output_file=args.raw_output_file,
        prompt_task=args.prompt_task,
        fewshot=not args.no_fewshot,
        limit=args.limit,
        skip_existing=args.skip_existing,
        interval=args.interval,
        log_file=args.log_file or None,
        verbose=args.verbose,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UIE PyTorch 信息抽取系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    batch_parser = subparsers.add_parser("batch", help="批量抽取")
    batch_parser.add_argument("--test-file", "-i", required=True, help="测试集文件（jsonl）")
    batch_parser.add_argument("--output", "-o", required=True, help="输出文件（jsonl）")
    batch_parser.add_argument("--tbox", required=True, help="TBox 文件路径（json）")
    batch_parser.add_argument("--text-source", default=None, help="完整文本来源文件（jsonl）")
    batch_parser.add_argument(
        "--task-type",
        choices=["ner", "re", "all"],
        default="re",
        help="任务类型：ner / re / all（默认 re）",
    )
    batch_parser.add_argument(
        "--model-path",
        default="/hy-tmp/zjx/models/modelscope/yjx123456/uie-pytorch-base",
        help="UIE PyTorch 模型路径",
    )
    batch_parser.add_argument("--precision", default="float16", help="模型精度 (float16/bfloat16/float32)")
    batch_parser.add_argument("--batch-size", type=int, default=1, help="批处理大小（兼容参数）")
    batch_parser.add_argument("--limit", type=int, default=None, help="最多处理样本数")
    batch_parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的预测")
    batch_parser.add_argument("--interval", type=float, default=0.0, help="请求间隔秒数")
    batch_parser.add_argument("--log-file", default="", help="日志文件（可选）")
    batch_parser.add_argument("--http-timeout", type=int, default=300, help="兼容参数（UIE 不使用）")
    batch_parser.add_argument("--max-new-tokens", type=int, default=2048, help="兼容参数（UIE 不使用）")

    prompt_parser = subparsers.add_parser("prompt-batch", help="PP-UIE Prompt 批量抽取")
    prompt_parser.add_argument("--test-file", "-i", required=True, help="测试集文件（jsonl）")
    prompt_parser.add_argument("--output", "-o", required=True, help="输出文件（jsonl）")
    prompt_parser.add_argument("--tbox", required=True, help="TBox 文件路径（json）")
    prompt_parser.add_argument("--text-source", default=None, help="完整文本来源文件（jsonl）")
    prompt_parser.add_argument("--model-name", default="paddlenlp/PP-UIE-0.5B", help="PP-UIE 模型名称")
    prompt_parser.add_argument(
        "--paddlenlp-home",
        default="/hy-tmp/zjx/models/paddle",
        help="PaddleNLP 模型缓存目录",
    )
    prompt_parser.add_argument(
        "--tensor-parallel-size",
        type=int,
        default=1,
        help="Tensor 并行度（>1 需使用 paddle.distributed.launch 多进程启动）",
    )
    prompt_parser.add_argument("--max-new-tokens", type=int, default=1024, help="生成长度上限")
    prompt_parser.add_argument("--temperature", type=float, default=0.7, help="采样温度")
    prompt_parser.add_argument("--top-p", type=float, default=0.9, help="Top-P")
    prompt_parser.add_argument("--no-cot", action="store_true", help="禁用 CoT Prompt")
    prompt_parser.add_argument("--no-graph", action="store_true", help="禁用图结构 Prompt")
    prompt_parser.add_argument("--no-system-role", action="store_true", help="不使用 system role 提示词")
    prompt_parser.add_argument(
        "--no-cot-fallback",
        action="store_true",
        help="关闭 CoT 解析失败后的非 CoT 回退",
    )
    prompt_parser.add_argument(
        "--debug-raw-output",
        action="store_true",
        help="打印模型原始输出（便于排查 CoT 解析问题）",
    )
    prompt_parser.add_argument(
        "--raw-output-file",
        default="",
        help="RAW 输出保存路径（默认使用 output 的 .raw.log）",
    )
    prompt_parser.add_argument(
        "--prompt-task",
        choices=["p5", "ner", "re"],
        default="p5",
        help="Prompt 任务类型：p5(默认) / ner / re",
    )
    prompt_parser.add_argument(
        "--no-fewshot",
        action="store_true",
        help="关闭通用 Prompt 的 few-shot 示例",
    )
    prompt_parser.add_argument("--limit", type=int, default=None, help="最多处理样本数")
    prompt_parser.add_argument("--skip-existing", action="store_true", help="跳过已存在的预测")
    prompt_parser.add_argument("--interval", type=float, default=0.0, help="请求间隔秒数")
    prompt_parser.add_argument("--log-file", default="", help="日志文件（可选）")

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command == "batch":
        cmd_batch(args)
        return
    if args.command == "prompt-batch":
        cmd_prompt_batch(args)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
