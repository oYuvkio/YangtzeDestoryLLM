"""
FastAPI HTTP 服务模块

提供 RESTful API 接口用于信息抽取。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .config import ModelConfig, ServiceConfig
from .model import ModelLoader
from .prompt import TaskType, TBoxSchema, PromptStyle
from .service import ExtractionRequest, ExtractionResponse, ExtractionService

logger = logging.getLogger(__name__)


# ============== Pydantic 模型 ==============

class ExtractRequestModel(BaseModel):
    """HTTP 抽取请求模型"""
    text: str = Field(..., description="待抽取的文本")
    task_type: str = Field(..., description="任务类型: ner, re, ee")
    doc_id: Optional[str] = Field(None, description="文档 ID")
    entity_types: Optional[List[str]] = Field(None, description="实体类型列表 (NER)")
    relation_types: Optional[List[str]] = Field(None, description="关系类型列表 (RE)")
    event_roles: Optional[List[str]] = Field(None, description="事件角色列表 (EE)")
    prompt_style: Optional[str] = Field("default", description="提示词风格: default/generic")
    fewshot: Optional[bool] = Field(True, description="是否启用 few-shot 示例")
    
    class Config:
        json_schema_extra = {
            "example": {
                "text": "1998年长江流域发生特大洪水，造成严重损失。",
                "task_type": "re",
                "doc_id": "doc_001",
                "relation_types": ["发生于", "位于", "导致"]
            }
        }


class ExtractResponseModel(BaseModel):
    """HTTP 抽取响应模型"""
    doc_id: str = Field(..., description="文档 ID")
    task_type: str = Field(..., description="任务类型")
    raw_output: str = Field(..., description="模型原始输出")
    parsed_result: Dict[str, Any] = Field(..., description="解析后的结构化结果")
    success: bool = Field(..., description="是否成功")
    latency_ms: float = Field(..., description="延迟时间（毫秒）")
    error: Optional[str] = Field(None, description="错误信息")


class HealthResponseModel(BaseModel):
    """健康检查响应模型"""
    status: str = Field(..., description="服务状态: healthy, loading, error")
    model_loaded: bool = Field(..., description="模型是否已加载")
    model_path: str = Field(..., description="模型路径")
    device_map: Optional[Dict[str, Any]] = Field(None, description="设备映射")


class BatchExtractRequestModel(BaseModel):
    """批量抽取请求模型"""
    requests: List[ExtractRequestModel] = Field(..., description="抽取请求列表")


# ============== API 应用 ==============

def create_app(
    service: ExtractionService,
    model_config: ModelConfig,
    service_config: ServiceConfig,
) -> FastAPI:
    """创建 FastAPI 应用
    
    Args:
        service: 抽取服务实例
        model_config: 模型配置
    
    Returns:
        FastAPI 应用实例
    """
    app = FastAPI(
        title="YAYI-UIE Extraction Service",
        description="基于 YAYI-UIE 的统一信息抽取服务，支持 NER、RE、EE 三种任务",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.state.semaphore = asyncio.Semaphore(service_config.max_concurrency)
    app.state.request_timeout = service_config.request_timeout
    
    # 添加 CORS 中间件（支持跨域访问）
    from fastapi.middleware.cors import CORSMiddleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/health", response_model=HealthResponseModel, tags=["系统"])
    async def health_check():
        """健康检查
        
        返回服务状态和模型信息。
        """
        device_map = None
        if service.model_loader.model:
            device_map = getattr(service.model_loader.model, "hf_device_map", None)
        
        status = "healthy" if service.model_loader.is_loaded else "loading"
        if service.model_loader.load_error:
            status = "error"
        
        return HealthResponseModel(
            status=status,
            model_loaded=service.model_loader.is_loaded,
            model_path=model_config.model_path,
            device_map=device_map,
        )

    async def run_extract_with_limits(extraction_request: ExtractionRequest) -> ExtractionResponse:
        async with app.state.semaphore:
            return await asyncio.wait_for(
                run_in_threadpool(service.extract, extraction_request),
                timeout=app.state.request_timeout,
            )
    
    @app.post("/extract", response_model=ExtractResponseModel, tags=["抽取"])
    async def extract(request: ExtractRequestModel):
        """单条抽取
        
        对单个文本执行信息抽取任务。
        
        - **text**: 待抽取的文本
        - **task_type**: 任务类型 (ner/re/ee)
        - **doc_id**: 文档 ID（可选）
        - **entity_types**: 实体类型列表，用于 NER 任务（可选）
        - **relation_types**: 关系类型列表，用于 RE 任务（可选）
        - **event_roles**: 事件角色列表，用于 EE 任务（可选）
        """
        # 检查模型是否已加载
        if not service.model_loader.is_loaded:
            raise HTTPException(status_code=503, detail="模型未加载")
        
        # 验证任务类型
        try:
            task_type = TaskType(request.task_type.lower())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"无效的任务类型: {request.task_type}，必须是 ner, re, ee 之一",
            )
        
        # 构建 schema
        schema = None
        if request.entity_types or request.relation_types or request.event_roles:
            schema = TBoxSchema(
                entity_types=request.entity_types or [],
                relation_types=request.relation_types or [],
                event_roles=request.event_roles or [],
            )
        
        # 执行抽取
        extraction_request = ExtractionRequest(
            text=request.text,
            task_type=task_type,
            doc_id=request.doc_id,
            schema=schema,
            prompt_style=PromptStyle(request.prompt_style or "default"),
            fewshot=bool(request.fewshot) if request.fewshot is not None else True,
        )
        
        try:
            response = await run_extract_with_limits(extraction_request)
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="抽取超时")
        
        return ExtractResponseModel(
            doc_id=response.doc_id,
            task_type=response.task_type,
            raw_output=response.raw_output,
            parsed_result=response.parsed_result,
            success=response.success,
            latency_ms=response.latency_ms,
            error=response.error,
        )
    
    @app.post("/batch_extract", response_model=List[ExtractResponseModel], tags=["抽取"])
    async def batch_extract(batch_request: BatchExtractRequestModel):
        """批量抽取
        
        对多个文本执行信息抽取任务。
        """
        # 检查模型是否已加载
        if not service.model_loader.is_loaded:
            raise HTTPException(status_code=503, detail="模型未加载")
        
        responses = []
        
        for req in batch_request.requests:
            # 验证任务类型
            try:
                task_type = TaskType(req.task_type.lower())
            except ValueError:
                responses.append(ExtractResponseModel(
                    doc_id=req.doc_id or "",
                    task_type=req.task_type,
                    raw_output="",
                    parsed_result={},
                    success=False,
                    latency_ms=0,
                    error=f"无效的任务类型: {req.task_type}",
                ))
                continue
            
            # 构建 schema
            schema = None
            if req.entity_types or req.relation_types or req.event_roles:
                schema = TBoxSchema(
                    entity_types=req.entity_types or [],
                    relation_types=req.relation_types or [],
                    event_roles=req.event_roles or [],
                )
            
            # 执行抽取
            extraction_request = ExtractionRequest(
                text=req.text,
                task_type=task_type,
                doc_id=req.doc_id,
                schema=schema,
                prompt_style=PromptStyle(req.prompt_style or "default"),
                fewshot=bool(req.fewshot) if req.fewshot is not None else True,
            )
            
            try:
                response = await run_extract_with_limits(extraction_request)
            except asyncio.TimeoutError:
                responses.append(ExtractResponseModel(
                    doc_id=req.doc_id or "",
                    task_type=req.task_type,
                    raw_output="",
                    parsed_result={},
                    success=False,
                    latency_ms=0,
                    error="timeout",
                ))
                continue
            except Exception as exc:
                responses.append(ExtractResponseModel(
                    doc_id=req.doc_id or "",
                    task_type=req.task_type,
                    raw_output="",
                    parsed_result={},
                    success=False,
                    latency_ms=0,
                    error=str(exc),
                ))
                continue
            
            responses.append(ExtractResponseModel(
                doc_id=response.doc_id,
                task_type=response.task_type,
                raw_output=response.raw_output,
                parsed_result=response.parsed_result,
                success=response.success,
                latency_ms=response.latency_ms,
                error=response.error,
            ))
        
        return responses
    
    @app.post("/extract_all", response_model=Dict[str, ExtractResponseModel], tags=["抽取"])
    async def extract_all(request: ExtractRequestModel):
        """全任务抽取
        
        对单个文本执行所有任务类型（NER、RE、EE）的抽取。
        """
        # 检查模型是否已加载
        if not service.model_loader.is_loaded:
            raise HTTPException(status_code=503, detail="模型未加载")
        
        # 构建 schema
        schema = None
        if request.entity_types or request.relation_types or request.event_roles:
            schema = TBoxSchema(
                entity_types=request.entity_types or [],
                relation_types=request.relation_types or [],
                event_roles=request.event_roles or [],
            )
        
        # 执行所有任务
        try:
            results = await asyncio.wait_for(
                run_in_threadpool(
                    service.extract_all_tasks,
                    text=request.text,
                    doc_id=request.doc_id,
                    schema=schema,
                    prompt_style=PromptStyle(request.prompt_style or "default"),
                    fewshot=bool(request.fewshot) if request.fewshot is not None else True,
                ),
                timeout=app.state.request_timeout,
            )
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="抽取超时")
        
        return {
            task_type: ExtractResponseModel(
                doc_id=resp.doc_id,
                task_type=resp.task_type,
                raw_output=resp.raw_output,
                parsed_result=resp.parsed_result,
                success=resp.success,
                latency_ms=resp.latency_ms,
                error=resp.error,
            )
            for task_type, resp in results.items()
        }
    
    return app


def run_server(
    model_config: ModelConfig,
    service_config: ServiceConfig,
) -> None:
    """启动 HTTP 服务
    
    Args:
        model_config: 模型配置
        service_config: 服务配置
    """
    import uvicorn
    
    # 加载模型
    logger.info("正在加载模型...")
    loader = ModelLoader(model_config)
    loader.load()
    
    # 创建服务
    service = ExtractionService(
        model_loader=loader,
        max_new_tokens=model_config.max_new_tokens,
        temperature=model_config.temperature,
        do_sample=model_config.do_sample,
        verbose=service_config.verbose,
    )
    
    # 创建应用
    app = create_app(service, model_config, service_config)
    
    # 启动服务
    logger.info(f"启动服务: http://{service_config.host}:{service_config.port}")
    uvicorn.run(
        app,
        host=service_config.host,
        port=service_config.port,
        workers=service_config.workers,
    )


# ============== 命令行入口 ==============

def main():
    """命令行入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="YAYI-UIE HTTP 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8000, help="监听端口")
    parser.add_argument("--workers", type=int, default=1, help="工作进程数")
    parser.add_argument("--max-concurrency", type=int, default=1, help="最大并发请求数")
    parser.add_argument("--request-timeout", type=int, default=300, help="单请求超时秒数")
    parser.add_argument("--model-path", default="/hy-tmp/zjx/models/modelscope/wenge-research/yayi-uie")
    parser.add_argument("--max-new-tokens", type=int, default=2048)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument(
        "--device-map",
        default="balanced_low_0",
        choices=["auto", "balanced", "balanced_low_0", "sequential"],
        help="device_map 策略 (默认: balanced_low_0)",
    )
    parser.add_argument("--cpu-memory", default="48GiB", help="CPU 最大内存上限 (默认: 48GiB)")
    parser.add_argument("--gpu-memory", default="22GiB", help="每张 GPU 最大显存上限 (默认: 22GiB)")
    parser.add_argument("--offload-folder", default="/hy-tmp/zjx/offload", help="权重/状态 offload 目录")
    parser.add_argument("-v", "--verbose", action="store_true", help="详细日志")
    
    args = parser.parse_args()
    
    model_config = ModelConfig(
        model_path=args.model_path,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
        device_map=args.device_map,
        cpu_max_memory=args.cpu_memory,
        gpu_max_memory=args.gpu_memory,
        offload_folder=args.offload_folder,
    )
    
    service_config = ServiceConfig(
        host=args.host,
        port=args.port,
        workers=args.workers,
        max_concurrency=args.max_concurrency,
        request_timeout=args.request_timeout,
        verbose=args.verbose,
    )
    
    run_server(model_config, service_config)


if __name__ == "__main__":
    main()
