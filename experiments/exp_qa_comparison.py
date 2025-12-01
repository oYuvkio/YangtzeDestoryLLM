from kg.llm_core import LLMFactory  # 引入工厂类
from kg.build_from_json import build_graph
from retrievers.graph_retriever import hop_subgraph, format_subgraph
from retrievers.vector_retriever import VectorRetriever
import sys
import os
import json
import yaml  # 需要 pip install pyyaml
import pandas as pd  # pip install pandas

# 🔧 路径黑魔法：将项目根目录加入 sys.path，防止 import 报错
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# 导入我们的模块


def load_config():
    """加载配置文件"""
    config_path = os.path.join(project_root, "configs", "cfg.yaml")
    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ 配置文件未找到: {config_path}")
        sys.exit(1)


def get_baseline_answer(question, retriever, cfg):
    """
    Baseline 方法: Naive RAG (仅基于向量检索文本)
    """
    # 1. 检索 Top-K 相关文档 (这里 K=3)
    # 注意：实际项目中 top_k 也可以从 config 读取
    retriever_cfg = cfg.get("retriever", {})
    top_k = retriever_cfg.get("top_k", 3)

    hits = retriever.retrieve(question, k=top_k)
    if not hits:
        return "未找到相关信息", []

    # 2. 拼接上下文
    context_text = "\n".join(
        [f"[{i+1}] {content}" for i, (content, score) in enumerate(hits)])

    # 3. LLM 生成
    prompt = f"基于以下背景信息回答问题：\n{context_text}\n\n问题：{question}"
    llm_cfg = cfg.get("llm", {})
    print(f"[LLM][Baseline] provider={llm_cfg.get('provider', 'unknown')}, model={llm_cfg.get('model_name', 'default')}")
    llm = LLMFactory.create(llm_cfg)

    answer = llm.chat(prompt, system_prompt="你是一个基于知识图谱的灾害问答专家。")
    return answer, [h[0] for h in hits]  # 返回答案和检索到的原始数据


def get_graphrag_answer(question, vector_retriever, graph, cfg):
    """
    Ours 方法: GraphRAG (向量检索 + 子图扩展)
    """
    # 1. 找到入口实体 (Anchor Entity)
    hits = vector_retriever.retrieve(question, k=1)
    if not hits:
        return "未找到相关实体", []

    center_id = hits[0][0].get("id")  # 假设数据中有 id 字段
    if not center_id:
        # 如果是纯文本块没有ID，这里需要逻辑适配，为了演示假设有ID
        return "检索到的内容无法定位图节点", []

    # 2. 获取 2-hop 子图
    hops = cfg.get("graph_hops", 2)
    sub_graph = hop_subgraph(graph, [center_id], hops=hops)
    evidence_triples = format_subgraph(sub_graph)
    if not evidence_triples:
        return "未找到相关的图谱路径信息", []

    # 3. 格式化三元组证据
    context_text = "\n".join(
        [f"- {s} {r} {o}" for s, r, o in evidence_triples])

    # 4. LLM 生成
    prompt = f"基于以下知识图谱结构化数据回答问题：\n{context_text}\n\n问题：{question}"
    llm_cfg = cfg.get("llm", {})
    print(f"[LLM][GraphRAG] provider={llm_cfg.get('provider', 'unknown')}, model={llm_cfg.get('model_name', 'default')}")
    llm = LLMFactory.create(llm_cfg)

    answer = llm.chat(prompt, system_prompt="你是一个基于知识图谱的灾害问答专家。")
    return answer, evidence_triples


def run_qa_experiment():
    """跑通基线与 GraphRAG 的问答对比实验。"""
    print(">>> 开始运行：QA 方法对比实验 (Innovation 2) <<<")

    # 0. 加载配置
    cfg = load_config()
    print(f"[LLM][QA] provider={cfg['llm'].get('provider', 'unknown')}, model={cfg['llm'].get('model_name', 'default')}")

    # 1. 准备路径
    data_path = os.path.join(project_root, "data",
                             "processed", "sample_events.jsonl")

    if not os.path.exists(data_path):
        print(f"❌ 数据文件未找到: {data_path}")
        print("请先运行 experiments/exp_kg_construction.py 生成数据，或检查路径。")
        return

    # 2. 初始化模块
    print("正在初始化检索器和图谱...")
    vector_retriever = VectorRetriever(data_path)  # 你的向量检索器
    kg_graph = build_graph(data_path)             # 你的 NetworkX 图

    # 3. 准备评测问题 (Questions)
    # 建议：这里也可以从 data/processed/qa_eval.jsonl 读取真实问题
    test_questions = [
        "2022年鄱阳湖干旱有什么影响？",
        "安徽2020年洪水的成因是什么？"
    ]

    comparison_results = []

    # 4. 循环评测
    for q in test_questions:
        print(f"\n--------------------------------------------------")
        print(f"正在评测问题: {q}")

        # --- 跑 Baseline ---
        print("Running Baseline (Naive RAG)...")
        base_ans, base_ctx = get_baseline_answer(
            q, vector_retriever, cfg)

        # --- 跑 Ours (GraphRAG) ---
        print("Running GraphRAG...")
        graph_ans, graph_ctx = get_graphrag_answer(
            q, vector_retriever, kg_graph, cfg)

        comparison_results.append({
            "question": q,
            "baseline_answer": base_ans,
            "graphrag_answer": graph_ans,
            "baseline_context_len": len(str(base_ctx)),
            "graph_context_triples": len(graph_ctx)
        })

    # 5. 保存并展示结果
    df = pd.DataFrame(comparison_results)
    output_file = os.path.join(
        project_root, "experiments", "qa_comparison_report.csv")
    df.to_csv(output_file, index=False, encoding="utf-8-sig")

    print(f"\n✅ 对比完成！报表已生成: {output_file}")
    # 打印预览
    print(df[["question", "baseline_answer", "graphrag_answer"]])


if __name__ == "__main__":
    run_qa_experiment()
