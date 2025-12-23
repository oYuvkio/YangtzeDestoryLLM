#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OntoQA 指标计算工具。

计算 TBox 结构指标（RR/IR/AR）并导出为 CSV/Markdown/JSON 表格。
支持：
- 多版本 TBox 批量对比（可传文件列表/Glob/目录）
- 指标增量对比（相对 baseline 的 delta + 新增/移除元素）
- 额外结构指标（层级深度、分支度、根/叶类、功能性关系比例等）

用法示例:
    python tools/ontoqa_metrics.py \
      --tboxes "outputs/cq_pipeline/final/p2_tbox_init.json,outputs/cq_pipeline/final/p3_tbox_dedup.json,outputs/cq_pipeline/final/p4_tbox_augmented_s2_allow0.json" \
      --out-csv "outputs/ontoqa/metrics.csv" \
      --out-md "outputs/ontoqa/metrics.md" \
      --log-file "logs/ontoqa/run.log"
"""

import argparse
import glob
import json
import logging
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


# 设置日志
logger = logging.getLogger(__name__)

try:
    # 复用项目里更鲁棒的 SC 统计（含显式层级/启发式估计）
    from tools.tbox_metrics import count_subclass_edges as count_subclass_edges_heuristic
except Exception:  # pragma: no cover
    count_subclass_edges_heuristic = None


def setup_logger(log_file: str = None) -> logging.Logger:
    """设置日志配置"""
    log_format = "%(asctime)s | %(levelname)s | %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"
    
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt=date_format,
        handlers=handlers,
        force=True
    )
    return logging.getLogger(__name__)


@dataclass
class OntoQAMetrics:
    """OntoQA + 扩展结构指标数据类"""
    model_name: str
    C: int  # 类数量
    SC_strict: int  # 严格继承数量（有效 parent 指针）
    SC_used: int  # 实际用于 RR/IR 的继承数量
    SC_heuristic: int  # 启发式继承数量（可能含估计）
    P: int  # 非继承关系数量（domain-range 关系）
    A: int  # 属性数量
    RR: Optional[float]  # Relationship Richness = P / (P + SC)
    IR: Optional[float]  # Inheritance Richness = SC / C
    AR: Optional[float]  # Attribute Richness = A / C

    # ===== 扩展结构指标 =====
    root_classes: int = 0
    leaf_classes: int = 0
    max_depth: Optional[int] = None
    avg_depth: Optional[float] = None
    max_children: int = 0
    avg_branching: Optional[float] = None
    functional_relations: int = 0
    rel_per_class: Optional[float] = None
    invalid_parent_refs: int = 0
    cycle_classes: int = 0

    # ===== 相对 baseline 的对比指标 =====
    delta_C: Optional[int] = None
    delta_SC_used: Optional[int] = None
    delta_P: Optional[int] = None
    delta_A: Optional[int] = None
    delta_RR: Optional[float] = None
    delta_IR: Optional[float] = None
    delta_AR: Optional[float] = None
    new_classes: Optional[int] = None
    removed_classes: Optional[int] = None
    new_relations: Optional[int] = None
    removed_relations: Optional[int] = None
    new_attributes: Optional[int] = None
    removed_attributes: Optional[int] = None
    notes: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "model_name": self.model_name,
            "C": self.C,
            "SC_strict": self.SC_strict,
            "SC_used": self.SC_used,
            "SC_heuristic": self.SC_heuristic,
            "P": self.P,
            "A": self.A,
            "RR": round(self.RR, 4) if self.RR is not None else None,
            "IR": round(self.IR, 4) if self.IR is not None else None,
            "AR": round(self.AR, 4) if self.AR is not None else None,
            "root_classes": self.root_classes,
            "leaf_classes": self.leaf_classes,
            "max_depth": self.max_depth,
            "avg_depth": round(self.avg_depth, 4) if self.avg_depth is not None else None,
            "max_children": self.max_children,
            "avg_branching": round(self.avg_branching, 4) if self.avg_branching is not None else None,
            "functional_relations": self.functional_relations,
            "rel_per_class": round(self.rel_per_class, 4) if self.rel_per_class is not None else None,
            "invalid_parent_refs": self.invalid_parent_refs,
            "cycle_classes": self.cycle_classes,
            "delta_C": self.delta_C,
            "delta_SC_used": self.delta_SC_used,
            "delta_P": self.delta_P,
            "delta_A": self.delta_A,
            "delta_RR": round(self.delta_RR, 4) if self.delta_RR is not None else None,
            "delta_IR": round(self.delta_IR, 4) if self.delta_IR is not None else None,
            "delta_AR": round(self.delta_AR, 4) if self.delta_AR is not None else None,
            "new_classes": self.new_classes,
            "removed_classes": self.removed_classes,
            "new_relations": self.new_relations,
            "removed_relations": self.removed_relations,
            "new_attributes": self.new_attributes,
            "removed_attributes": self.removed_attributes,
            "notes": self.notes,
        }


def load_tbox(tbox_path: Path) -> Dict[str, Any]:
    """加载 TBox JSON 文件"""
    if not tbox_path.exists():
        raise FileNotFoundError(f"TBox 文件不存在: {tbox_path}")
    
    try:
        return json.loads(tbox_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"TBox 文件格式错误 {tbox_path}: {exc}")


def _normalize_parent_value(raw_parent: Any) -> Optional[str]:
    """规整 parent 值，过滤 null/None/空串 等无效占位。"""
    if raw_parent is None:
        return None
    if isinstance(raw_parent, str):
        parent_text = raw_parent.strip()
    else:
        parent_text = str(raw_parent).strip()
    if not parent_text:
        return None
    if parent_text.lower() in {"null", "none", "nan"}:
        return None
    return parent_text


def _build_hierarchy(classes: List[Dict[str, Any]]) -> Tuple[Dict[str, str], Dict[str, Set[str]], int]:
    """根据 classes 的 parent/parent_class 构建严格层级。"""
    class_names: Set[str] = {c.get("name") for c in classes if c.get("name")}
    strict_parent_map: Dict[str, str] = {}
    children_map: Dict[str, Set[str]] = defaultdict(set)
    invalid_parent_refs = 0
    for class_item in classes:
        class_name = class_item.get("name")
        if not class_name:
            continue
        raw_parent = class_item.get("parent") or class_item.get("parent_class")
        parent_name = _normalize_parent_value(raw_parent)
        if not parent_name:
            continue
        if parent_name not in class_names or parent_name == class_name:
            invalid_parent_refs += 1
            continue
        strict_parent_map[class_name] = parent_name
        children_map[parent_name].add(class_name)
    return strict_parent_map, children_map, invalid_parent_refs


def _compute_depth_stats(
    class_names: Set[str],
    strict_parent_map: Dict[str, str],
) -> Tuple[Optional[int], Optional[float], int]:
    """计算严格层级下的 max/avg depth，并检测循环。"""
    depth_cache: Dict[str, Optional[int]] = {}
    visiting: Set[str] = set()
    cycle_classes = 0

    def depth_of(class_name: str) -> Optional[int]:
        nonlocal cycle_classes
        if class_name in depth_cache:
            return depth_cache[class_name]
        if class_name in visiting:
            cycle_classes += 1
            depth_cache[class_name] = None
            return None
        visiting.add(class_name)
        parent_name = strict_parent_map.get(class_name)
        if not parent_name:
            depth_value = 1
        else:
            parent_depth = depth_of(parent_name)
            depth_value = parent_depth + 1 if parent_depth is not None else None
        visiting.remove(class_name)
        depth_cache[class_name] = depth_value
        return depth_value

    for name in class_names:
        depth_of(name)

    depth_values = [v for v in depth_cache.values() if v is not None]
    if not depth_values:
        return None, None, cycle_classes
    max_depth = max(depth_values)
    avg_depth = sum(depth_values) / len(depth_values)
    return max_depth, avg_depth, cycle_classes


def calculate_metrics(
    tbox_path: Path,
    model_name: Optional[str] = None,
    sc_mode: str = "strict",
) -> OntoQAMetrics:
    """
    计算单个 TBox 的 OntoQA 指标。
    
    Args:
        tbox_path: TBox 文件路径
        model_name: 模型名称（可选，默认使用文件名）
        sc_mode: strict|heuristic，决定 RR/IR 使用的 SC
        
    Returns:
        OntoQAMetrics 对象
    """
    tbox = load_tbox(tbox_path)
    
    if model_name is None:
        model_name = tbox_path.stem
    
    # 统计类数量
    classes = tbox.get("classes", []) or []
    C = len(classes)
    strict_parent_map, children_map, invalid_parent_refs = _build_hierarchy(classes)
    SC_strict = len(strict_parent_map)
    if count_subclass_edges_heuristic:
        try:
            SC_heuristic = int(count_subclass_edges_heuristic(tbox))
        except Exception:
            SC_heuristic = SC_strict
    else:
        SC_heuristic = SC_strict
    if sc_mode == "heuristic":
        SC_used = SC_heuristic
    else:
        SC_used = SC_strict
    if sc_mode == "heuristic" and not count_subclass_edges_heuristic:
        logger.warning("未找到启发式 SC 统计实现，已回退为 strict。")
    
    class_names: Set[str] = {c.get("name") for c in classes if c.get("name")}
    root_classes = sum(1 for name in class_names if name not in strict_parent_map)
    leaf_classes = sum(1 for name in class_names if len(children_map.get(name, set())) == 0)
    children_counts = [len(children_map.get(name, set())) for name in class_names]
    max_children = max(children_counts) if children_counts else 0
    avg_branching = (sum(children_counts) / len(children_counts)) if children_counts else None
    max_depth, avg_depth, cycle_classes = _compute_depth_stats(class_names, strict_parent_map)
    
    # 统计非继承关系数量（domain-range 类型的关系）
    relations = tbox.get("relations", []) or []
    P = len(relations)
    functional_relations = sum(1 for r in relations if bool(r.get("functional")))
    
    # 统计属性数量
    attributes = tbox.get("attributes", []) or []
    A = len(attributes)
    rel_per_class = P / C if C > 0 else None
    
    # 计算指标
    # RR = P / (P + SC)，分母为 0 时为 None
    RR = P / (P + SC_used) if (P + SC_used) > 0 else None
    
    # IR = SC / C，分母为 0 时为 None
    IR = SC_used / C if C > 0 else None
    
    # AR = A / C，分母为 0 时为 None
    AR = A / C if C > 0 else None
    
    rr_str = f"{RR:.4f}" if RR is not None else "N/A"
    ir_str = f"{IR:.4f}" if IR is not None else "N/A"
    ar_str = f"{AR:.4f}" if AR is not None else "N/A"
    logger.info(
        f"[{model_name}] C={C}, SC_strict={SC_strict}, SC_used={SC_used}, "
        f"P={P}, A={A}, RR={rr_str}, IR={ir_str}, AR={ar_str}"
    )
    if invalid_parent_refs:
        logger.warning(f"[{model_name}] 发现无效 parent 引用: {invalid_parent_refs} 个")
    if cycle_classes:
        logger.warning(f"[{model_name}] 发现层级循环相关类: {cycle_classes} 个")
    
    return OntoQAMetrics(
        model_name=model_name,
        C=C,
        SC_strict=SC_strict,
        SC_used=SC_used,
        SC_heuristic=SC_heuristic,
        P=P,
        A=A,
        RR=RR,
        IR=IR,
        AR=AR,
        root_classes=root_classes,
        leaf_classes=leaf_classes,
        max_depth=max_depth,
        avg_depth=avg_depth,
        max_children=max_children,
        avg_branching=avg_branching,
        functional_relations=functional_relations,
        rel_per_class=rel_per_class,
        invalid_parent_refs=invalid_parent_refs,
        cycle_classes=cycle_classes,
    )


def _format_csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _get_csv_columns(core_only: bool = False) -> List[str]:
    core_columns = ["model_name", "C", "SC_used", "P", "A", "RR", "IR", "AR"]
    if core_only:
        return core_columns
    extended_columns = [
        "SC_strict",
        "SC_heuristic",
        "root_classes",
        "leaf_classes",
        "max_depth",
        "avg_depth",
        "max_children",
        "avg_branching",
        "functional_relations",
        "rel_per_class",
        "invalid_parent_refs",
        "cycle_classes",
        "delta_C",
        "delta_SC_used",
        "delta_P",
        "delta_A",
        "delta_RR",
        "delta_IR",
        "delta_AR",
        "new_classes",
        "removed_classes",
        "new_relations",
        "removed_relations",
        "new_attributes",
        "removed_attributes",
        "notes",
    ]
    return core_columns + extended_columns


def save_to_csv(
    metrics_list: List[OntoQAMetrics],
    output_path: Path,
    core_only: bool = False,
) -> None:
    """保存指标到 CSV 文件（可选 core-only）。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    columns = _get_csv_columns(core_only=core_only)
    with output_path.open("w", encoding="utf-8") as f:
        f.write(",".join(columns) + "\n")
        for metrics in metrics_list:
            metrics_dict = metrics.to_dict()
            row = [_format_csv_value(metrics_dict.get(col)) for col in columns]
            f.write(",".join(row) + "\n")
    logger.info(f"CSV 文件已保存: {output_path}")


def save_to_markdown(
    metrics_list: List[OntoQAMetrics],
    output_path: Path,
    full: bool = False,
) -> None:
    """保存指标到 Markdown 表格。full=True 会额外输出扩展/对比表。"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8") as f:
        f.write("### OntoQA 核心指标\n")
        f.write("| Model | C | SC_used | P | A | RR | IR | AR |\n")
        f.write("|-------|---|---------|---|---|-----|-----|-----|\n")
        for metrics in metrics_list:
            metrics_dict = metrics.to_dict()
            rr_str = f"{metrics_dict['RR']:.4f}" if metrics_dict["RR"] is not None else "N/A"
            ir_str = f"{metrics_dict['IR']:.4f}" if metrics_dict["IR"] is not None else "N/A"
            ar_str = f"{metrics_dict['AR']:.4f}" if metrics_dict["AR"] is not None else "N/A"
            f.write(
                f"| {metrics_dict['model_name']} | {metrics_dict['C']} | "
                f"{metrics_dict['SC_used']} | {metrics_dict['P']} | {metrics_dict['A']} | "
                f"{rr_str} | {ir_str} | {ar_str} |\n"
            )

        if not full:
            logger.info(f"Markdown 文件已保存: {output_path}")
            return

        f.write("\n### 层级与关系扩展指标\n")
        f.write("| Model | roots | leaves | max_depth | avg_depth | max_children | avg_branching | functional_rel | invalid_parent | cycles |\n")
        f.write("|-------|-------|--------|-----------|-----------|--------------|---------------|----------------|---------------|--------|\n")
        for metrics in metrics_list:
            metrics_dict = metrics.to_dict()
            avg_depth_str = f"{metrics_dict['avg_depth']:.4f}" if metrics_dict["avg_depth"] is not None else "N/A"
            avg_branching_str = f"{metrics_dict['avg_branching']:.4f}" if metrics_dict["avg_branching"] is not None else "N/A"
            f.write(
                f"| {metrics_dict['model_name']} | {metrics_dict['root_classes']} | "
                f"{metrics_dict['leaf_classes']} | {metrics_dict['max_depth'] or 'N/A'} | "
                f"{avg_depth_str} | {metrics_dict['max_children']} | {avg_branching_str} | "
                f"{metrics_dict['functional_relations']} | {metrics_dict['invalid_parent_refs']} | "
                f"{metrics_dict['cycle_classes']} |\n"
            )

        f.write("\n### 相对 Baseline 的增量与新增元素\n")
        f.write("| Model | ΔC | ΔSC | ΔP | ΔA | ΔRR | ΔIR | ΔAR | +Classes | -Classes | +Rels | -Rels | +Attrs | -Attrs |\n")
        f.write("|-------|----|-----|----|----|-----|-----|-----|---------|---------|-------|-------|--------|--------|\n")
        for metrics in metrics_list:
            metrics_dict = metrics.to_dict()
            delta_rr_str = f"{metrics_dict['delta_RR']:.4f}" if metrics_dict["delta_RR"] is not None else "N/A"
            delta_ir_str = f"{metrics_dict['delta_IR']:.4f}" if metrics_dict["delta_IR"] is not None else "N/A"
            delta_ar_str = f"{metrics_dict['delta_AR']:.4f}" if metrics_dict["delta_AR"] is not None else "N/A"
            f.write(
                f"| {metrics_dict['model_name']} | {metrics_dict['delta_C'] if metrics_dict['delta_C'] is not None else 0} | "
                f"{metrics_dict['delta_SC_used'] if metrics_dict['delta_SC_used'] is not None else 0} | "
                f"{metrics_dict['delta_P'] if metrics_dict['delta_P'] is not None else 0} | "
                f"{metrics_dict['delta_A'] if metrics_dict['delta_A'] is not None else 0} | "
                f"{delta_rr_str} | {delta_ir_str} | {delta_ar_str} | "
                f"{metrics_dict['new_classes'] or 0} | {metrics_dict['removed_classes'] or 0} | "
                f"{metrics_dict['new_relations'] or 0} | {metrics_dict['removed_relations'] or 0} | "
                f"{metrics_dict['new_attributes'] or 0} | {metrics_dict['removed_attributes'] or 0} |\n"
            )

    logger.info(f"Markdown 文件已保存: {output_path}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="OntoQA 指标计算工具",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--tboxes",
        type=str,
        required=False,
        default="",
        help="TBox 文件路径列表（逗号分隔），如：p2.json,p3.json,p4.json"
    )
    parser.add_argument(
        "--tbox-glob",
        type=str,
        default="",
        help="Glob 模式（逗号分隔），如：outputs/.../p4_tbox_augmented_*_allow*.json"
    )
    parser.add_argument(
        "--tbox-dir",
        type=str,
        default="",
        help="TBox 目录（逗号分隔），会递归匹配 pattern（默认 *.json）"
    )
    parser.add_argument(
        "--pattern",
        type=str,
        default="*.json",
        help="配合 --tbox-dir 的文件匹配模式（默认 *.json）"
    )
    parser.add_argument(
        "--names",
        type=str,
        default="",
        help="与 tboxes 对应的别名（逗号分隔），用于表格展示"
    )
    parser.add_argument(
        "--baseline",
        type=str,
        default="",
        help="baseline TBox 路径（默认使用第一个 TBox）"
    )
    parser.add_argument(
        "--sc-mode",
        type=str,
        default="strict",
        choices=["strict", "heuristic"],
        help="SC 计算模式：strict(只计有效 parent) / heuristic(缺失层级时启发式估计)"
    )
    parser.add_argument(
        "--core-only",
        action="store_true",
        help="CSV 仅导出 OntoQA 核心列（保持旧格式）"
    )
    parser.add_argument(
        "--md-full",
        action="store_true",
        help="Markdown 额外输出扩展/增量对比表"
    )
    
    parser.add_argument(
        "--out-csv",
        type=str,
        default="outputs/ontoqa/metrics.csv",
        help="CSV 输出文件路径（默认：outputs/ontoqa/metrics.csv）"
    )
    
    parser.add_argument(
        "--out-md",
        type=str,
        default="outputs/ontoqa/metrics.md",
        help="Markdown 输出文件路径（默认：outputs/ontoqa/metrics.md）"
    )
    parser.add_argument(
        "--out-json",
        type=str,
        default="",
        help="可选 JSON 输出路径（便于画图/进一步分析）"
    )
    
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="日志文件路径（可选）"
    )
    
    return parser.parse_args()


def _collect_tbox_paths(args: argparse.Namespace) -> List[Path]:
    """从 tboxes/glob/dir 收集 TBox 路径，保持输入顺序并去重。"""
    seen: Set[Path] = set()
    collected: List[Path] = []

    def add_paths(paths: List[Path]) -> None:
        for path_item in paths:
            resolved = path_item
            if resolved not in seen:
                seen.add(resolved)
                collected.append(resolved)

    if args.tboxes:
        add_paths([Path(p.strip()) for p in args.tboxes.split(",") if p.strip()])

    if args.tbox_glob:
        patterns = [p.strip() for p in args.tbox_glob.split(",") if p.strip()]
        for pattern in patterns:
            matched = sorted(glob.glob(pattern, recursive=True))
            add_paths([Path(m) for m in matched])

    if args.tbox_dir:
        dirs = [d.strip() for d in args.tbox_dir.split(",") if d.strip()]
        for directory in dirs:
            dir_path = Path(directory)
            if not dir_path.exists():
                logger.warning(f"目录不存在，跳过: {dir_path}")
                continue
            add_paths(sorted(dir_path.rglob(args.pattern)))

    if not collected:
        raise ValueError("未收集到任何 TBox，请提供 --tboxes 或 --tbox-glob 或 --tbox-dir。")
    return collected


def _resolve_model_names(tbox_paths: List[Path], args: argparse.Namespace) -> List[str]:
    """根据 --names 或文件名生成展示名。"""
    if not args.names:
        return [p.stem for p in tbox_paths]
    raw_names = [n.strip() for n in args.names.split(",") if n.strip()]
    resolved_names: List[str] = []
    for idx, path_item in enumerate(tbox_paths):
        if idx < len(raw_names):
            resolved_names.append(raw_names[idx])
        else:
            resolved_names.append(path_item.stem)
    return resolved_names


def _extract_signatures(tbox: Dict[str, Any]) -> Tuple[Set[str], Set[Tuple[str, str, str]], Set[Tuple[str, str]]]:
    """抽取类/关系/属性签名用于对比。"""
    classes = tbox.get("classes", []) or []
    class_names: Set[str] = {c.get("name").strip() for c in classes if c.get("name")}

    relations = tbox.get("relations", []) or []
    relation_sigs: Set[Tuple[str, str, str]] = set()
    for rel in relations:
        name = (rel.get("name") or "").strip()
        domain = (rel.get("domain") or "").strip()
        range_name = (rel.get("range") or "").strip()
        if name and domain and range_name:
            relation_sigs.add((name, domain, range_name))

    attributes = tbox.get("attributes", []) or []
    attribute_sigs: Set[Tuple[str, str]] = set()
    for attr in attributes:
        owner = (attr.get("owner") or "").strip()
        name = (attr.get("name") or "").strip()
        if owner and name:
            attribute_sigs.add((owner, name))

    return class_names, relation_sigs, attribute_sigs


def main():
    """主函数"""
    args = parse_args()
    
    # 设置日志
    global logger
    logger = setup_logger(log_file=args.log_file)
    
    logger.info("=" * 60)
    logger.info("OntoQA 指标计算工具")
    logger.info("=" * 60)
    
    # 解析/收集 TBox 文件列表
    try:
        tbox_paths = _collect_tbox_paths(args)
    except Exception as exc:
        logger.error(str(exc))
        return
    logger.info(f"待处理 TBox 文件: {len(tbox_paths)} 个")

    model_names = _resolve_model_names(tbox_paths, args)

    # 计算每个 TBox 的指标（先不含 baseline 差异）
    metrics_pairs: List[Tuple[Path, OntoQAMetrics]] = []
    for tbox_path, model_name in zip(tbox_paths, model_names):
        try:
            metrics = calculate_metrics(tbox_path, model_name=model_name, sc_mode=args.sc_mode)
            metrics_pairs.append((tbox_path, metrics))
        except Exception as exc:
            logger.error(f"处理 {tbox_path} 时出错: {exc}")
            continue
    
    if not metrics_pairs:
        logger.error("没有成功计算任何指标，退出。")
        return
    metrics_list = [m for _, m in metrics_pairs]

    # baseline 选择与差异计算
    baseline_path = Path(args.baseline) if args.baseline else tbox_paths[0]
    try:
        baseline_tbox = load_tbox(baseline_path)
        baseline_class_names, baseline_relation_sigs, baseline_attribute_sigs = _extract_signatures(baseline_tbox)
    except Exception as exc:
        logger.warning(f"baseline 加载失败，将跳过增量对比: {exc}")
        baseline_tbox = None
        baseline_class_names = set()
        baseline_relation_sigs = set()
        baseline_attribute_sigs = set()

    baseline_metrics = None
    for path_item, metrics in metrics_pairs:
        if path_item == baseline_path:
            baseline_metrics = metrics
            break
    if baseline_metrics is None:
        baseline_metrics = metrics_list[0]
        logger.warning(f"baseline 未在成功列表中找到，回退为第一个成功 TBox: {baseline_metrics.model_name}")

    for tbox_path, metrics in metrics_pairs:
        metrics.delta_C = metrics.C - baseline_metrics.C
        metrics.delta_SC_used = metrics.SC_used - baseline_metrics.SC_used
        metrics.delta_P = metrics.P - baseline_metrics.P
        metrics.delta_A = metrics.A - baseline_metrics.A
        if metrics.RR is not None and baseline_metrics.RR is not None:
            metrics.delta_RR = metrics.RR - baseline_metrics.RR
        if metrics.IR is not None and baseline_metrics.IR is not None:
            metrics.delta_IR = metrics.IR - baseline_metrics.IR
        if metrics.AR is not None and baseline_metrics.AR is not None:
            metrics.delta_AR = metrics.AR - baseline_metrics.AR

        if baseline_tbox is not None:
            try:
                current_tbox = load_tbox(tbox_path)
                current_class_names, current_relation_sigs, current_attribute_sigs = _extract_signatures(current_tbox)
                metrics.new_classes = len(current_class_names - baseline_class_names)
                metrics.removed_classes = len(baseline_class_names - current_class_names)
                metrics.new_relations = len(current_relation_sigs - baseline_relation_sigs)
                metrics.removed_relations = len(baseline_relation_sigs - current_relation_sigs)
                metrics.new_attributes = len(current_attribute_sigs - baseline_attribute_sigs)
                metrics.removed_attributes = len(baseline_attribute_sigs - current_attribute_sigs)
            except Exception as exc:
                metrics.notes = f"diff 失败: {exc}"
    
    # 保存到 CSV
    csv_path = Path(args.out_csv)
    save_to_csv(metrics_list, csv_path, core_only=args.core_only)
    
    # 保存到 Markdown
    md_path = Path(args.out_md)
    save_to_markdown(metrics_list, md_path, full=args.md_full)

    # 可选 JSON 导出
    if args.out_json:
        json_path = Path(args.out_json)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps([m.to_dict() for m in metrics_list], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"JSON 文件已保存: {json_path}")
    
    logger.info("=" * 60)
    logger.info("指标计算完成")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
