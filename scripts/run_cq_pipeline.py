"""
命令行演示：基于 CQ 的 TBox + 事件抽取全流程。

用法示例：
    python scripts/run_cq_pipeline.py --provider openai --model gpt-4o-mini
    python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash

注意：
* 需要提前设置对应的 API KEY（OPENAI_API_KEY / ZHIPU_API_KEY / GEMINI_API_KEY）；
* 默认使用 summary 中的领域说明与 1998 洪水示例段落，可通过参数替换。
"""
import argparse
from pathlib import Path
from typing import Optional

from kg.cq_pipeline import CQLLMPipeline, DEMO_DOMAIN_DESC, DEMO_PARAGRAPH_1998


def read_text_if_provided(path: Optional[str], fallback: str) -> str:
    """若传入文件路径则读取文件，否则返回默认文本。"""
    if path:
        return Path(path).read_text(encoding="utf-8")
    return fallback


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 CQ 驱动的长江灾害 KG 构建流程 (P1->P2->P5)")
    parser.add_argument(
        "--domain-file", help="领域说明文件路径，若不提供则使用示例描述", default=None)
    parser.add_argument("--paragraph-file",
                        help="待抽取的文本文件路径，若不提供则使用 1998 洪水示例", default=None)
    parser.add_argument("--provider", default="openai",
                        choices=["openai", "zhipu", "gemini"], help="LLM 提供商")
    parser.add_argument("--model", default=None,
                        help="模型名称，缺省则使用各 provider 的推荐默认值")
    parser.add_argument("--temperature", type=float,
                        default=0.1, help="采样温度，建议 JSON 模式保持较低")
    parser.add_argument("--n-cq", type=int, default=10, help="生成 CQ 的数量")
    parser.add_argument(
        "--output-dir", default="outputs/cq_pipeline", help="结果保存目录")

    args = parser.parse_args()

    llm_config = {
        "provider": args.provider,
        "model_name": args.model or ("gpt-4o-mini" if args.provider == "openai" else "glm-4.5-flash"),
        "temperature": args.temperature,
    }

    domain_desc = read_text_if_provided(args.domain_file, DEMO_DOMAIN_DESC)
    paragraph = read_text_if_provided(args.paragraph_file, DEMO_PARAGRAPH_1998)

    pipeline = CQLLMPipeline(llm_config=llm_config, output_dir=args.output_dir)
    out_dir = Path(args.output_dir)

    print("Step P1: 生成 CQ ...")
    cqs = pipeline.generate_cqs(
        domain_desc, n_cq=args.n_cq, save_path=out_dir / "p1_cqs.json")
    print(f"  ✅ 获得 {len(cqs)} 条 CQ，已保存到 {out_dir / 'p1_cqs.json'}")

    print("Step P2: CQ -> 初始 TBox ...")
    tbox = pipeline.cq_to_schema(cqs, save_path=out_dir / "p2_tbox_init.json")
    print(
        f"  ✅ 类 {len(tbox.classes)} 个，关系 {len(tbox.relations)} 条，已保存到 {out_dir / 'p2_tbox_init.json'}")

    # 可选：这里可以插入 P3/P4 的人工校验或继续调用 pipeline.refine_schema/pipeline.enhance_schema

    print("Step P5: 事件与三元组抽取 ...")
    p5_res = pipeline.extract_events(
        paragraph, tbox, save_path=out_dir / "p5_events.json")
    print(
        f"  ✅ 抽取事件 {len(p5_res.get('events', []))} 个，三元组 {len(p5_res.get('triples', []))} 条，"
        f"已保存到 {out_dir / 'p5_events.json'}"
    )


if __name__ == "__main__":
    main()
