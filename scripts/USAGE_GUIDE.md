# 向量去重功能使用指南

## 📋 概述

本指南说明如何使用和验证项目中的向量去重功能，确保 KG 构建流程与论文保持一致。

## ✅ 已完成的配置修改

### 1. 配置文件已更新 (`configs/cfg.yaml`)

```yaml
# P2/P3 阶段去重
dedup_schema:
  enabled: true      # ✅ 已启用
  threshold: 0.7     # ✅ 调整为论文推荐值

# P4 阶段去重
p4:
  align_synonyms: true           # ✅ 启用同义词对齐
  dedup_with_embeddings: true    # ✅ 启用向量去重
  dedup_threshold: 0.7           # ✅ 统一阈值
```

### 2. 关键变更说明

| 配置项 | 原值 | 新值 | 说明 |
|--------|------|------|------|
| `dedup_schema.enabled` | `false` | `true` | 启用 P2/P3 去重 |
| `dedup_schema.threshold` | `0.75` | `0.7` | 与论文对齐 |
| `p4.align_synonyms` | `false` | `true` | 启用同义词对齐 |
| `p4.dedup_with_embeddings` | `false` | `true` | 启用 P4 去重 |
| `p4.dedup_threshold` | `0.8` | `0.7` | 统一阈值 |

## 🚀 使用方法

### 方法1: 完整流程验证

运行端到端验证脚本：

```bash
# 激活环境
conda activate YangtzeLLM

# 完整流程测试（会调用 LLM）
python scripts/verify_full_pipeline.py

# 仅测试去重功能（不调用 LLM）
python scripts/verify_full_pipeline.py --test-dedup-only

# 跳过 LLM 调用（仅验证代码结构）
python scripts/verify_full_pipeline.py --skip-llm
```

**输出示例**：
```
🚀 CQ 驱动 KG 构建流程验证工具
======================================================================

============================================================
  验证配置文件
============================================================

📋 配置检查结果：
  ✅ dedup_schema.enabled: True
  ✅ dedup_schema.threshold: 0.7
  ✅ p4.dedup_with_embeddings: True
  ✅ p4.dedup_threshold: 0.7
  ✅ p4.align_synonyms: True

✅ 配置文件符合论文要求！
```

### 方法2: 运行对比实验

对比不同去重策略的效果：

```bash
# 完整对比实验
python experiments/exp_dedup_comparison.py

# 使用已有 TBox
python experiments/exp_dedup_comparison.py --input-tbox outputs/p2_tbox_init.json

# 查看已有结果
python experiments/exp_dedup_comparison.py --report-only
```

**实验会对比**：
- Baseline（无去重）
- 阈值 0.7（论文推荐）
- 阈值 0.75（保守）
- 阈值 0.8（严格）

**评估指标**：
- TBox 规模（类、关系、属性数量）
- OntoQA 指标（RR、IR、AR）
- 去重效果（保留率、重复率）

### 方法3: 在主流程中使用

在运行主流程时，去重会自动生效：

```bash
# P1-P5 完整流程（去重已启用）
python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash

# 如需临时禁用去重
python scripts/run_cq_pipeline.py --dedup-schema false

# 如需调整阈值
python scripts/run_cq_pipeline.py --dedup-threshold 0.75
```

## 📊 验证检查清单

运行以下命令确保一切正常：

```bash
# 1. 检查配置
cat configs/cfg.yaml | grep -A 3 "dedup_schema"
cat configs/cfg.yaml | grep -A 5 "^p4:"

# 2. 快速验证（不调用 LLM）
python scripts/verify_full_pipeline.py --test-dedup-only

# 3. 完整流程测试
python scripts/verify_full_pipeline.py --skip-llm
```

**预期输出**：
- ✅ 所有配置项显示为 `true` 或 `0.7`
- ✅ 去重测试显示正确过滤重复类
- ✅ 流程验证显示所有阶段成功

## 🔧 故障排查

### 问题1: 导入错误

```
ModuleNotFoundError: No module named 'sentence_transformers'
```

**解决方案**：
```bash
conda activate YangtzeLLM
pip install sentence-transformers
```

### 问题2: 模型下载失败

```
HuggingFaceError: Cannot download model 'BAAI/bge-base-zh-v1.5'
```

**解决方案**：
```bash
# 设置镜像
export HF_ENDPOINT=https://hf-mirror.com
# 或手动下载模型到本地
```

### 问题3: 配置未生效

**解决方案**：
```bash
# 检查配置文件
python -c "import yaml; print(yaml.safe_load(open('configs/cfg.yaml'))['dedup_schema'])"

# 确认输出: {'enabled': True, 'threshold': 0.7}
```

## 📈 论文撰写建议

### 消融实验章节

使用对比实验结果：

```bash
# 生成对比数据
python experiments/exp_dedup_comparison.py
```

**可用于论文的内容**：
1. 表格：不同去重策略下的 TBox 规模对比
2. 图表：阈值对保留率和 OntoQA 指标的影响
3. 分析：被去重的类/关系示例及合理性分析

### 方法章节

引用验证报告中的数据：

```bash
# 查看验证报告
cat outputs/verify_pipeline/verification_report.json
```

**可引用的指标**：
- P2 去重前后的类数量对比
- 去重耗时（证明效率）
- 保留率（证明不会过度过滤）

## 📁 相关文件

- **配置文件**: `configs/cfg.yaml`
- **去重模块**: `kg/utils/deduplication.py`
- **验证脚本**: `scripts/verify_full_pipeline.py`
- **对比实验**: `experiments/exp_dedup_comparison.py`
- **主流程**: `scripts/run_cq_pipeline.py`

## 🎯 下一步

1. ✅ 配置已更新
2. ✅ 验证脚本已创建
3. ✅ 对比实验已创建
4. 🔄 运行完整流程测试
5. 📊 收集实验数据用于论文

---

**最后更新**: 2025-12-10
**状态**: ✅ 已完成配置和脚本准备
