目标：严格使用 manifest 过滤后的 p4_only.jsonl 进行模式扩展；增强后再次去重，产出最终 TBox。


任务：完善 P4 增强流水线，限制输入为 p4_only.jsonl；输出 suggestions 与增强后 TBox，并对增强结果再次去重。

[改动点]
1) 修改/新增 kg/cq_pipeline.py 的 P4 阶段函数：
   - 函数签名：p4_suggest(in_tbox, corpus_jsonl, out_suggestions, log_file, seed)
   - 行为：从 p4_only.jsonl 中抽取“概念性句子”，分类为候选类/关系/属性；生成 JSONL suggestions（含 provenance）
   - 提示：用已有 prompts.py 的 P4_AUGMENT_PROMPT；温度 0.1；每段落最多生成 N<=5 个建议；同段内消重
2) 新增工具 kg/apply_p4.py：
   - 输入：--in-tbox, --suggestions
   - 输出：p4_tbox_enhanced_raw.json
   - 规则：同名合并、冲突（domain/range）进入冲突队列（输出 conflict_report.json）
3) 复用 Prompt 2 的 dedup 工具对 p4_tbox_enhanced_raw.json 再去重，得 p4_tbox_enhanced.json

[CLI]
python kg/cq_pipeline.py --stage p4_suggest \
  --in-tbox outputs/cq_pipeline/final/p3_tbox_dedup_final.json \
  --corpus data/corpus_for_onto/p4_only.jsonl \
  --out-suggestions data/p4_suggestions.jsonl \
  --log-file logs/kg_p4/p4_suggest.log \
  --seed 42

python kg/apply_p4.py \
  --in-tbox outputs/cq_pipeline/final/p3_tbox_dedup_final.json \
  --suggestions data/p4_suggestions.jsonl \
  --out-tbox outputs/cq_pipeline/final/p4_tbox_enhanced_raw.json \
  --conflict-report outputs/ontoqa/p4_conflicts.json \
  --log-file logs/kg_p4/p4_apply.log

python tools/tbox_dedup.py dedup \
  --in-tbox outputs/cq_pipeline/final/p4_tbox_enhanced_raw.json \
  --out-tbox outputs/cq_pipeline/final/p4_tbox_enhanced.json \
  --model text-embedding-3-large --sim-th 0.7 \
  --log-file logs/kg_tbox/dedup_p4.log

[验收标准]
- p4_suggestions.jsonl 每条含：type, name, cn_name, definition, domain, range, evidence_span, doc_id, rel_path, year
- 冲突报告统计：签名冲突计数、父类冲突计数、需人工处理清单
- 最终 TBox 导出成功


##以下是一部分参考代码
kg/p4_suggest.py - P4 建议生成模块
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P4 阶段：从概念性语料中提取 TBox 扩展建议。

功能：
- 从 p4_only.jsonl 中抽取概念性句子
- 使用 LLM 生成候选类/关系/属性建议
- 输出带 provenance 的 suggestions JSONL

使用示例：
    python kg/p4_suggest.py \\
        --in-tbox outputs/cq_pipeline/final/p3_tbox_dedup_final.json \\
        --corpus data/corpus_for_onto/p4_only.jsonl \\
        --out-suggestions data/p4_suggestions.jsonl \\
        --log-file logs/kg_p4/p4_suggest.log \\
        --seed 42
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Set, Tuple

# ==============================================================================
# 项目路径配置
# ==============================================================================
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    yaml = None
    YAML_AVAILABLE = False

# ==============================================================================
# LLM 模块导入
# ==============================================================================
try:
    from kg.llm_core import LLMFactory
    LLM_AVAILABLE = True
except ImportError:
    LLMFactory = None
    LLM_AVAILABLE = False

try:
    from kg.prompts import P4_AUGMENT_SYSTEM, P4_AUGMENT_USER_TEMPLATE
    PROMPTS_AVAILABLE = True
except ImportError:
    PROMPTS_AVAILABLE = False
    # 回退 Prompt
    P4_AUGMENT_SYSTEM = """你是一个本体工程专家，负责从领域文本中提取概念、关系和属性定义。

任务：分析给定的概念性文本，提取可以扩展现有本体的新元素。

输出要求（JSON 格式）：
{
  "suggestions": [
    {
      "type": "class|relation|attribute",
      "name": "英文名称（驼峰命名）",
      "cn_name": "中文名称",
      "definition": "定义描述",
      "parent": "父类名称（仅 class 类型）",
      "domain": "定义域（仅 relation 类型）",
      "range": "值域（仅 relation 类型）",
      "owner": "所属类（仅 attribute 类型）",
      "value_type": "值类型（仅 attribute 类型）",
      "evidence_span": "原文依据（摘录）"
    }
  ]
}

注意：
1. 只提取明确定义的概念，不要推测
2. 优先使用已有本体中的类作为 parent/domain/range/owner
3. 每段文本最多提取 5 个建议
4. evidence_span 必须是原文的直接摘录"""

    P4_AUGMENT_USER_TEMPLATE = """## 现有本体概要

### 已有类
{existing_classes}

### 已有关系
{existing_relations}

### 已有属性
{existing_attributes}

## 待分析文本

来源：{doc_title}
年份：{year}

{text}

---

请分析上述文本，提取可以扩展本体的新概念、关系或属性。"""
