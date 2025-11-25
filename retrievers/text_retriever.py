import json
from pathlib import Path
from rank_bm25 import BM25Okapi
import jieba

# 基线算法：BM25（关键词匹配）


class BM25Retriever:
    """基于 BM25 的关键词检索器，用于快速定位相关事件。"""

    def __init__(self, path: str):
        rows = [json.loads(l) for l in Path(path).read_text(
            encoding="utf-8-sig").splitlines() if l.strip()]
        self.rows = rows
        corpus = [self._concat(r) for r in rows]
        self.tokens = [jieba.lcut(doc)
                       for doc in corpus]  # 可替换为 jieba.lcut 做中文分词
        self.bm25 = BM25Okapi(self.tokens)

    @staticmethod
    def _concat(r):
        """拼接结构化字段，形成 BM25 的文档输入。"""
        return " ".join([str(r.get(k, "")) for k in ["type", "location", "time", "impact", "cause", "measure"]])

    def retrieve(self, query: str, k: int = 3):
        """返回与查询最匹配的前 k 条记录及得分。"""
        # scores = self.bm25.get_scores(query.split())
        scores = self.bm25.get_scores(jieba.lcut(query))
        idxs = sorted(range(len(scores)),
                      key=lambda i: scores[i], reverse=True)[:k]
        return [(self.rows[i], scores[i]) for i in idxs]
