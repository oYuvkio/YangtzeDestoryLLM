#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 LLM 客户端是否正确实现 close 方法"""

import sys
from pathlib import Path

# 确保能导入项目模块
sys.path.insert(0, str(Path(__file__).parent))

try:
    from kg.llm_core import LLMClient
    print("✅ LLMClient 导入成功")
    
    # 检查 close 方法
    if hasattr(LLMClient, 'close'):
        print("✅ LLMClient.close() 方法存在")
    else:
        print("❌ LLMClient.close() 方法不存在")
        sys.exit(1)
    
    # 检查上下文管理器
    if hasattr(LLMClient, '__enter__') and hasattr(LLMClient, '__exit__'):
        print("✅ LLMClient 支持上下文管理器 (with 语句)")
    else:
        print("⚠️  LLMClient 不支持上下文管理器")
    
    print("\n✅ 所有检查通过！修复已生效。")
    
except Exception as e:
    print(f"❌ 测试失败: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
