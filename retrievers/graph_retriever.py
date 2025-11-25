import networkx as nx
from typing import List, Tuple
# 核心组件：图遍历工具（子图提取）

def hop_subgraph(g: nx.DiGraph, center_ids: List[str], hops: int = 2) -> nx.DiGraph:
    """在图中围绕中心节点进行多跳扩展，返回子图。"""
    nodes = set(center_ids)
    frontier = set(center_ids)
    for _ in range(hops):
        nbrs = set()
        for n in frontier:
            nbrs.update(g.successors(n))
            nbrs.update(g.predecessors(n))
        frontier = nbrs - nodes
        nodes.update(nbrs)
    return g.subgraph(nodes).copy()


def format_subgraph(g: nx.DiGraph) -> List[Tuple[str, str, str]]:
    """将子图边转换为 (主体, 关系, 客体) 形式的三元组列表。"""
    triples = []
    for u, v, data in g.edges(data=True):
        rel = data.get("rel", data.get("label", "related_to"))
        triples.append((u, rel, v))
    return triples
