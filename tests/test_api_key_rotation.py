#!/usr/bin/env python3
"""测试 API Key 轮换机制"""
import sys
from pathlib import Path

# 确保项目路径在 sys.path 中
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from kg.llm_core import APIKeyManager, get_key_manager, LLMClient

def test_api_key_manager():
    """测试 API Key 管理器"""
    print("=" * 50)
    print("测试 API Key 轮换机制")
    print("=" * 50)

    # 测试初始化
    manager = get_key_manager()
    print(f"\n总 Key 数量: {manager.total_count}")
    print(f"可用 Key 数量: {manager.available_count}")
    print(f"当前 Key: {manager.get_current_key()[:10]}...")

    # 模拟 429 限流
    print("\n模拟 429 限流:")
    for i in range(3):
        key_before = manager.get_current_key()[:8]
        success = manager.mark_rate_limited()
        try:
            key_after = manager.get_current_key()[:8]
        except Exception:
            key_after = "N/A"
        print(f"  轮次 {i+1}: {key_before}... -> {key_after}..., 成功: {success}")
        print(f"          可用: {manager.available_count}/{manager.total_count}")

    # 查看状态
    print("\nKey 状态:")
    status = manager.get_status()
    for key_info in status["keys"]:
        avail = "✓ 可用" if key_info["is_available"] else f"⏳ 冷却中"
        curr = " ← 当前" if key_info["is_current"] else ""
        print(f"  Key #{key_info['index']} ({key_info['preview']}): {avail}{curr}")

    print("\n✅ 测试完成!")


if __name__ == "__main__":
    test_api_key_manager()
