"""
YAYI-UIE 统一信息抽取系统

基于 YAYI-UIE 大模型的本地部署与评测系统，支持：
- 命名实体识别 (NER)
- 关系抽取 (RE)
- 事件抽取 (EE)
"""

from .config import ModelConfig, ServiceConfig, Config
from .model import ModelLoader
from .prompt import (
    TaskType,
    PromptStyle,
    TBoxSchema,
    BasePromptBuilder,
    NERPromptBuilder,
    REPromptBuilder,
    EEPromptBuilder,
    GenericNERPromptBuilder,
    GenericREPromptBuilder,
    PromptBuilderFactory,
)
from .parser import (
    ParseResult,
    BaseOutputParser,
    NEROutputParser,
    REOutputParser,
    EEOutputParser,
    OutputParserFactory,
)
from .service import (
    ExtractionRequest,
    ExtractionResponse,
    ExtractionService,
    convert_to_unified_format,
)
from .utils import (
    normalize_text,
    load_jsonl,
    save_jsonl,
    pick_doc_id,
    pick_source_text,
    compute_f1,
)

__version__ = "1.0.0"
__all__ = [
    # Config
    "ModelConfig",
    "ServiceConfig",
    "Config",
    # Model
    "ModelLoader",
    # Prompt
    "TaskType",
    "PromptStyle",
    "TBoxSchema",
    "BasePromptBuilder",
    "NERPromptBuilder",
    "REPromptBuilder",
    "EEPromptBuilder",
    "GenericNERPromptBuilder",
    "GenericREPromptBuilder",
    "PromptBuilderFactory",
    # Parser
    "ParseResult",
    "BaseOutputParser",
    "NEROutputParser",
    "REOutputParser",
    "EEOutputParser",
    "OutputParserFactory",
    # Service
    "ExtractionRequest",
    "ExtractionResponse",
    "ExtractionService",
    "convert_to_unified_format",
    # Utils
    "normalize_text",
    "load_jsonl",
    "save_jsonl",
    "pick_doc_id",
    "pick_source_text",
    "compute_f1",
]
