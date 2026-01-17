"""
模型加载模块

负责加载 YAYI-UIE 模型并分配到多个 GPU。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import torch

from .config import ModelConfig

logger = logging.getLogger(__name__)


class ModelLoader:
    """YAYI-UIE 模型加载器
    
    支持多 GPU 分布式加载，使用 device_map="auto" 自动分配模型层到不同 GPU。
    
    Example:
        >>> config = ModelConfig(model_path="/path/to/yayi-uie")
        >>> loader = ModelLoader(config)
        >>> loader.load()
        >>> print(loader.is_loaded)
        True
    """
    
    def __init__(self, config: ModelConfig):
        """初始化模型加载器
        
        Args:
            config: 模型配置
        """
        self.config = config
        self.tokenizer = None
        self.model = None
        self._loaded = False
        self._load_error: Optional[str] = None
    
    def load(self) -> None:
        """加载模型和分词器
        
        Raises:
            RuntimeError: 模型加载失败时抛出
        """
        try:
            from transformers import AutoTokenizer, AutoModelForCausalLM
            
            logger.info(f"开始加载模型: {self.config.model_path}")
            
            # 加载分词器
            self.tokenizer = AutoTokenizer.from_pretrained(
                self.config.model_path,
                use_fast=False,
                trust_remote_code=self.config.trust_remote_code,
            )
            logger.info("分词器加载完成")
            
            # 解析 torch_dtype
            dtype_map = {
                "float16": torch.float16,
                "float32": torch.float32,
                "bfloat16": torch.bfloat16,
            }
            torch_dtype = dtype_map.get(self.config.torch_dtype, torch.float16)
            
            # 构建加载参数
            load_kwargs: Dict[str, Any] = {
                "trust_remote_code": self.config.trust_remote_code,
                "torch_dtype": torch_dtype,
                "device_map": self.config.device_map,
                "low_cpu_mem_usage": self.config.low_cpu_mem_usage,
            }
            if self.config.max_memory:
                load_kwargs["max_memory"] = self.config.max_memory

            import os
            os.makedirs(self.config.offload_folder, exist_ok=True)
            load_kwargs["offload_folder"] = self.config.offload_folder
            load_kwargs["offload_state_dict"] = True
            if self.config.max_memory:
                load_kwargs["max_memory"] = self.config.max_memory
            
            # 加载模型
            self.model = AutoModelForCausalLM.from_pretrained(
                self.config.model_path,
                **load_kwargs,
            )
            
            self._loaded = True
            
            # 打印设备映射信息
            device_map = getattr(self.model, "hf_device_map", None)
            logger.info(f"模型加载完成，设备映射: {device_map}")
            
        except FileNotFoundError as e:
            self._load_error = f"模型路径不存在: {self.config.model_path}"
            logger.error(self._load_error)
            raise RuntimeError(self._load_error) from e
        except torch.cuda.OutOfMemoryError as e:
            self._load_error = f"GPU 显存不足，请调整 max_memory 配置"
            logger.error(self._load_error)
            raise RuntimeError(self._load_error) from e
        except Exception as e:
            self._load_error = f"模型加载失败: {str(e)}"
            logger.error(self._load_error)
            raise RuntimeError(self._load_error) from e
    
    @property
    def is_loaded(self) -> bool:
        """模型是否已加载"""
        return self._loaded
    
    @property
    def load_error(self) -> Optional[str]:
        """加载错误信息"""
        return self._load_error
    
    @property
    def device(self) -> torch.device:
        """模型所在设备"""
        if self.model is None:
            return torch.device("cpu")
        return self.model.device
    
    @property
    def device_map(self) -> Optional[Dict[str, Any]]:
        """模型设备映射"""
        if self.model is None:
            return None
        return getattr(self.model, "hf_device_map", None)
    
    def generate(
        self,
        prompt: str,
        max_new_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        do_sample: Optional[bool] = None,
    ) -> str:
        """生成文本
        
        Args:
            prompt: 输入提示词
            max_new_tokens: 最大生成 token 数，默认使用配置值
            temperature: 采样温度，默认使用配置值
            do_sample: 是否采样，默认使用配置值
        
        Returns:
            生成的文本
        
        Raises:
            RuntimeError: 模型未加载时抛出
        """
        if not self._loaded:
            raise RuntimeError("模型未加载，请先调用 load() 方法")
        
        # 使用配置默认值
        max_new_tokens = max_new_tokens or self.config.max_new_tokens
        temperature = temperature if temperature is not None else self.config.temperature
        do_sample = do_sample if do_sample is not None else self.config.do_sample
        
        # 编码输入
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        input_length = inputs["input_ids"].shape[1]
        
        # 生成
        with torch.no_grad():
            outputs = self.model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=do_sample,
                temperature=temperature if do_sample else None,
            )
        
        # 只解码新生成的部分（去除 prompt）
        generated_ids = outputs[0][input_length:]
        generated_text = self.tokenizer.decode(generated_ids, skip_special_tokens=True)
        
        return generated_text
    
    def unload(self) -> None:
        """卸载模型，释放显存"""
        if self.model is not None:
            del self.model
            self.model = None
        if self.tokenizer is not None:
            del self.tokenizer
            self.tokenizer = None
        self._loaded = False
        
        # 清理 CUDA 缓存
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        
        logger.info("模型已卸载")
