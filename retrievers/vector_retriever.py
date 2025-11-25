"""基于句向量的语义检索器。"""
from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
from typing import List, Tuple, Dict
from pathlib import Path
import numpy as np
import torch
import json
import os
# 镜像加速

# 核心组件：向量检索（语义匹配）
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


class VectorRetriever:
    """使用 SentenceTransformer 构建向量索引并执行相似度检索。"""

    def __init__(self, data_path: str, model_name: str = 'paraphrase-multilingual-MiniLM-L12-v2'):
        print(f"正在加载向量模型: {model_name} ...")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=device)

        # 加载数据
        self.rows = [json.loads(l) for l in Path(data_path).read_text(
            encoding="utf-8-sig").splitlines() if l.strip()]
        # 构建文档库：将实体的各个属性拼成一段文本用于嵌入
        self.corpus = [self._concat(r) for r in self.rows]

        print(f"正在构建 {len(self.corpus)} 条数据的向量索引...")
        self.embeddings = self.model.encode(self.corpus)

    @staticmethod
    def _concat(r: Dict) -> str:
        """拼接多字段内容，提升语义表征的覆盖度。"""
        parts = [
            r.get("id", ""),
            r.get("type", ""),
            r.get("location", ""),
            r.get("impact", ""),
            r.get("cause", "")
        ]
        return " ".join([str(p) for p in parts if p])

    def retrieve(self, query: str, k: int = 3) -> List[Tuple[Dict, float]]:
        """返回 Top-K 相关的实体数据及其相似度得分。"""
        query_vec = self.model.encode([query])
        sim_matrix = cosine_similarity(query_vec, self.embeddings)[0]

        # 获取 Top-K 索引
        top_indices = np.argsort(sim_matrix)[::-1][:k]

        results = []
        for idx in top_indices:
            score = sim_matrix[idx]
            # 可以设置一个阈值，例如 0.3
            if score > 0.3:
                results.append((self.rows[idx], float(score)))

        return results
