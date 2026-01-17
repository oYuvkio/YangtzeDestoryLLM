#!/usr/bin/env python3
"""
YAYI-UIE 信息抽取主入口脚本

支持两种运行模式：
1. HTTP 服务模式：启动 FastAPI 服务
2. 批量处理模式：从 JSONL 文件批量抽取

使用方式：
    # 启动 HTTP 服务
    python run_yayi_extraction.py server --port 8000
    
    # 批量抽取
    python run_yayi_extraction.py batch \
        --test-file data/test.jsonl \
        --output outputs/predictions.jsonl \
        --task-type re
    
    # 评测
    python run_yayi_extraction.py evaluate \
        --gold data/gold.jsonl \
        --pred outputs/predictions.jsonl
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def setup_logging(verbose: bool = False):
    """设置日志"""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_server(args):
    """启动 HTTP 服务"""
    from scripts.p5.baseline.yayi_uie.config import ModelConfig, ServiceConfig
    from scripts.p5.baseline.yayi_uie.api import run_server
    
    model_config = ModelConfig(
        model_path=args.model_path,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )
    
    service_config = ServiceConfig(
        host=args.host,
        port=args.port,
        workers=args.workers,
        verbose=args.verbose,
    )
    
    run_server(model_config, service_config)


def cmd_batch(args):
    """批量抽取"""
    from scripts.p5.baseline.yayi_uie.config import ModelConfig
    from scripts.p5.baseline.yayi_uie.batch import run_batch_extraction
    
    model_config = ModelConfig(
        model_path=args.model_path,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )
    
    run_batch_extraction(
        test_file=Path(args.test_file),
        output_path=Path(args.output),
        task_type=args.task_type,
        model_config=model_config,
        tbox_path=Path(args.tbox) if args.tbox else None,
        text_source_path=Path(args.text_source) if args.text_source else None,
        limit=args.limit,
        skip_existing=args.skip_existing,
        verbose=args.verbose,
        interval=args.interval,
    )


def cmd_evaluate(args):
    """评测"""
    from scripts.p5.baseline.yayi_uie.evaluate import evaluate
    
    output_path = Path(args.output) if args.output else None
    evaluate(Path(args.gold), Path(args.pred), output_path)


def main():
    parser = argparse.ArgumentParser(
        description="YAYI-UIE 信息抽取系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # server 子命令
    server_parser = subparsers.add_parser("server", help="启动 HTTP 服务")
    server_parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    server_parser.add_argument("--port", type=int, default=8000, help="监听端口")
    server_parser.add_argument("--workers", type=int, default=1, help="工作进程数")
    server_parser.add_argument("--model-path", default="/hy-tmp/zjx/models/modelscope/wenge-research/yayi-uie")
    server_parser.add_argument("--max-new-tokens", type=int, default=2048)
    server_parser.add_argument("--temperature", type=float, default=0.0)
    
    # batch 子命令
    batch_parser = subparsers.add_parser("batch", help="批量抽取")
    batch_parser.add_argument("--test-file", "-i", required=True, help="测试集文件（提供 doc_id 列表）")
    batch_parser.add_argument("--output", "-o", required=True, help="输出文件")
    batch_parser.add_argument("--tbox", default=None, help="TBox 文件")
    batch_parser.add_argument("--text-source", default=None, help="完整文本来源文件（用 doc_id 映射获取 text）")
    batch_parser.add_argument("--task-type", "-t", choices=["ner", "re", "ee", "ner+re", "all"], default="ner+re",
                              help="任务类型: ner/re/ee 单任务，ner+re 实体+关系，all 全部任务")
    batch_parser.add_argument("--model-path", default="/hy-tmp/zjx/models/modelscope/wenge-research/yayi-uie")
    batch_parser.add_argument("--max-new-tokens", type=int, default=2048)
    batch_parser.add_argument("--temperature", type=float, default=0.0)
    batch_parser.add_argument("--limit", type=int, default=None)
    batch_parser.add_argument("--skip-existing", action="store_true")
    batch_parser.add_argument("--interval", type=float, default=0.0)
    
    # evaluate 子命令
    eval_parser = subparsers.add_parser("evaluate", help="评测")
    eval_parser.add_argument("--gold", "-g", required=True, help="gold 文件")
    eval_parser.add_argument("--pred", "-p", required=True, help="预测文件")
    eval_parser.add_argument("--output", "-o", default=None, help="输出报告")
    
    args = parser.parse_args()
    setup_logging(args.verbose)
    
    if args.command == "server":
        cmd_server(args)
    elif args.command == "batch":
        cmd_batch(args)
    elif args.command == "evaluate":
        cmd_evaluate(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
