"""
P5 抽取结果对比实验：
用于对比不同 TBox 版本（或不同参数）下的批量抽取结果差异，便于论文/答辩展示。

比较内容：
- 文件覆盖情况：各目录的总文件数、交集/差集；
- 事件/三元组规模：总数、均值；单文件差异（事件数/三元组数差的 Top-N）。

使用示例：
python -m experiments.exp_p5_compare \
    --dir-a outputs/kg/final/p5_batch_baseline \
    --dir-b outputs/kg/final/p5_batch_augmented \
    --report outputs/kg/process/p5_compare_report.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple, List


def load_results(root: Path) -> Dict[str, Dict]:
    """
    读取批量 P5 结果目录，返回 {relative_path: json_obj}。
    过滤掉进度文件和非 json。
    """
    results = {}
    for fp in root.rglob("*.json"):
        if fp.name.startswith("_p5_progress"):
            continue
        rel = fp.relative_to(root).as_posix()
        try:
            results[rel] = json.loads(fp.read_text(encoding="utf-8"))
        except Exception as e:
            results[rel] = {"events": [], "triples": [], "error": str(e)}
    return results


def count_events_triples(data: Dict) -> Tuple[int, int]:
    """统计单文件的事件数与三元组数，容错处理空/错误。"""
    events = data.get("events", []) or []
    triples = data.get("triples", []) or []
    return len(events), len(triples)


def summarize(results: Dict[str, Dict]) -> Dict:
    total_events = 0
    total_triples = 0
    for _, obj in results.items():
        ev, tri = count_events_triples(obj)
        total_events += ev
        total_triples += tri
    n_files = len(results)
    return {
        "n_files": n_files,
        "total_events": total_events,
        "total_triples": total_triples,
        "avg_events": total_events / n_files if n_files else 0.0,
        "avg_triples": total_triples / n_files if n_files else 0.0,
    }


def diff_stats(res_a: Dict[str, Dict], res_b: Dict[str, Dict], top_n: int = 10) -> Dict:
    """
    计算两套结果的差异：
    - 仅在 A/仅在 B/交集文件列表
    - 事件数/三元组数差异最大的 Top-N
    """
    set_a = set(res_a.keys())
    set_b = set(res_b.keys())
    only_a = sorted(set_a - set_b)
    only_b = sorted(set_b - set_a)
    common = set_a & set_b

    diffs: List[Tuple[str, int, int]] = []
    for rel in common:
        ev_a, tri_a = count_events_triples(res_a[rel])
        ev_b, tri_b = count_events_triples(res_b[rel])
        diffs.append((rel, ev_b - ev_a, tri_b - tri_a))

    # 按三元组差的绝对值排序
    diffs_sorted = sorted(diffs, key=lambda x: abs(x[2]), reverse=True)[:top_n]

    return {
        "only_a": only_a,
        "only_b": only_b,
        "top_diffs": [
            {"file": rel, "delta_events": de, "delta_triples": dt}
            for rel, de, dt in diffs_sorted
        ],
    }


def main():
    parser = argparse.ArgumentParser(description="对比两套 P5 批量抽取结果（事件/三元组规模差异）")
    parser.add_argument("--dir-a", required=True, help="P5 结果目录 A（基线）")
    parser.add_argument("--dir-b", required=True, help="P5 结果目录 B（增强）")
    parser.add_argument("--report", default=None,
                        help="可选：输出对比报告 JSON 路径（推荐 outputs/kg/process/）")
    parser.add_argument("--top-n", type=int, default=10,
                        help="展示差异最大的前 N 个文件，默认 10")
    args = parser.parse_args()

    dir_a = Path(args.dir_a)
    dir_b = Path(args.dir_b)
    if not dir_a.exists() or not dir_b.exists():
        raise FileNotFoundError("结果目录不存在，请检查 --dir-a / --dir-b 参数")

    print(f"[COMPARE] 加载目录 A: {dir_a}")
    res_a = load_results(dir_a)
    res_b = load_results(dir_b)
    print(f"[COMPARE] 加载目录 B: {dir_b}")

    sum_a = summarize(res_a)
    sum_b = summarize(res_b)
    diffs = diff_stats(res_a, res_b, top_n=args.top_n)

    print("==== P5 抽取结果对比（规模统计）====")
    print(f"Dir A: {dir_a} | files={sum_a['n_files']} events={sum_a['total_events']} triples={sum_a['total_triples']} "
          f"avg_events={sum_a['avg_events']:.2f} avg_triples={sum_a['avg_triples']:.2f}")
    print(f"Dir B: {dir_b} | files={sum_b['n_files']} events={sum_b['total_events']} triples={sum_b['total_triples']} "
          f"avg_events={sum_b['avg_events']:.2f} avg_triples={sum_b['avg_triples']:.2f}")
    print(
        f"Only in A: {len(diffs['only_a'])} 个，Only in B: {len(diffs['only_b'])} 个")
    print(f"Top-{args.top_n} 三元组差异文件：")
    for item in diffs["top_diffs"]:
        print(
            f"  - {item['file']}: Δevents={item['delta_events']}, Δtriples={item['delta_triples']}")

    if args.report:
        report = {
            "dir_a": str(dir_a),
            "dir_b": str(dir_b),
            "summary_a": sum_a,
            "summary_b": sum_b,
            "diffs": diffs,
        }
        Path(args.report).write_text(json.dumps(
            report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"报告已写入：{args.report}")


if __name__ == "__main__":
    main()
