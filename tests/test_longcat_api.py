#!/usr/bin/env python3
"""
LongCat API 测试脚本

测试两种调用方式：
1. OpenAI SDK 方式（与项目代码一致）
2. requests POST 方式（直接 HTTP 调用）

使用方法：
    python tests/test_longcat_api.py
    python tests/test_longcat_api.py --api-key YOUR_KEY
"""
import os
import sys
import argparse
import json
from typing import Optional

# =============================================================================
# 配置
# =============================================================================
DEFAULT_BASE_URL = "https://api.longcat.chat/openai/v1"
DEFAULT_MODEL = "LongCat-Flash-Chat"
TEST_PROMPT = "你好！请用一句话介绍自己。"


def print_header(title: str) -> None:
    """打印分隔标题"""
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def print_result(success: bool, response: str, duration: float) -> None:
    """打印测试结果"""
    status = "✅ 成功" if success else "❌ 失败"
    print(f"状态: {status}")
    print(f"耗时: {duration:.2f}s")
    print(f"响应: {response[:200]}{'...' if len(response) > 200 else ''}")


# =============================================================================
# 方式一：OpenAI SDK
# =============================================================================
def test_openai_sdk(api_key: str, base_url: str, model: str) -> bool:
    """
    使用 OpenAI SDK 测试 API。
    
    这与项目中 kg/llm_core.py 的调用方式一致。
    """
    print_header("方式一：OpenAI SDK")
    
    try:
        from openai import OpenAI
    except ImportError:
        print("❌ 未安装 openai 库，请先运行: pip install openai")
        return False
    
    import time
    
    print(f"Base URL: {base_url}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"Prompt: {TEST_PROMPT}")
    print()
    
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )
        
        start = time.time()
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "user", "content": TEST_PROMPT}
            ],
            max_tokens=100,
            temperature=0.7,
        )
        duration = time.time() - start
        
        content = response.choices[0].message.content or ""
        print_result(True, content, duration)
        
        # 打印完整响应（调试用）
        print(f"\n完整响应对象:")
        print(f"  - model: {response.model}")
        print(f"  - usage: {response.usage}")
        
        return True
        
    except Exception as e:
        print_result(False, str(e), 0)
        print(f"\n错误详情: {type(e).__name__}: {e}")
        return False


# =============================================================================
# 方式二：requests POST
# =============================================================================
def test_requests_post(api_key: str, base_url: str, model: str) -> bool:
    """
    使用 requests 库直接发送 POST 请求测试 API。
    
    这与 curl 命令等效。
    """
    print_header("方式二：requests POST")
    
    try:
        import requests
    except ImportError:
        print("❌ 未安装 requests 库，请先运行: pip install requests")
        return False
    
    import time
    
    # 构建请求 URL（注意：base_url 已包含 /v1，需要拼接 /chat/completions）
    url = f"{base_url.rstrip('/')}/chat/completions"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    
    data = {
        "model": model,
        "messages": [
            {"role": "user", "content": TEST_PROMPT}
        ],
        "max_tokens": 100,
        "temperature": 0.7,
    }
    
    print(f"URL: {url}")
    print(f"Model: {model}")
    print(f"API Key: {api_key[:10]}...{api_key[-4:]}")
    print(f"Prompt: {TEST_PROMPT}")
    print()
    
    try:
        start = time.time()
        response = requests.post(
            url,
            headers=headers,
            json=data,
            timeout=30,
        )
        duration = time.time() - start
        
        # 检查状态码
        if response.status_code != 200:
            print_result(False, f"HTTP {response.status_code}: {response.text}", duration)
            return False
        
        # 解析响应
        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        
        print_result(True, content, duration)
        
        # 打印完整响应（调试用）
        print(f"\n完整响应 JSON:")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:500])
        
        return True
        
    except requests.exceptions.Timeout:
        print_result(False, "请求超时", 30)
        return False
    except requests.exceptions.ConnectionError as e:
        print_result(False, f"连接失败: {e}", 0)
        return False
    except Exception as e:
        print_result(False, str(e), 0)
        print(f"\n错误详情: {type(e).__name__}: {e}")
        return False


# =============================================================================
# 方式三：测试项目中的 LLMClient
# =============================================================================
def test_llm_client(api_key: str, base_url: str, model: str) -> bool:
    """
    使用项目中的 LLMClient 测试。
    
    这会验证 kg/llm_core.py 的完整功能。
    """
    print_header("方式三：项目 LLMClient")
    
    # 设置环境变量（LLMClient 从环境变量读取 API Key）
    os.environ["OPENAI_API_KEY"] = api_key
    
    try:
        # 添加项目根目录到路径
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        
        from kg.llm_core import LLMClient
    except ImportError as e:
        print(f"❌ 无法导入 LLMClient: {e}")
        return False
    
    import time
    
    config = {
        "base_url": base_url,
        "model_name": model,
        "temperature": 0.7,
        "max_tokens": 100,
        "max_retries": 1,
        "timeout": 30,
    }
    
    print(f"Config: {json.dumps(config, indent=2)}")
    print(f"Prompt: {TEST_PROMPT}")
    print()
    
    try:
        client = LLMClient(config)
        
        start = time.time()
        response = client.chat(TEST_PROMPT)
        duration = time.time() - start
        
        if response:
            print_result(True, response, duration)
            return True
        else:
            print_result(False, "响应为空", duration)
            return False
        
    except Exception as e:
        print_result(False, str(e), 0)
        print(f"\n错误详情: {type(e).__name__}: {e}")
        return False


# =============================================================================
# 主函数
# =============================================================================
def main():
    parser = argparse.ArgumentParser(
        description="LongCat API 测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python tests/test_longcat_api.py
  python tests/test_longcat_api.py --api-key ak_xxxxx
  python tests/test_longcat_api.py --test openai
  python tests/test_longcat_api.py --test requests
  python tests/test_longcat_api.py --test client
        """
    )
    parser.add_argument(
        "--api-key", "-k",
        default=os.getenv("OPENAI_API_KEY", ""),
        help="API Key（默认从环境变量 OPENAI_API_KEY 读取）"
    )
    parser.add_argument(
        "--base-url", "-u",
        default=DEFAULT_BASE_URL,
        help=f"API Base URL（默认: {DEFAULT_BASE_URL}）"
    )
    parser.add_argument(
        "--model", "-m",
        default=DEFAULT_MODEL,
        help=f"模型名称（默认: {DEFAULT_MODEL}）"
    )
    parser.add_argument(
        "--test", "-t",
        choices=["all", "openai", "requests", "client"],
        default="all",
        help="测试方式: all=全部, openai=SDK, requests=POST, client=LLMClient"
    )
    
    args = parser.parse_args()
    
    # 检查 API Key
    if not args.api_key:
        print("❌ 未提供 API Key")
        print("请通过以下方式之一提供：")
        print("  1. 命令行参数: --api-key YOUR_KEY")
        print("  2. 环境变量: export OPENAI_API_KEY=YOUR_KEY")
        print("  3. .env 文件: OPENAI_API_KEY=YOUR_KEY")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("  LongCat API 测试")
    print("="*60)
    print(f"\nAPI Key: {args.api_key[:10]}...{args.api_key[-4:]}")
    print(f"Base URL: {args.base_url}")
    print(f"Model: {args.model}")
    
    results = {}
    
    # 执行测试
    if args.test in ("all", "openai"):
        results["OpenAI SDK"] = test_openai_sdk(args.api_key, args.base_url, args.model)
    
    if args.test in ("all", "requests"):
        results["requests POST"] = test_requests_post(args.api_key, args.base_url, args.model)
    
    if args.test in ("all", "client"):
        results["LLMClient"] = test_llm_client(args.api_key, args.base_url, args.model)
    
    # 打印总结
    print_header("测试总结")
    
    all_passed = True
    for name, passed in results.items():
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print()
    if all_passed:
        print("🎉 所有测试通过！")
        return 0
    else:
        print("⚠️  部分测试失败，请检查上面的错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())
