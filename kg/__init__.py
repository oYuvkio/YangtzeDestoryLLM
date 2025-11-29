"""
KG (知识图谱) 包初始化模块。

本模块暴露了 ``kg`` 包中的关键类和函数，以便于外部便捷导入。
它通过 ``__all__`` 属性定义了包的公共 API。
"""

# 导入 LLM 核心组件
from .llm_core import LLMFactory, draft_answer_with_graph  # noqa: F401

# 导入 Neo4j 适配器
from .neo4j_adapter import Neo4jAdapter  # noqa: F401

# 导入 Schema 定义
from .schema import RELATIONS  # noqa: F401

# 导入知识抽取器 (修正了文件名引用，从 .extractor 导入)
from .extractor import LLMExtractor, DeepLearningExtractor, ExtractionResult, KnowledgeExtractor

# CQ 驱动 Pipeline
from .cq_pipeline import CQLLMPipeline  # noqa: F401

# 注意：GraphRetriever 通常位于 retrievers 包中，不建议在这里重新导出，
# 除非您在 kg 目录下也有同名文件。如果需要，请确保文件路径正确。
# from .query import GraphRAG # 也可以选择暴露 GraphRAG 类

__all__ = [
    "LLMFactory",
    "draft_answer_with_graph",
    "Neo4jAdapter",
    "RELATIONS",
    "LLMExtractor",
    "DeepLearningExtractor",
    "ExtractionResult",
    "KnowledgeExtractor",
    "CQLLMPipeline",
]
