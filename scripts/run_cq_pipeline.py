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
import json
from pathlib import Path
from typing import Optional

import yaml

from kg.cq_pipeline import (
    CQLLMPipeline,
    TBoxSchema,
    ClassDef,
    RelationDef,
    AttributeDef,
    DEMO_DOMAIN_DESC,
    DEMO_PARAGRAPH_1998,
)
from kg.utils.deduplication import EmbeddingDeduplicator
from kg.utils.conflict_detection import detect_schema_conflicts, summarize_conflicts
from kg.utils.entity_linking import normalize_extraction_result


def read_text_if_provided(path: Optional[str], fallback: str) -> str:
    """若传入文件路径则读取文件，否则返回默认文本。"""
    if path:
        return Path(path).read_text(encoding="utf-8")
    return fallback


def main() -> None:
    parser = argparse.ArgumentParser(
        description="运行 CQ 驱动的长江灾害 KG 构建流程，可指定起点阶段 (P1/P2/P3/P4/P5)")
    parser.add_argument("--cfg", default="configs/cfg.yaml",
                        help="默认配置文件（命令行优先级最高，cfg 作为默认值来源）")
    parser.add_argument(
        "--domain-file", help="领域说明文件路径，若不提供则使用示例描述", default=None)
    parser.add_argument("--paragraph-file",
                        help="待抽取的文本文件路径，若不提供则使用 1998 洪水示例", default=None)
    parser.add_argument("--provider", default=None,
                        choices=["openai", "zhipu", "gemini"], help="LLM 提供商（默认读取 cfg 或 openai）")
    parser.add_argument("--model", default=None,
                        help="模型名称，缺省则读取 cfg 或 provider 默认值")
    parser.add_argument("--temperature", type=float,
                        default=None, help="采样温度，建议 JSON 模式保持较低（默认读 cfg 或 0.1）")
    parser.add_argument("--n-cq", type=int, default=10, help="生成 CQ 的数量")
    parser.add_argument(
        "--output-dir", default=None, help="结果保存目录（默认读 cfg.paths.output_dir）")
    parser.add_argument("--start-step", choices=["p1", "p2", "p3", "p4", "p5"], default="p1",
                        help="从哪个阶段开始运行，之后步骤依次继续")
    parser.add_argument("--cqs-file", help="直接读取已有 CQ 文件（JSON，含 cqs 字段或 CQ 列表）")
    parser.add_argument("--p2-file", help="已有 P2 初始 TBox 路径（跳过 P1/P2 时使用）")
    parser.add_argument("--p3-file", help="已有 P3 规范化后的 TBox 路径（跳过 P1-P3 时使用）")
    parser.add_argument("--p4-file", help="已有 P4 增强后的 TBox 路径（跳过 P1-P4 时使用）")
    parser.add_argument("--favor-existing-classes", action="store_true",
                        help="P5 抽取时提示优先使用已有类（保守模式）")
    parser.add_argument("--dedup-schema", action="store_true",
                        help="在 P2/P3 后对类/关系做 embedding 去重（默认读 cfg.dedup_schema.enabled）")
    parser.add_argument("--dedup-threshold", type=float, default=None,
                        help="去重相似度阈值（默认读 cfg.dedup_schema.threshold 或 0.75）")
    parser.add_argument("--normalize-entities", action="store_true",
                        help="P5 输出后做实体标准化（地点别名等），默认读 cfg.p5.normalize_entities")

    args = parser.parse_args()

    # 读取 cfg
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

    cfg_llm = cfg.get("llm", {}) if isinstance(cfg, dict) else {}
    cfg_llm_stage = cfg.get("llm_per_stage", {}) if isinstance(cfg, dict) else {}
    cfg_paths = cfg.get("paths", {}) if isinstance(cfg, dict) else {}
    cfg_p5 = cfg.get("p5", {}) if isinstance(cfg, dict) else {}
    cfg_dedup = cfg.get("dedup_schema", {}) if isinstance(cfg, dict) else {}

    def stage_llm_conf(stage: str) -> dict:
        """按优先级获取阶段专用 LLM 配置：CLI > cfg.llm_per_stage[stage] > cfg.llm > 默认。"""
        st = cfg_llm_stage.get(stage, {}) if isinstance(cfg_llm_stage, dict) else {}
        provider_val = pick(args.provider, st.get("provider"), cfg_llm.get("provider"), "openai")
        model_val = pick(
            args.model,
            st.get("model_name"),
            cfg_llm.get("model_name"),
            "gpt-4o-mini" if provider_val == "openai" else "glm-4.5-flash",
        )
        temp_val = pick(args.temperature, st.get("temperature"), cfg_llm.get("temperature"), 0.1)
        return {
            "provider": provider_val,
            "model_name": model_val,
            "temperature": temp_val,
            "thinking_type": cfg_llm.get("thinking_type"),
        }
    output_dir = pick(args.output_dir, cfg_paths.get("output_dir"), "outputs/cq_pipeline/final")
    favor_existing = pick(args.favor_existing_classes, cfg_p5.get("favor_existing_classes"), True)
    dedup_schema_flag = pick(args.dedup_schema, cfg_dedup.get("enabled"), False)
    dedup_threshold = pick(args.dedup_threshold, cfg_dedup.get("threshold"), 0.75)
    normalize_entities = pick(args.normalize_entities, cfg_p5.get("normalize_entities"), False)

    domain_desc = read_text_if_provided(args.domain_file, DEMO_DOMAIN_DESC)
    paragraph = read_text_if_provided(args.paragraph_file, DEMO_PARAGRAPH_1998)
    out_dir = Path(output_dir)

    # ---------- P1 ----------
    if args.start_step == "p1":
        llm_conf_p1 = stage_llm_conf("p1")
        print(f"[LLM][P1] provider={llm_conf_p1['provider']}, model={llm_conf_p1['model_name']}, temp={llm_conf_p1['temperature']}")
        pipeline = CQLLMPipeline(llm_config=llm_conf_p1, output_dir=output_dir)
        print("Step P1: 生成 CQ ...")
        cqs = pipeline.generate_cqs(
            domain_desc, n_cq=args.n_cq, save_path=out_dir / "p1_cqs.json")
        print(f"  ✅ 获得 {len(cqs)} 条 CQ，已保存到 {out_dir / 'p1_cqs.json'}")
    else:
        if args.cqs_file:
            cqs_path = Path(args.cqs_file)
        else:
            cqs_path = out_dir / "p1_cqs.json"
        cqs_json = json.loads(cqs_path.read_text(encoding="utf-8"))
        if isinstance(cqs_json, dict) and "cqs" in cqs_json:
            from kg.cq_pipeline import CQ
            cqs = [CQ(**c) for c in cqs_json["cqs"]]
        else:
            cqs = cqs_json
        print(f"[SKIP] 直接使用已有 CQ：{cqs_path}")

    # ---------- P2 ----------
    if args.start_step in ["p1", "p2"]:
        llm_conf_p2 = stage_llm_conf("p2")
        print(f"[LLM][P2] provider={llm_conf_p2['provider']}, model={llm_conf_p2['model_name']}, temp={llm_conf_p2['temperature']}")
        pipeline = CQLLMPipeline(llm_config=llm_conf_p2, output_dir=output_dir)
        print("Step P2: CQ -> 初始 TBox ...")
        tbox = pipeline.cq_to_schema(cqs, save_path=out_dir / "p2_tbox_init.json")
        print(
            f"  ✅ 类 {len(tbox.classes)} 个，关系 {len(tbox.relations)} 条，已保存到 {out_dir / 'p2_tbox_init.json'}")
        if dedup_schema_flag:
            print(f"  去重中（threshold={dedup_threshold}) ...")
            tbox = pipeline.deduplicate_tbox(tbox, threshold=float(dedup_threshold))
            pipeline._dump_json(tbox.to_dict(), out_dir / "p2_tbox_init_dedup.json")
            print(f"  ✅ 去重后：类 {len(tbox.classes)}，关系 {len(tbox.relations)}")
    else:
        tbox_path = Path(args.p2_file or out_dir / "p2_tbox_init.json")
        data = json.loads(tbox_path.read_text(encoding="utf-8"))
        tbox = TBoxSchema(
            classes=[ClassDef(**c) for c in data["classes"]],
            relations=[RelationDef(**r) for r in data["relations"]],
            attributes=[AttributeDef(**a) for a in data["attributes"]],
        )
        print(f"[SKIP] 直接使用已有 P2 TBox：{tbox_path}")

    # ---------- P3 ----------
    if args.start_step in ["p1", "p2", "p3"]:
        llm_conf_p3 = stage_llm_conf("p3")
        print(f"[LLM][P3] provider={llm_conf_p3['provider']}, model={llm_conf_p3['model_name']}, temp={llm_conf_p3['temperature']}")
        pipeline = CQLLMPipeline(llm_config=llm_conf_p3, output_dir=output_dir)
        print("Step P3: 规范化 TBox ...")
        p3_res = pipeline.refine_schema(tbox, save_path=out_dir / "p3_tbox_refinement.json")
        tbox = pipeline.normalize_tbox_with_p3(
            tbox, p3_res, save_path=out_dir / "p3_tbox_normalized.json")
        print(
            f"  ✅ P3 规范化完成，类 {len(tbox.classes)}，关系 {len(tbox.relations)}，属性 {len(tbox.attributes)}")
        if dedup_schema_flag:
            print(f"  P3 后去重（threshold={dedup_threshold}) ...")
            tbox = pipeline.deduplicate_tbox(tbox, threshold=float(dedup_threshold))
            pipeline._dump_json(tbox.to_dict(), out_dir / "p3_tbox_normalized_dedup.json")
            print(f"  ✅ 去重后：类 {len(tbox.classes)}，关系 {len(tbox.relations)}")
        # 冲突检测
        conflicts = detect_schema_conflicts(tbox.to_dict())
        if conflicts:
            conf_path = out_dir / "p3_conflicts.json"
            conf_path.write_text(json.dumps(conflicts, ensure_ascii=False, indent=2), encoding="utf-8")
            summary = summarize_conflicts(conflicts)
            print(f"  ⚠️ 发现 {len(conflicts)} 条潜在冲突，汇总={summary}，已写入 {conf_path}")
        else:
            print("  ✅ 未发现模式冲突")
    else:
        tbox_path = Path(args.p3_file or out_dir / "p3_tbox_normalized.json")
        data = json.loads(tbox_path.read_text(encoding="utf-8"))
        tbox = TBoxSchema(
            classes=[ClassDef(**c) for c in data["classes"]],
            relations=[RelationDef(**r) for r in data["relations"]],
            attributes=[AttributeDef(**a) for a in data["attributes"]],
        )
        print(f"[SKIP] 使用已有 P3 规范化 TBox：{tbox_path}")

    # ---------- P4 ----------
    if args.p4_file:
        tbox_path = Path(args.p4_file)
        data = json.loads(tbox_path.read_text(encoding="utf-8"))
        tbox = TBoxSchema(
            classes=[ClassDef(**c) for c in data["classes"]],
            relations=[RelationDef(**r) for r in data["relations"]],
            attributes=[AttributeDef(**a) for a in data["attributes"]],
        )
        print(f"[LOAD] 使用已有 P4 增强 TBox：{tbox_path}")
        # 冲突检测
        conflicts = detect_schema_conflicts(tbox.to_dict())
        if conflicts:
            conf_path = out_dir / "p4_conflicts.json"
            conf_path.write_text(json.dumps(conflicts, ensure_ascii=False, indent=2), encoding="utf-8")
            summary = summarize_conflicts(conflicts)
            print(f"  ⚠️ 发现 {len(conflicts)} 条潜在冲突，汇总={summary}，已写入 {conf_path}")
        else:
            print("  ✅ 未发现模式冲突")

    # ---------- P5 ----------
    print("Step P5: 事件与三元组抽取 ...")
    p5_res = pipeline.extract_events(
        paragraph, tbox, save_path=None, favor_existing_classes=bool(favor_existing))
    if normalize_entities:
        p5_res = normalize_extraction_result(p5_res)
    pipeline._dump_json(p5_res, out_dir / "p5_events.json")
    print(
        f"  ✅ 抽取事件 {len(p5_res.get('events', []))} 个，三元组 {len(p5_res.get('triples', []))} 条，"
        f"已保存到 {out_dir / 'p5_events.json'}"
    )


if __name__ == "__main__":
    main()
