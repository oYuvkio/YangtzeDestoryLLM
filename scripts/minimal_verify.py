#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
最小化验证脚本 - 仅检查配置文件

不需要任何额外依赖，只验证核心配置
"""
import sys
from pathlib import Path

# ANSI 颜色
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'


def main():
    print("=" * 70)
    print("  配置文件快速验证")
    print("=" * 70)
    print()
    
    # 检查 YAML 是否可用
    try:
        import yaml
    except ImportError:
        print(f"{RED}✗ PyYAML 未安装，无法继续{NC}")
        print("  请运行: pip install pyyaml")
        return 1
    
    # 读取配置
    cfg_path = Path("configs/cfg.yaml")
    if not cfg_path.exists():
        print(f"{RED}✗ 配置文件不存在: {cfg_path}{NC}")
        return 1
    
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{RED}✗ 配置文件解析失败: {e}{NC}")
        return 1
    
    print(f"{GREEN}✓ 配置文件加载成功{NC}\n")
    
    # 检查关键配置
    print("检查向量去重相关配置：")
    print("-" * 70)
    
    checks = [
        ("P2/P3 去重启用", "dedup_schema.enabled", True),
        ("P2/P3 去重阈值", "dedup_schema.threshold", 0.7),
        ("P4 去重启用", "p4.dedup_with_embeddings", True),
        ("P4 去重阈值", "p4.dedup_threshold", 0.7),
        ("P4 同义词对齐", "p4.align_synonyms", True),
    ]
    
    all_ok = True
    
    for desc, key, expected in checks:
        parts = key.split(".")
        value = cfg
        for part in parts:
            value = value.get(part, {})
        
        if value == expected:
            print(f"  {GREEN}✓{NC} {desc:20s}: {value}")
        else:
            print(f"  {RED}✗{NC} {desc:20s}: {value} (期望: {expected})")
            all_ok = False
    
    print("-" * 70)
    print()
    
    # 显示其他关键配置
    print("其他配置信息：")
    print("-" * 70)
    
    embedding_model = cfg.get("embedding", {}).get("model_name", "未设置")
    print(f"  Embedding 模型: {embedding_model}")
    
    llm_model = cfg.get("llm", {}).get("model_name", "未设置")
    print(f"  LLM 模型: {llm_model}")
    
    output_dir = cfg.get("paths", {}).get("output_dir", "未设置")
    print(f"  输出目录: {output_dir}")
    
    print("-" * 70)
    print()
    
    # 总结
    if all_ok:
        print(f"{GREEN}{'='*70}")
        print(f"  ✓ 所有配置检查通过！")
        print(f"{'='*70}{NC}")
        print()
        print("✅ 您的配置已与论文要求对齐：")
        print("   - 向量去重已启用（P2/P3/P4 阶段）")
        print("   - 阈值设置为 0.7（论文推荐值）")
        print("   - 同义词对齐已启用")
        print()
        print("📝 下一步建议：")
        print("   1. 安装依赖: pip install sentence-transformers")
        print("   2. 运行验证: python scripts/verify_full_pipeline.py --test-dedup-only")
        print("   3. 完整测试: python scripts/verify_full_pipeline.py")
        print()
        return 0
    else:
        print(f"{YELLOW}{'='*70}")
        print(f"  ⚠ 部分配置不符合要求")
        print(f"{'='*70}{NC}")
        print()
        print("请检查配置文件: configs/cfg.yaml")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
