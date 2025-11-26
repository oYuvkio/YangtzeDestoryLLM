"""
用于知识增强 RAG 的图检索与排序工具。

本模块定义了一个 :class:`GraphRetriever` 类，它封装了一个图实例（例如 :class:`networkx.DiGraph`）
并提供了多种检索策略。该类旨在作为检索增强生成（RAG）管道的一部分，根据自然语言查询
选择相关的三元组或子图。

此处实现的检索策略包括：

* **语义检索 (Semantic retrieval)** – 使用提供的嵌入模型（如 SentenceTransformer）
  计算节点名称的稠密向量嵌入，并根据与查询的余弦相似度对节点进行排序。
  这类似于现有 ``demo.py`` 中的方法，但被抽象为一个方法。

* **BM25 检索 (BM25 retrieval)** – 将每个三元组视为由头实体、关系和尾实体组成的文档，
  使用 jieba 对中文文本进行分词，并使用 rank-bm25 库进行相关性评分。
  这可以捕捉到向量相似度可能遗漏的词汇相关三元组。

* **多跳检索 (Multi-hop retrieval)** – 从一组种子节点（例如通过语义检索获得的节点）开始，
  执行广度优先搜索（BFS）至给定的跳数限制，以收集上下文三元组。
  这有助于捕捉间接关系，并为下游 LLM 提供更丰富的上下文。

您可以组合这些策略：首先调用 ``semantic_retrieval`` 找到少量种子节点，
然后调用 ``multi_hop_subgraph`` 提取它们周围的邻域。
"""

from __future__ import annotations
import networkx as nx
from typing import List, Tuple
import math
from collections import defaultdict, deque
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
import networkx as nx
import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.metrics.pairwise import cosine_similarity
import jieba


# ==========================================
# Part 1: 独立函数 (兼容旧代码 kg/query.py)
# ==========================================

def hop_subgraph(g: nx.DiGraph, center_ids: List[str], hops: int = 2) -> nx.DiGraph:
    """
    从中心节点向外扩展 hops 层，返回子图。
    (这是旧版 API，为了兼容性保留)
    """
    if not center_ids or g is None:
        return nx.DiGraph()

    nodes = set(center_ids)
    frontier = set(center_ids)

    for _ in range(hops):
        nbrs = set()
        for n in frontier:
            if g.has_node(n):
                nbrs.update(g.successors(n))
                nbrs.update(g.predecessors(n))
        frontier = nbrs - nodes
        nodes.update(nbrs)

    # 提取子图并返回副本
    return g.subgraph(nodes).copy()


def format_subgraph(g: nx.DiGraph) -> List[Tuple[str, str, str]]:
    """
    将 NetworkX 子图格式化为三元组列表。
    (这是旧版 API，为了兼容性保留)
    """
    triples = []
    for u, v, data in g.edges(data=True):
        # 兼容不同的关系键名: 'relation', 'rel', 'label'
        rel = data.get("relation", data.get(
            "rel", data.get("label", "related_to")))
        triples.append((u, rel, v))
    return triples

# ==========================================
# Part 2: GraphRetriever 类 (新版 API)
# ==========================================


class GraphRetriever:
    """
    从知识图谱中检索信息的辅助类。

    参数
    ----------
    G: nx.DiGraph
        包含知识三元组的有向图。节点标识符应为字符串；
        边属性应包含一个 ``relation`` 键。
    embedding_model: Optional[callable]
        一个具有 ``encode`` 方法的函数或对象，该方法接受字符串列表并返回
        形状为 (n, d) 的 NumPy 数组。这仅在语义检索时需要。
    """

    def __init__(self, G: nx.DiGraph, embedding_model: Optional[Any] = None):
        self.G = G
        self.embedding_model = embedding_model
        # 懒加载：预计算的节点嵌入
        self._node_embeddings: Optional[np.ndarray] = None
        self._node_names: List[str] = []

    def semantic_retrieval(self, query: str, top_k: int = 5, threshold: float = 0.4) -> List[str]:
        """
        使用稠密向量嵌入检索与查询语义最相似的节点。
        如果未提供嵌入模型，将返回空列表。

        参数
        ----------
        query: str
            自然语言问题。
        top_k: int
            返回的最大节点数。
        threshold: float
            包含节点的最小余弦相似度阈值。

        返回
        -------
        List[str]
            按相似度排序的节点标识符列表，最多包含 ``top_k`` 个元素。
        """
        if self.embedding_model is None:
            return []

        # 懒加载计算嵌入
        if self._node_embeddings is None:
            self._node_names = list(self.G.nodes())
            if not self._node_names:
                return []
            # 假设模型返回 numpy 数组
            self._node_embeddings = self.embedding_model.encode(
                self._node_names)

        # 编码查询并确保形状正确
        query_emb = self.embedding_model.encode([query])
        # 兼容处理：如果返回的是列表，转为 numpy
        if not isinstance(query_emb, np.ndarray):
            query_emb = np.array(query_emb)

        # 取第一个向量（因为输入是单元素的列表）并 reshape
        if query_emb.ndim == 1:
            query_vec = query_emb.reshape(1, -1)
        else:
            query_vec = query_emb[0].reshape(1, -1)

        sims = cosine_similarity(query_vec, self._node_embeddings)[0]

        # 按相似度对节点进行排序
        scored = [(name, score) for name, score in zip(
            self._node_names, sims) if score >= threshold]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [name for name, _ in scored[:top_k]]

    def bm25_retrieval(self, query: str, top_k: int = 5) -> List[Tuple[str, str, str]]:
        """
        使用 BM25 检索与查询在词汇上最相关的三元组。

        该方法将每个三元组（头实体-关系-尾实体）视为一个短文档，并针对
        分词后的查询进行评分。对于中文文本分词，如果可用则使用 jieba；
        否则应用朴素的字符级分词。

        参数
        ----------
        query: str
            自然语言问题。
        top_k: int
            返回的最大三元组数。

        返回
        -------
        List[Tuple[str, str, str]]
            按 BM25 分数排序的三元组列表 (head, relation, tail)。
            关系来自于边的 ``relation`` 属性。
        """
        # 如果 BM25Okapi 不可用，返回空列表以避免导入错误
        if BM25Okapi is None:
            return []

        triples: List[Tuple[str, str, str]] = []
        corpus: List[List[str]] = []

        for u, v, data in self.G.edges(data=True):
            rel = data.get("relation", "")
            # 构造文档字符串
            doc = f"{u} {rel} {v}"
            corpus.append(self._tokenise(doc))
            triples.append((u, rel, v))

        if not corpus:
            return []

        bm25 = BM25Okapi(corpus)
        query_tokens = self._tokenise(query)
        scores = bm25.get_scores(query_tokens)

        scored = list(zip(triples, scores))
        # 按分数降序排序
        scored.sort(key=lambda x: x[1], reverse=True)
        return [t for (t, _s) in scored[:top_k]]

    def multi_hop_subgraph(self, seed_nodes: Iterable[str], max_hops: int = 2) -> List[Tuple[str, str, str]]:
        """
        使用 BFS 收集种子节点 ``max_hops`` 范围内的三元组。

        参数
        ----------
        seed_nodes: Iterable[str]
            开始扩展的起始节点列表。图中不存在的节点将被忽略。
        max_hops: int
            遍历的最大跳数。沿任意方向遍历一条边算作一跳。

        返回
        -------
        List[Tuple[str, str, str]]
            代表种子周围诱导子图的三元组列表 (head, relation, tail)。
        """
        visited: Set[str] = set()
        queue: deque[Tuple[str, int]] = deque()

        for n in seed_nodes:
            if self.G.has_node(n):
                queue.append((n, 0))
                visited.add(n)

        triples: List[Tuple[str, str, str]] = []

        while queue:
            current, depth = queue.popleft()
            if depth >= max_hops:
                continue

            # 探索出边 (Outgoing edges)
            for succ in self.G.successors(current):
                # 获取边属性中的关系名称，默认为空字符串
                # 注意：networkx 的 get_edge_data 可能返回 None（如果是多重图则不同），
                # 这里假设是 DiGraph，返回字典
                edge_data = self.G.get_edge_data(current, succ)
                rel = edge_data.get("relation", "") if edge_data else ""

                triples.append((current, rel, succ))
                if succ not in visited:
                    visited.add(succ)
                    queue.append((succ, depth + 1))

            # 探索入边 (Incoming edges) - 双向搜索以捕捉上下文
            for pred in self.G.predecessors(current):
                edge_data = self.G.get_edge_data(pred, current)
                rel = edge_data.get("relation", "") if edge_data else ""

                triples.append((pred, rel, current))
                if pred not in visited:
                    visited.add(pred)
                    queue.append((pred, depth + 1))

        return triples

    def _tokenise(self, text: str) -> List[str]:
        """
        如果 jieba 可用，使用它对中文文本进行分词；否则进行字符级拆分。
        """
        if jieba:
            return list(jieba.cut(text))
        # 回退方案：朴素的字符级分词
        return list(text)


__all__ = ["GraphRetriever", "hop_subgraph", "format_subgraph"]
