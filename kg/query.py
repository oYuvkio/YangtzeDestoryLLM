from retrievers.text_retriever import BM25Retriever
from retrievers.graph_retriever import hop_subgraph, format_subgraph
from kg.build_from_json import build_graph
from kg.llm_core import draft_answer_with_graph


# GraphRAG引擎（负责问答推理）
class GraphRAG:
    """结合文本检索与图谱扩展的问答工作流。"""

    def __init__(self, data_path: str, hops: int, top_k: int, llm_config: dict):
        self.ret = BM25Retriever(data_path)  # 注意：这里可以进一步优化为根据配置选择检索器
        self.g = build_graph(data_path)
        self.hops = hops
        self.top_k = top_k
        self.llm_config = llm_config  # 保存 LLM 配置字典

    def answer(self, question: str):
        """返回 GraphRAG 的检索证据和草稿答案。"""
        # 1. 检索入口实体
        top_rows = self.ret.retrieve(question, k=self.top_k)

        if not top_rows:
            return {"evidence": [], "draft_answer": "未找到相关实体信息。"}

        center_ids = [r[0]["id"] for r in top_rows]

        # 2. 图谱多跳扩展
        sub = hop_subgraph(self.g, center_ids, hops=self.hops)
        triples = format_subgraph(sub)

        # 3. 调用 LLM 生成答案 (使用策略模式)  需传入配置
        reply = draft_answer_with_graph(
            question, triples, llm_config=self.llm_config)

        return {"evidence": triples, "draft_answer": reply}
