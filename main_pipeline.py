"""演示从知识抽取到 GraphRAG 问答的端到端流程。"""
import os
import yaml
from kg.extractor import KnowledgeExtractor
from kg.build_from_json import build_graph
from retrievers.vector_retriever import VectorRetriever
from retrievers.graph_retriever import hop_subgraph, format_subgraph
from kg.llm import draft_answer


# 模拟一段新的原始文本（论文中的非结构化数据来源）
RAW_DOC = """
2020年7月，安徽省遭遇了历史罕见的洪涝灾害。
受持续强降雨和长江上游来水影响，长江安徽段水位全线超警。
洪水导致合肥、芜湖、安庆等多地发生严重内涝，大量农田被淹。
为应对灾情，安徽省启动了防汛I级应急响应，紧急转移安置群众，并对堤防进行了加固。
"""

def main():
    """串联知识抽取、图谱构建与问答的示例入口。"""
    print("="*20 + " 阶段一：基于LLM的知识抽取 (创新点1) " + "="*20)
    extractor = KnowledgeExtractor()
    kg_data = extractor.extract(RAW_DOC)
    print(f"抽取结果: 包含 {len(kg_data.get('entities', []))} 个实体, {len(kg_data.get('relations', []))} 条关系")
    
    # 将抽取结果保存为系统可读的格式 (模拟写入 sample_events.jsonl 的过程)
    # 这里为了演示，我们直接在内存中处理或假设已存入文件
    # 实际项目中，你需要把 kg_data 转换成 sample_events.jsonl 的格式并追加写入
    
    print("\n" + "="*20 + " 阶段二：知识图谱构建 " + "="*20)
    # 这里我们还是加载预设的数据文件，演示图谱检索流程
    DATA_PATH = "data/processed/sample_events.jsonl"
    kg_graph = build_graph(DATA_PATH)
    print(f"图谱构建完成: {kg_graph.number_of_nodes()} 节点, {kg_graph.number_of_edges()} 边")
    
    print("\n" + "="*20 + " 阶段三：GraphRAG 问答 (创新点2) " + "="*20)
    # 初始化向量检索器
    retriever = VectorRetriever(DATA_PATH)
    
    question = "2022年鄱阳湖干旱造成了什么后果？"
    print(f"用户提问: {question}")
    
    # 1. 向量检索找到入口实体 (Semantic Retrieval)
    hits = retriever.retrieve(question, k=1)
    if not hits:
        print("未找到相关知识。")
        return

    top_event, score = hits[0]
    center_id = top_event["id"]
    print(f"检索定位到核心实体: {center_id} (相似度: {score:.4f})")
    
    # 2. 图结构多跳检索 (Graph Traversal)
    # 从核心实体出发，向外跳2层，获取子图
    sub_graph = hop_subgraph(kg_graph, [center_id], hops=2)
    evidence_triples = format_subgraph(sub_graph)
    print(f"提取子图证据: 找到 {len(evidence_triples)} 条关联三元组")
    for t in evidence_triples[:3]: # 打印前3条
        print(f"  - {t}")
    
    # 3. LLM 生成答案 (Generation)
    final_answer = draft_answer(question, evidence_triples)
    print(f"\nAI 回答:\n{final_answer}")

if __name__ == "__main__":
    main()