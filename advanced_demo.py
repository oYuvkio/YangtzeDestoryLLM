"""
长江灾害 RAG 系统的高级演示脚本。

本脚本展示了改进后的抽取管道（基于 LLM 的思维链与验证）、基线抽取器（传统启发式方法），
以及增强的图检索模块（结合了语义、词汇和多跳策略）。
运行此文件可以看到原始文本是如何转化为知识图谱的，以及不同检索策略的表现。

用法示例::

    python advanced_demo.py

注意：此脚本需要设置 LLM 提供商的环境变量，例如 ``ZHIPU_API_KEY`` 或 ``GEMINI_API_KEY``。
"""

from retrievers.graph_retriever import GraphRetriever
from kg.extractor import LLMExtractor, DeepLearningExtractor
from sentence_transformers import SentenceTransformer
import networkx as nx
from pprint import pprint
import json
import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def build_graph_from_result(result: dict) -> nx.DiGraph:
    """从抽取结果构建有向图。"""
    G = nx.DiGraph()
    for entity in result["entities"]:
        G.add_node(entity["name"], type=entity.get("type", ""))
    for rel in result["relations"]:
        head = rel["head"]
        tail = rel["tail"]
        relation = rel["relation"]
        G.add_edge(head, tail, relation=relation)
    return G


def main() -> None:
    # 配置 LLM 提供商 —— 如果未指定，默认为 zhipu
    llm_provider = os.getenv("LLM_PROVIDER", "zhipu")
    llm_config = {
        "provider": llm_provider,
        # 如果模型名称不同，请在此处设置
        "model_name": "glm-4.5-flash" if llm_provider == "zhipu" else "gemini-2.5-flash",
        "temperature": 0.1,
    }

    # 示例原始文本。在实际应用中，您应该将其替换为实际语料库或数据集样本。
    raw_text = """
1998年长江全流域特大洪水是20世纪以来仅次于1954年的大洪水。
此次洪水发生于1998年6月中旬至9月上旬。
灾害主要由气候异常、降雨集中以及生态破坏导致。
洪水淹没了江西、湖南、湖北等省份的广大地区。
针对此次灾害，政府采取了退田还湖、加固堤防等应对措施。
"""
    if nx is None:
        print("❌ networkx 未安装，无法运行演示脚本。")
        return
    if SentenceTransformer is None:
        print("❌ sentence-transformers 未安装，无法运行演示脚本。")
        return

    print(">>> 使用 LLMExtractor (多轮验证) 进行知识抽取")
    # 实例化 LLM 抽取器（创新点一：基于 Prompt 工程）
    llm_extractor = LLMExtractor(llm_config)
    llm_result = llm_extractor.extract(raw_text)
    # 注意：extract 返回的是 ExtractionResult 对象，需要调用 as_json()
    pprint(json.loads(llm_result.as_json()), width=120, indent=2)

    print("\n>>> 使用 DeepLearningExtractor (传统方法) 进行知识抽取")
    # 实例化深度学习/规则抽取器（基线对照组）
    dl_extractor = DeepLearningExtractor()
    dl_result = dl_extractor.extract(raw_text)
    pprint(json.loads(dl_result.as_json()), width=120, indent=2)

    print("\n>>> 构建知识图谱 (取 LLM 结果) 并展示节点与边")
    # 使用 NetworkX 在内存中构建图谱，模拟 Neo4j 的结构
    G = build_graph_from_result(json.loads(llm_result.as_json()))
    print(f"图中共有 {G.number_of_nodes()} 个节点，{G.number_of_edges()} 条边。")
    print("节点类型:")
    for n, attrs in G.nodes(data=True):
        print(f"  - {n} ({attrs.get('type', '')})")
    print("关系:")
    for u, v, data in G.edges(data=True):
        print(f"  - {u} --[{data['relation']}]--> {v}")

    # 为语义检索准备嵌入模型
    print("\n>>> 加载句子向量模型以进行语义检索...")
    # 这里使用本地或 HuggingFace 上的预训练模型
    embedding_model = SentenceTransformer(
        'paraphrase-multilingual-MiniLM-L12-v2')
    # 初始化图检索器（创新点二的核心组件）
    retriever = GraphRetriever(G, embedding_model)

    user_query = "1998年长江洪水的起因是什么？"
    print(f"\n用户查询: {user_query}")

    # 1. 语义检索：找到最相关的“种子节点”
    seed_nodes = retriever.semantic_retrieval(
        user_query, top_k=3, threshold=0.3)
    print(f"语义检索得到的相关节点: {seed_nodes}")

    # 2. 多跳检索：从种子节点向外扩展，获取上下文子图
    subgraph_triples = retriever.multi_hop_subgraph(seed_nodes, max_hops=2)
    print("\n多跳检索得到的知识三元组:")
    for head, rel, tail in subgraph_triples:
        print(f"  {head} --[{rel}]--> {tail}")

    # 3. BM25 检索：作为传统关键词匹配的对照
    bm25_results = retriever.bm25_retrieval(user_query, top_k=5)
    print("\nBM25 检索得到的三元组:")
    for head, rel, tail in bm25_results:
        print(f"  {head} --[{rel}]--> {tail}")


if __name__ == "__main__":
    main()
