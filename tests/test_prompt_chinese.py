#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
验证 LLM Prompt 中文约束的测试脚本
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from tools.corpus_cleaner import LLMSemanticSplitter

# 打印系统提示词
print("=" * 70)
print("【系统提示词 (SYSTEM_PROMPT)】")
print("=" * 70)
print(LLMSemanticSplitter.SYSTEM_PROMPT)
print()

# 创建一个示例实例并打印用户提示词
try:
    from dataclasses import dataclass
    
    @dataclass
    class MockConfig:
        model_name: str = "mock-model"
        base_url: str = "http://mock"
        temperature: float = 0.1
        
        def to_factory_dict(self):
            return {}
    
    splitter = LLMSemanticSplitter(config=MockConfig())
    
    # 生成示例用户提示词
    sample_text = "这是一个测试文本，用于演示用户提示词的格式。" * 10
    user_prompt = splitter._build_user_prompt(sample_text)
    
    print("=" * 70)
    print("【用户提示词 (USER_PROMPT) 示例】")
    print("=" * 70)
    print(user_prompt)
    
except Exception as e:
    print(f"⚠️ 创建示例实例失败: {e}")
    print("这是正常的，因为我们没有配置实际的 LLM 后端")
