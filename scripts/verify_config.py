#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
配置文件验证脚本（无需临时文件）

用于替代 quick_verify.sh 中的 heredoc 部分
"""
import sys
from pathlib import Path
import yaml

def main():
    """验证配置文件是否符合论文要求。"""
    cfg_path = Path("configs/cfg.yaml")
    
    if not cfg_path.exists():
        print("✗ 配置文件不存在")
        return 1
    
    try:
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"✗ 配置文件解析失败: {e}")
        return 1
    
    # 检查关键配置
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
                print(f"✗ {key}: {value}")
                all_ok = False
            else:
                print(f"✓ {key}: {value}")
        elif key.endswith("threshold"):
            if value == 0.7:
                print(f"✓ {key}: {value}")
            else:
                print(f"⚠ {key}: {value} (建议为 0.7)")
    
    if all_ok:
        print("\n✓ 配置文件符合论文要求")
        return 0
    else:
        print("\n✗ 配置文件存在问题，请检查")
        return 1


if __name__ == "__main__":
    sys.exit(main())
