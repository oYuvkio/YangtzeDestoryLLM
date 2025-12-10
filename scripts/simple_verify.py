#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版快速验证脚本

避免使用 shell 的 heredoc 和 conda 命令，直接用 Python 完成所有检查
"""
import sys
import subprocess
from pathlib import Path

# ANSI 颜色代码
GREEN = '\033[0;32m'
YELLOW = '\033[1;33m'
RED = '\033[0;31m'
NC = '\033[0m'  # No Color


def print_header():
    """打印标题。"""
    print("=" * 70)
    print("  向量去重功能快速验证")
    print("=" * 70)
    print()


def check_config():
    """检查配置文件。"""
    print(f"{YELLOW}[1/4]{NC} 验证配置文件...")
    
    import yaml
    
    cfg_path = Path("configs/cfg.yaml")
    if not cfg_path.exists():
        print(f"{RED}✗ 配置文件不存在{NC}")
        return False
    
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{RED}✗ 配置文件解析失败: {e}{NC}")
        return False
    
    checks = {
        "dedup_schema.enabled": cfg.get("dedup_schema", {}).get("enabled", False),
        "dedup_schema.threshold": cfg.get("dedup_schema", {}).get("threshold", 0),
        "p4.dedup_with_embeddings": cfg.get("p4", {}).get("dedup_with_embeddings", False),
        "p4.dedup_threshold": cfg.get("p4", {}).get("dedup_threshold", 0),
        "p4.align_synonyms": cfg.get("p4", {}).get("align_synonyms", False),
    }
    
    all_ok = True
    for key, value in checks.items():
        if key.endswith("enabled") or key.endswith("embeddings") or key.endswith("synonyms"):
            if not value:
                print(f"  {RED}✗{NC} {key}: {value}")
                all_ok = False
            else:
                print(f"  {GREEN}✓{NC} {key}: {value}")
        elif key.endswith("threshold"):
            if value == 0.7:
                print(f"  {GREEN}✓{NC} {key}: {value}")
            else:
                print(f"  {YELLOW}⚠{NC} {key}: {value} (建议为 0.7)")
    
    if all_ok:
        print(f"{GREEN}✓ 配置检查通过{NC}\n")
        return True
    else:
        print(f"{RED}✗ 配置检查失败{NC}\n")
        return False


def test_dedup():
    """测试向量去重功能。"""
    print(f"{YELLOW}[2/4]{NC} 测试向量去重功能（不调用 LLM）...")
    
    try:
        result = subprocess.run(
            [sys.executable, "scripts/verify_full_pipeline.py", "--test-dedup-only"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            print(f"{GREEN}✓ 去重测试通过{NC}\n")
            return True
        else:
            print(f"{RED}✗ 去重测试失败{NC}")
            if result.stderr:
                print(f"错误信息: {result.stderr[:200]}")
            print()
            return False
            
    except subprocess.TimeoutExpired:
        print(f"{RED}✗ 去重测试超时{NC}\n")
        return False
    except Exception as e:
        print(f"{RED}✗ 去重测试异常: {e}{NC}\n")
        return False


def verify_code_structure():
    """验证代码结构。"""
    print(f"{YELLOW}[3/4]{NC} 验证代码结构...")
    
    try:
        result = subprocess.run(
            [sys.executable, "scripts/verify_full_pipeline.py", "--skip-llm", "--skip-config-check"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print(f"{GREEN}✓ 代码结构验证通过{NC}\n")
            return True
        else:
            print(f"{RED}✗ 代码结构验证失败{NC}")
            if result.stderr:
                print(f"错误信息: {result.stderr[:200]}")
            print()
            return False
            
    except Exception as e:
        print(f"{RED}✗ 代码结构验证异常: {e}{NC}\n")
        return False


def check_dependencies():
    """检查关键依赖。"""
    print(f"{YELLOW}[4/4]{NC} 检查关键依赖...")
    
    required_modules = [
        "yaml",
        "sentence_transformers",
        "numpy",
    ]
    
    missing = []
    for module in required_modules:
        try:
            __import__(module)
            print(f"  {GREEN}✓{NC} {module}")
        except ImportError:
            print(f"  {RED}✗{NC} {module} (缺失)")
            missing.append(module)
    
    if missing:
        print(f"\n{YELLOW}提示: 安装缺失模块{NC}")
        print(f"  pip install {' '.join(missing)}")
        print()
        return False
    else:
        print(f"{GREEN}✓ 依赖检查通过{NC}\n")
        return True


def print_summary(results):
    """打印总结。"""
    print("=" * 70)
    
    all_passed = all(results.values())
    
    if all_passed:
        print(f"{GREEN}✓ 所有检查通过！{NC}")
    else:
        print(f"{YELLOW}⚠ 部分检查未通过{NC}")
    
    print("=" * 70)
    print()
    
    # 显示详细结果
    for check, passed in results.items():
        status = f"{GREEN}✓{NC}" if passed else f"{RED}✗{NC}"
        print(f"  {status} {check}")
    
    print()
    
    if all_passed:
        print("📋 下一步操作建议：")
        print("  1. 运行完整流程测试（会调用 LLM）：")
        print("     python scripts/verify_full_pipeline.py")
        print()
        print("  2. 运行对比实验：")
        print("     python experiments/exp_dedup_comparison.py")
        print()
        print("  3. 运行主流程：")
        print("     python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash")
        print()


def main():
    """主函数。"""
    print_header()
    
    results = {}
    
    # 1. 配置检查
    results["配置文件验证"] = check_config()
    
    # 2. 依赖检查
    results["依赖检查"] = check_dependencies()
    
    # 3. 去重功能测试（如果依赖齐全）
    if results["依赖检查"]:
        results["去重功能测试"] = test_dedup()
    else:
        print(f"{YELLOW}⏭️  跳过去重测试（缺少依赖）{NC}\n")
        results["去重功能测试"] = False
    
    # 4. 代码结构验证
    results["代码结构验证"] = verify_code_structure()
    
    # 打印总结
    print_summary(results)
    
    # 返回状态码
    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n{YELLOW}⚠ 用户中断{NC}")
        sys.exit(130)
    except Exception as e:
        print(f"\n{RED}✗ 未预期的错误: {e}{NC}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
