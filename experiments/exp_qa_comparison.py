import sys
import os
import json
import pandas as pd # pip install pandas

# 🔧 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# 导入我们的模块
from retrievers.vector_retriever import VectorRetriever
from retrievers.graph_retriever import hop_subgraph, format_subgraph
from kg.build_from_json import build_graph
from kg.llm import chat_with_llm

def get_baseline_answer(question, retriever):
    """
    Baseline 方法: Naive RAG (仅基于向量检索文本)
    """
    # 1. 检索 Top-3 相关文档
    hits = retriever.retrieve(question, k=3)
    if not hits:
        return "未找到相关信息", []
    
    # 2. 拼接上下文
    context_text = "\n".join([f"[{i+1}] {content}" for i, (content, score) in enumerate(hits)])
    
    # 3. LLM 生成
    prompt = f"基于以下背景信息回答问题：\n{context_text}\n\n问题：{question}"
    answer = chat_with_llm(prompt, system_prompt="你是一个助手。")
    return answer, [h[0] for h in hits] # 返回答案和检索到的原始数据

def get_graphrag_answer(question, vector_retriever, graph):
    """
    Ours 方法: GraphRAG (向量检索 + 子图扩展)
    """
    # 1. 找到入口实体 (Anchor Entity)
    hits = vector_retriever.retrieve(question, k=1)
    if not hits:
        return "未找到相关实体", []
    
    center_id = hits[0][0].get("id") # 假设数据中有 id 字段
    if not center_id:
         # 如果是纯文本块没有ID，这里需要逻辑适配，为了演示假设有ID
         return "检索到的内容无法定位图节点", []

    # 2. 获取 2-hop 子图
    sub_graph = hop_subgraph(graph, [center_id], hops=2)
    evidence_triples = format_subgraph(sub_graph)
    
    # 3. 格式化三元组证据
    context_text = "\n".join([f"- {s} {r} {o}" for s, r, o in evidence_triples])
    
    # 4. LLM 生成
    prompt = f"基于以下知识图谱结构化数据回答问题：\n{context_text}\n\n问题：{question}"
    answer = chat_with_llm(prompt, system_prompt="你是一个基于知识图谱的专家。")
    
    return answer, evidence_triples

def run_qa_experiment():
    print(">>> 开始运行：QA 方法对比实验 (Innovation 2) <<<")
    
    # 1. 准备路径
    data_path = os.path.join(project_root, "data", "processed", "sample_events.jsonl")
    
    # 2. 初始化模块
    print("正在初始化检索器和图谱...")
    vector_retriever = VectorRetriever(data_path) # 你的向量检索器
    kg_graph = build_graph(data_path)             # 你的 NetworkX 图
    
    # 3. 准备评测问题 (Questons)
    test_questions = [
        "2022年鄱阳湖干旱有什么影响？",
        "安徽2020年洪水的成因是什么？"
    ]
    
    comparison_results = []
    
    # 4. 循环评测
    for q in test_questions:
        print(f"\n正在评测问题: {q}")
        
        # --- 跑 Baseline ---
        base_ans, base_ctx = get_baseline_answer(q, vector_retriever)
        
        # --- 跑 Ours (GraphRAG) ---
        graph_ans, graph_ctx = get_graphrag_answer(q, vector_retriever, kg_graph)
        
        comparison_results.append({
            "question": q,
            "baseline_answer": base_ans,
            "graphrag_answer": graph_ans,
            "baseline_context_len": len(str(base_ctx)),
            "graph_context_triples": len(graph_ctx)
        })
        
    # 5. 保存并展示结果
    df = pd.DataFrame(comparison_results)
    output_file = os.path.join(project_root, "experiments", "qa_comparison_report.csv")
    df.to_csv(output_file, index=False, encoding="utf-8-sig")
    
    print(f"\n✅ 对比完成！报表已生成: {output_file}")
    print(df[["question", "baseline_answer", "graphrag_answer"]])

if __name__ == "__main__":
    run_qa_experiment()