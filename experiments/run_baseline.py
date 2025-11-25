import argparse, yaml
from retrievers.text_retriever import BM25Retriever
from kg.query import GraphRAG


def run_text_only(cfg):
    """仅使用 BM25 文本检索评估问答效果。"""
    ret = BM25Retriever(cfg["data_path"])
    q = "2022年鄱阳湖干旱的主要影响是什么？"
    hits = ret.retrieve(q, k=cfg["top_k"])
    print("[Text BM25] Top-1 impact:", hits[0][0]["impact"])


def run_graph_rag(cfg):
    """运行 GraphRAG 流程并输出草稿答案与证据。"""
    rag = GraphRAG(cfg["data_path"], hops=cfg["graph_hops"], top_k=cfg["top_k"])
    q = "2022年鄱阳湖干旱的主要影响是什么？"
    ans = rag.answer(q)
    print("[GraphRAG] draft:", ans["draft_answer"])
    print("[GraphRAG] evidence triples (sample):", ans["evidence"][:5])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/demo.yaml")
    args = parser.parse_args()
    cfg = yaml.safe_load(open(args.config, "r", encoding="utf-8"))
    run_text_only(cfg)
    run_graph_rag(cfg)
