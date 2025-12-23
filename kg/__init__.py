"""
KG (知识图谱) 包初始化模块。

本模块暴露了 ``kg`` 包中的关键类和函数，以便于外部便捷导入。
它通过 ``__all__`` 属性定义了包的公共 API。
"""

from typing import Optional

# 导入 LLM 核心组件
from .llm_core import LLMFactory, draft_answer_with_graph  # noqa: F401

__all__ = [
    "LLMFactory",
    "draft_answer_with_graph",
]

# 导入 Neo4j 适配器（可选依赖：未安装 neo4j 包时不应导致 kg 整包不可用）
try:
    from .neo4j_adapter import Neo4jAdapter  # noqa: F401
    _NEO4J_AVAILABLE = True
    _NEO4J_IMPORT_ERROR: Optional[Exception] = None
except Exception as e:  # pragma: no cover - 环境依赖差异
    _NEO4J_AVAILABLE = False
    _NEO4J_IMPORT_ERROR = e

    class Neo4jAdapter:  # type: ignore[no-redef]
        """Neo4j 适配器占位符（neo4j 依赖未安装时）。"""

        def __init__(self, *_: object, **__: object) -> None:
            raise ImportError(
                "Neo4jAdapter 需要额外依赖 `neo4j`，当前环境未安装或导入失败。"
                "请在 Conda 环境中执行 `pip install neo4j` 或 `pip install -r requirements.txt`。"
            ) from _NEO4J_IMPORT_ERROR

# 仅在 neo4j 依赖可用时导出 Neo4jAdapter
if _NEO4J_AVAILABLE:
    __all__.append("Neo4jAdapter")

# 导入 Schema 定义（可选：避免因环境缺依赖导致 kg 无法导入）
try:
    from .schema import RELATIONS  # noqa: F401
    __all__.append("RELATIONS")
except Exception:  # pragma: no cover - 环境依赖差异
    RELATIONS = None  # type: ignore[assignment]

# 导入知识抽取器（可选）
try:
    from .extractor import (  # noqa: F401
        LLMExtractor,
        DeepLearningExtractor,
        ExtractionResult,
        KnowledgeExtractor,
    )
    __all__.extend([
        "LLMExtractor",
        "DeepLearningExtractor",
        "ExtractionResult",
        "KnowledgeExtractor",
    ])
except Exception:  # pragma: no cover - 环境依赖差异
    pass

# CQ 驱动 Pipeline（可选：依赖 sentence-transformers 等）
try:
    from .cq_pipeline import CQLLMPipeline  # noqa: F401
    __all__.append("CQLLMPipeline")
except Exception:  # pragma: no cover - 环境依赖差异
    pass

# 注意：GraphRetriever 通常位于 retrievers 包中，不建议在这里重新导出，
# 除非您在 kg 目录下也有同名文件。如果需要，请确保文件路径正确。
# from .query import GraphRAG
