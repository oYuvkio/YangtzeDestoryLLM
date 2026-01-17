"""
配置模块

定义模型配置和服务配置的数据类。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import yaml
except ImportError:
    yaml = None


@dataclass
class ModelConfig:
    """模型配置
    
    Attributes:
        model_path: 模型路径（本地目录或 HuggingFace 模型 ID）
        torch_dtype: 模型精度，默认 float16
        device_map: 设备映射策略，默认 "auto" 自动分配多 GPU
        trust_remote_code: 是否信任远程代码
        low_cpu_mem_usage: 是否使用低 CPU 内存模式
        max_memory: 每个 GPU 的最大显存限制，如 {0: "22GiB", 1: "22GiB"}
        max_new_tokens: 生成的最大 token 数
        temperature: 采样温度，0 表示贪婪解码
        do_sample: 是否使用采样
        timeout: 推理超时时间（秒）
    """
    model_path: str = "/hy-tmp/zjx/models/modelscope/wenge-research/yayi-uie"
    torch_dtype: str = "float16"
    device_map: str = "auto"
    trust_remote_code: bool = True
    low_cpu_mem_usage: bool = True
    max_memory: Optional[Dict[int, str]] = None
    max_new_tokens: int = 4096
    temperature: float = 0.1
    do_sample: bool = False
    timeout: int = 180
    
    def __post_init__(self):
        # 默认三卡配置
        if self.max_memory is None:
            self.max_memory = {0: "22GiB", 1: "22GiB", 2: "22GiB"}


@dataclass
class ServiceConfig:
    """服务配置
    
    Attributes:
        host: 服务监听地址
        port: 服务监听端口
        workers: 工作进程数
        debug: 是否开启调试模式
        verbose: 是否打印详细日志
        log_dir: 日志目录
    """
    host: str = "0.0.0.0"
    port: int = 8000
    workers: int = 1
    debug: bool = False
    verbose: bool = False
    log_dir: str = "logs/yayi-uie"


@dataclass
class Config:
    """完整配置
    
    支持从 YAML 文件、环境变量、命令行参数加载配置。
    优先级：命令行参数 > 环境变量 > YAML 文件 > 默认值
    """
    model: ModelConfig = field(default_factory=ModelConfig)
    service: ServiceConfig = field(default_factory=ServiceConfig)
    
    @classmethod
    def from_yaml(cls, yaml_path: str) -> "Config":
        """从 YAML 文件加载配置"""
        path = Path(yaml_path)
        if not path.exists():
            return cls()
        
        if yaml is None:
            raise ImportError("需要安装 PyYAML: pip install pyyaml")
        
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        model_data = data.get("model", {})
        service_data = data.get("service", {})
        
        return cls(
            model=ModelConfig(**model_data) if model_data else ModelConfig(),
            service=ServiceConfig(**service_data) if service_data else ServiceConfig(),
        )
    
    @classmethod
    def from_env(cls) -> "Config":
        """从环境变量加载配置"""
        config = cls()
        
        # 模型配置
        if os.getenv("YAYI_MODEL_PATH"):
            config.model.model_path = os.getenv("YAYI_MODEL_PATH")
        if os.getenv("YAYI_MAX_NEW_TOKENS"):
            config.model.max_new_tokens = int(os.getenv("YAYI_MAX_NEW_TOKENS"))
        if os.getenv("YAYI_TEMPERATURE"):
            config.model.temperature = float(os.getenv("YAYI_TEMPERATURE"))
        if os.getenv("YAYI_TIMEOUT"):
            config.model.timeout = int(os.getenv("YAYI_TIMEOUT"))
        
        # 服务配置
        if os.getenv("YAYI_HOST"):
            config.service.host = os.getenv("YAYI_HOST")
        if os.getenv("YAYI_PORT"):
            config.service.port = int(os.getenv("YAYI_PORT"))
        if os.getenv("YAYI_DEBUG"):
            config.service.debug = os.getenv("YAYI_DEBUG").lower() in ("true", "1", "yes")
        if os.getenv("YAYI_VERBOSE"):
            config.service.verbose = os.getenv("YAYI_VERBOSE").lower() in ("true", "1", "yes")
        
        return config
    
    def merge(self, other: "Config") -> "Config":
        """合并配置，other 中的非默认值覆盖当前值"""
        # 简单实现：直接返回 other（实际应用中可以更精细地合并）
        return other
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "model": {
                "model_path": self.model.model_path,
                "torch_dtype": self.model.torch_dtype,
                "device_map": self.model.device_map,
                "max_memory": self.model.max_memory,
                "max_new_tokens": self.model.max_new_tokens,
                "temperature": self.model.temperature,
                "do_sample": self.model.do_sample,
                "timeout": self.model.timeout,
            },
            "service": {
                "host": self.service.host,
                "port": self.service.port,
                "workers": self.service.workers,
                "debug": self.service.debug,
                "verbose": self.service.verbose,
                "log_dir": self.service.log_dir,
            },
        }
