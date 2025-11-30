"""
从规范化后的 TBox 直接启动 P5 事件抽取。

使用场景：
1) 已完成 P1/P2/P3，拿到了最终的 TBox JSON（包含 classes/relations/attributes）。
2) 希望跳过前置步骤，直接在 TBox 约束下对文本段落抽取事件与三元组。

示例：
    python scripts/p5_from_tbox.py \
        --tbox-file outputs/cq_pipeline/final/p4_tbox_augmented.json \
        --paragraph-file data/raw/sample_paragraph.txt \
        --provider openai --model gpt-4o-mini \
        --out outputs/cq_pipeline/final/p5_from_tbox.json
"""
import argparse
import json
from pathlib import Path
from typing import Optional

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
    parser = argparse.ArgumentParser(description="在规范化 TBox 约束下执行 P5 事件与三元组抽取")
    parser.add_argument(
        "--tbox-file",
        default="outputs/cq_pipeline/final/p4_tbox_augmented.json",
        help="包含 classes/relations/attributes 的 TBox JSON 路径（默认使用 final/p4_tbox_augmented.json）",
    )
    parser.add_argument("--paragraph-file", help="待抽取文本文件路径；缺省时从 stdin 读取")
    parser.add_argument("--provider", default="openai", choices=["openai", "zhipu", "gemini"], help="LLM 提供商")
    parser.add_argument("--model", default=None, help="模型名称，不填则使用各 provider 推荐默认值")
    parser.add_argument("--temperature", type=float, default=0.1, help="采样温度，建议 JSON 模式保持较低")
    parser.add_argument(
        "--out",
        default="outputs/cq_pipeline/final/p5_from_tbox.json",
        help="输出 JSON 路径（默认写入 final 目录）",
    )
    args = parser.parse_args()

    tbox_path = Path(args.tbox_file)
    if not tbox_path.exists():
        raise FileNotFoundError(f"TBox 文件不存在：{tbox_path}")

    paragraph = read_paragraph(args.paragraph_file)

    llm_config = {
        "provider": args.provider,
        "model_name": args.model or ("gpt-4o-mini" if args.provider == "openai" else "glm-4.5-flash"),
        "temperature": args.temperature,
    }

    print(f"加载 TBox: {tbox_path}")
    tbox = load_tbox(tbox_path)

    pipeline = CQLLMPipeline(llm_config=llm_config, output_dir=Path(args.out).parent.as_posix())

    print("执行 P5 抽取...")
    res = pipeline.extract_events(paragraph, schema=tbox, save_path=Path(args.out))

    print(
        f"完成：事件 {len(res.get('events', []))} 个，三元组 {len(res.get('triples', []))} 条，"
        f"已保存到 {args.out}"
    )


if __name__ == "__main__":
    main()
