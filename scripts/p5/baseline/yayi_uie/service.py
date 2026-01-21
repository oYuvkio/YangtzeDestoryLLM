"""
抽取服务模块

核心服务类，协调模型推理、提示词构建和输出解析。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .config import ModelConfig
from .model import ModelLoader
from .parser import OutputParserFactory, ParseResult
from .prompt import PromptBuilderFactory, TaskType, TBoxSchema, PromptStyle

logger = logging.getLogger(__name__)


@dataclass
class ExtractionRequest:
    """抽取请求
    
    Attributes:
        text: 待抽取的文本
        task_type: 任务类型 (NER/RE/EE)
        doc_id: 文档 ID，可选
        schema: TBox 模式定义，可选
    """
    text: str
    task_type: TaskType
    doc_id: Optional[str] = None
    schema: Optional[TBoxSchema] = None
    prompt_style: PromptStyle = PromptStyle.DEFAULT
    fewshot: bool = True


@dataclass
class ExtractionResponse:
    """抽取响应
    
    Attributes:
        doc_id: 文档 ID
        task_type: 任务类型
        raw_output: 模型原始输出
        parsed_result: 解析后的结构化结果
        success: 是否成功
        latency_ms: 延迟时间（毫秒）
        error: 错误信息
    """
    doc_id: str
    task_type: str
    raw_output: str
    parsed_result: Dict[str, Any]
    success: bool
    latency_ms: float
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "doc_id": self.doc_id,
            "task_type": self.task_type,
            "raw_output": self.raw_output,
            "parsed_result": self.parsed_result,
            "success": self.success,
            "latency_ms": self.latency_ms,
            "error": self.error,
        }


class ExtractionService:
    """信息抽取服务
    
    协调模型推理、提示词构建和输出解析，提供统一的抽取接口。
    
    Example:
        >>> config = ModelConfig()
        >>> loader = ModelLoader(config)
        >>> loader.load()
        >>> service = ExtractionService(loader)
        >>> request = ExtractionRequest(text="张三在北京工作。", task_type=TaskType.NER)
        >>> response = service.extract(request)
        >>> print(response.parsed_result)
    """
    
    def __init__(
        self,
        model_loader: ModelLoader,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        do_sample: Optional[bool] = None,
        verbose: bool = False,
    ):
        """初始化抽取服务
        
        Args:
            model_loader: 模型加载器
            max_new_tokens: 最大生成 token 数
            temperature: 采样温度
            do_sample: 是否采样
            verbose: 是否打印详细日志
        """
        self.model_loader = model_loader
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.do_sample = do_sample
        self.verbose = verbose
    
    def extract(self, request: ExtractionRequest) -> ExtractionResponse:
        """执行单条抽取
        
        Args:
            request: 抽取请求
        
        Returns:
            抽取响应
        """
        start_time = time.time()
        doc_id = request.doc_id or ""
        
        # 检查模型是否已加载
        if not self.model_loader.is_loaded:
            return ExtractionResponse(
                doc_id=doc_id,
                task_type=request.task_type.value,
                raw_output="",
                parsed_result={},
                success=False,
                latency_ms=0,
                error="模型未加载",
            )
        
        try:
            # 构建提示词
            builder = PromptBuilderFactory.get_builder(
                request.task_type,
                style=request.prompt_style,
                fewshot=request.fewshot,
            )
            prompt = builder.build(request.text, request.schema)
            
            if self.verbose:
                logger.info(f"[{doc_id}] Prompt: {prompt[:200]}...")
            
            # 模型推理
            raw_output = self.model_loader.generate(
                prompt,
                max_new_tokens=self.max_new_tokens,
                temperature=self.temperature,
                do_sample=self.do_sample,
            )
            
            if self.verbose:
                logger.info(f"[{doc_id}] Raw output: {raw_output[:500]}...")
            
            # 解析输出
            parser = OutputParserFactory.get_parser(request.task_type)
            parse_result = parser.parse(raw_output)
            
            latency_ms = (time.time() - start_time) * 1000
            
            return ExtractionResponse(
                doc_id=doc_id,
                task_type=request.task_type.value,
                raw_output=raw_output,
                parsed_result=parse_result.data,
                success=parse_result.success,
                latency_ms=latency_ms,
                error=parse_result.error,
            )
            
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e)
            logger.error(f"[{doc_id}] 抽取失败: {error_msg}")
            
            return ExtractionResponse(
                doc_id=doc_id,
                task_type=request.task_type.value,
                raw_output="",
                parsed_result={},
                success=False,
                latency_ms=latency_ms,
                error=error_msg,
            )
    
    def batch_extract(
        self,
        requests: List[ExtractionRequest],
        progress_callback: Optional[callable] = None,
    ) -> List[ExtractionResponse]:
        """批量抽取
        
        Args:
            requests: 抽取请求列表
            progress_callback: 进度回调函数，接收 (current, total) 参数
        
        Returns:
            抽取响应列表
        """
        responses = []
        total = len(requests)
        
        for i, request in enumerate(requests):
            response = self.extract(request)
            responses.append(response)
            
            if progress_callback:
                progress_callback(i + 1, total)
        
        return responses
    
    def extract_all_tasks(
        self,
        text: str,
        doc_id: Optional[str] = None,
        schema: Optional[TBoxSchema] = None,
        prompt_style: PromptStyle = PromptStyle.DEFAULT,
        fewshot: bool = True,
    ) -> Dict[str, ExtractionResponse]:
        """对同一文本执行所有任务类型的抽取
        
        Args:
            text: 待抽取的文本
            doc_id: 文档 ID
            schema: TBox 模式定义
        
        Returns:
            任务类型到响应的映射
        """
        results = {}
        
        for task_type in TaskType:
            request = ExtractionRequest(
                text=text,
                task_type=task_type,
                doc_id=doc_id,
                schema=schema,
                prompt_style=prompt_style,
                fewshot=fewshot,
            )
            results[task_type.value] = self.extract(request)
        
        return results


def convert_to_unified_format(
    response: ExtractionResponse,
    source_text: str = "",
) -> Dict[str, Any]:
    """将抽取响应转换为项目统一格式
    
    兼容 kg.extraction_output.build_extraction_record() 的输出格式。
    
    Args:
        response: 抽取响应
        source_text: 原始文本
    
    Returns:
        统一格式的字典
    """
    record = {
        "doc_id": response.doc_id,
        "source_text": source_text,
        "entities": [],
        "events": [],
        "triples": [],
        "raw_output": response.raw_output,
        "latency_ms": response.latency_ms,
    }
    
    if response.error:
        record["error"] = response.error
        return record
    
    parsed = response.parsed_result
    
    # 根据任务类型提取结果
    if response.task_type == TaskType.NER.value:
        record["entities"] = parsed.get("entities", [])
    elif response.task_type == TaskType.RE.value:
        record["triples"] = parsed.get("triples", [])
    elif response.task_type == TaskType.EE.value:
        events = parsed.get("events", [])
        # 转换事件格式
        for event in events:
            record["events"].append({
                "event_type": event.get("event_type", ""),
                "name": event.get("event_type", ""),  # 使用事件类型作为名称
                "arguments": event.get("arguments", {}),
            })
    
    return record
