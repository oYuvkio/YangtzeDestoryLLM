from retrievers.text_retriever import BM25Retriever
from retrievers.graph_retriever import hop_subgraph, format_subgraph
from kg.build_from_json import build_graph
# 🔥 修改这里：导入新的核心模块，不再用 stub
from kg.llm_core import draft_answer_with_graph 

# GraphRAG引擎（负责问答推理）
class GraphRAG:
    def __init__(self, data_path: str, hops: int = 2, top_k: int = 3, llm_provider: str = "zhipu"):
        self.ret = BM25Retriever(data_path)
        self.g = build_graph(data_path)
        self.hops = hops
        self.top_k = top_k
        self.llm_provider = llm_provider # 支持切换模型

    def answer(self, question: str):
        # 1. 检索入口实体
        top_rows = self.ret.retrieve(question, k=self.top_k)
        
        if not top_rows:
            return {"evidence": [], "draft_answer": "未找到相关实体信息。"}

        center_ids = [r[0]["id"] for r in top_rows]
        
        # 2. 图谱多跳扩展
        sub = hop_subgraph(self.g, center_ids, hops=self.hops)
        triples = format_subgraph(sub)
        
        # 3. 调用 LLM 生成答案 (使用策略模式)
        reply = draft_answer_with_graph(question, triples, provider=self.llm_provider)
        
        return {"evidence": triples, "draft_answer": reply}