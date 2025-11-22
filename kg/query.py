from retrievers.text_retriever import BM25Retriever
from retrievers.graph_retriever import hop_subgraph, format_subgraph
from kg.build_from_json import build_graph
from kg.llm_stub import draft_with_llm

class GraphRAG:
    def __init__(self, data_path: str, hops: int = 2, top_k: int = 3):
        self.ret = BM25Retriever(data_path)
        self.g = build_graph(data_path)
        self.hops = hops
        self.top_k = top_k

    def answer(self, question: str):
        top_rows = self.ret.retrieve(question, k=self.top_k)
        center_ids = [r[0]["id"] for r in top_rows]
        sub = hop_subgraph(self.g, center_ids, hops=self.hops)
        triples = format_subgraph(sub)
        reply = draft_with_llm(question, triples)
        return {"evidence": triples, "draft_answer": reply}
