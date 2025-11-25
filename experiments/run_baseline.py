import argparse
import yaml
import sys
import os
from retrievers.text_retriever import BM25Retriever
from kg.query import GraphRAG

# 添加根目录路径防止导入错误
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# GraphRAG vs 纯文本检索对比


def run_text_only(cfg):
    """仅使用 BM25 文本检索评估问答效果。"""
    ret = BM25Retriever(cfg["data_path"])
    q = "2022年鄱阳湖干旱的主要影响是什么？"
    #  适配新的检索器配置结构
    top_k = cfg["retriever"]["top_k"]
    hits = ret.retrieve(q, k=top_k)
    print("[Text BM25] Top-1 impact:", hits[0]
          [0]["impact"] if hits else "None")


def run_graph_rag(cfg):
    """运行 GraphRAG 流程并输出草稿答案与证据。"""
    rag = GraphRAG(
        data_path=cfg["data_path"],
        hops=cfg["graph_hops"],
        top_k=cfg["retriever"]["top_k"],
        llm_config=cfg["llm"]
    )
    q = "2022年鄱阳湖干旱的主要影响是什么？"
    ans = rag.answer(q)
    print("[GraphRAG] draft:", ans["draft_answer"])
    print("[GraphRAG] evidence triples (sample):", ans["evidence"][:5])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/cfg.yaml")
    args = parser.parse_args()

    # 读取配置
    with open(args.config, "r", encoding="utf-8-sig") as f:
        cfg = yaml.safe_load(f)
    run_text_only(cfg)
    print("-" * 30)
    run_graph_rag(cfg)
