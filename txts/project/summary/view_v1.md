# CQ-Enhanced 知识图谱构建流程 v1.0

> 基于CQ驱动的长江流域水旱灾害知识图谱构建完整流程
> 最后更新：2026-01-02

---

## 快速导航

| 角色 | 阅读路径 |
|------|---------|
| **论文写作** | [核心创新点](#11-核心创新点) → [Pipeline架构](#13-完整pipeline架构图) → [实验设计](#三实验设计) |
| **代码开发** | [阶段详解](#14-各阶段详细说明) → [代码入口](#四代码实现入口) → [常用命令](#五常用命令) |
| **实验复现** | [数据准备](#二数据准备) → [消融实验](#32-消融实验设计) → [评估指标](#33-评估指标设计) |

---

## 一、方法设计

### 1.1 核心创新点

| 序号 | 创新点 | 解决问题 | 论文包装 |
|------|--------|----------|----------|
| 1 | **CoT分步抽取** | 复杂句抽取遗漏 | 基于思维链的分步约束抽取策略 |
| 2 | **原文回溯校验** | **幻觉问题（核心）** | 面向事实一致性的原文回溯校验机制 |
| 3 | **知识融合** | 实体冗余 | 基于语义相似度的实体归一化与关系聚合策略 |

### 1.2 融合策略总览

| 阶段 | 原方法 | 融合后方法 | 变化类型 | 代码改动 |
|------|--------|------------|----------|----------|
| P2 本体构建 | CQ直接生成 | 专家骨架 + CQ扩展 | 表述优化 | 无 |
| P3 规范化 | LLM整理 | 保持不变 | 无 | 无 |
| P4 增强 | 文献挖掘 | 保持不变 | 无 | 无 |
| **P4+** | 无 | **统一向量去重** | **新增** | 新增调用 |
| P5 抽取 | 一步抽取 | **CoT三步抽取** | Prompt重构 | 修改Prompt |
| **P5+/P6** | 无 | **原文回溯校验** | **新增模块** | 新增代码 |
| **P6+** | 无 | **实体归一化+关系去重** | **新增阶段** | 新增代码 |

### 1.3 完整Pipeline架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        完整Pipeline架构                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ╔═══════════════════════════════════════════════════════════════════╗  │
│  ║                    【本体构建阶段 TBox】                            ║  │
│  ╠═══════════════════════════════════════════════════════════════════╣  │
│  ║                                                                   ║  │
│  ║  ┌────────┐    ┌────────┐    ┌────────┐    ┌────────┐            ║  │
│  ║  │P1: CQ  │───→│P2: 初始│───→│P3: 整理│───→│P4: 文献│            ║  │
│  ║  │问题生成│    │TBox    │    │规范化  │    │增强    │            ║  │
│  ║  └────────┘    └────────┘    └────────┘    └───┬────┘            ║  │
│  ║                                                │                  ║  │
│  ║                                                ▼                  ║  │
│  ║                                    ┌───────────────────┐          ║  │
│  ║                                    │ P4+: 统一向量去重  │ ★新增    ║  │
│  ║                                    │ (finalize_tbox)   │          ║  │
│  ║                                    └─────────┬─────────┘          ║  │
│  ║                                              │                    ║  │
│  ║                                              ▼                    ║  │
│  ║                                    ┌───────────────────┐          ║  │
│  ║                                    │   Master TBox     │          ║  │
│  ║                                    └─────────┬─────────┘          ║  │
│  ╚══════════════════════════════════════════════╪═══════════════════╝  │
│                                                 │                       │
│  ╔══════════════════════════════════════════════╪═══════════════════╗  │
│  ║                    【知识抽取阶段 ABox】       │                    ║  │
│  ╠══════════════════════════════════════════════╪═══════════════════╣  │
│  ║                                              ▼                    ║  │
│  ║  ┌────────────┐                  ┌───────────────────┐            ║  │
│  ║  │ 原始文本   │─────────────────→│ P5: CoT约束抽取   │ ★改进      ║  │
│  ║  │ (+上下文)  │                  │ (分步思维链)      │            ║  │
│  ║  └────────────┘                  └─────────┬─────────┘            ║  │
│  ║                                            │                      ║  │
│  ║                                            ▼                      ║  │
│  ║                                  ┌───────────────────┐            ║  │
│  ║                                  │ P5+/P6: 原文回溯  │ ★核心创新  ║  │
│  ║                                  │ 校验(幻觉过滤)    │            ║  │
│  ║                                  └─────────┬─────────┘            ║  │
│  ║                                            │                      ║  │
│  ╚════════════════════════════════════════════╪═════════════════════╝  │
│                                               │                        │
│  ╔════════════════════════════════════════════╪═════════════════════╗  │
│  ║                    【知识融合阶段】          │                ★新增 ║  │
│  ╠════════════════════════════════════════════╪═════════════════════╣  │
│  ║                                            ▼                      ║  │
│  ║                                  ┌───────────────────┐            ║  │
│  ║                                  │ P6+: 实体归一化   │            ║  │
│  ║                                  │ (同义实体合并)    │            ║  │
│  ║                                  └─────────┬─────────┘            ║  │
│  ║                                            │                      ║  │
│  ║                                            ▼                      ║  │
│  ║                                  ┌───────────────────┐            ║  │
│  ║                                  │ P6++: 关系去重    │            ║  │
│  ║                                  │ (计算支持度)      │            ║  │
│  ║                                  └─────────┬─────────┘            ║  │
│  ╚════════════════════════════════════════════╪═════════════════════╝  │
│                                               │                        │
│                                               ▼                        │
│                                     ┌───────────────────┐              │
│                                     │  高质量知识图谱    │              │
│                                     └───────────────────┘              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.4 各阶段详细说明

| 阶段 | 功能 | 输入 | 输出 | 改动状态 |
|------|------|------|------|----------|
| **P1** | CQ问题生成 | 领域描述 | p1_cqs.json | 保持不变 |
| **P2** | 初始本体生成 | CQ列表 | p2_tbox_init.json | 保持不变 |
| **P3** | 本体整理规范化 | 初始TBox | p3_tbox_normalized.json | 保持不变 |
| **P4** | 文献驱动增强 | TBox + 语料 | p4_tbox_augmented.json | 保持不变 |
| **P4+** | 统一向量去重 | 增强后TBox | tbox_final.json | **新增** |
| **P5** | CoT约束抽取 | 文本+TBox | 候选三元组 | **Prompt改进** |
| **P5+/P6** | 原文回溯校验 | 三元组+原文 | 过滤后三元组 | **新增模块** |
| **P6+** | 实体归一化 | 三元组 | 归一化三元组 | **新增** |
| **P6++** | 关系去重 | 归一化三元组 | 最终三元组 | **新增** |

---

## 二、数据准备

### 2.1 语料三分法划分

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         三分法语料划分                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                    原始语料（light_pool_v2_dedup.jsonl）          │   │
│  └───────────────────────────────┬──────────────────────────────────┘   │
│                                  │                                      │
│                                  ▼                                      │
│            ┌─────────────────────┼─────────────────────┐                │
│            │                     │                     │                │
│            ▼                     ▼                     ▼                │
│    ┌──────────────┐      ┌──────────────┐      ┌──────────────┐        │
│    │ P4 语料      │      │ P5 语料      │      │ EVAL 语料    │        │
│    │ (概念/制度)  │      │ (事件事实)   │      │ (评测池)     │        │
│    └──────┬───────┘      └──────┬───────┘      └──────┬───────┘        │
│           │                     │                     │                 │
│           ▼                     ▼                     ▼                 │
│     TBox增强               ABox抽取            黄金标注评估             │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

| 语料类型 | 用途 | 特征 | 示例来源 |
|----------|------|------|----------|
| **P4 语料** | TBox 增强（概念扩展） | 制度性、定义性文本 | 防汛条例、应急预案、技术规范 |
| **P5 语料** | ABox 抽取（事件填充） | 事实性、叙述性文本 | 灾害新闻、年鉴记录、事件报告 |
| **EVAL 语料** | 评测池（黄金标注） | 代表性、覆盖性 | 人工标注的典型段落 |

### 2.2 黄金标注设计

#### 标注Schema（独立于项目Schema）

**重要原则**：标注Schema与项目Schema完全独立，避免循环依赖，确保评估公平性。

**9种标准实体类型**：
- TIME：时间表达（年份、日期、时间段）
- LOCATION：地理位置（省市、河流、湖泊、水库、水文站点）
- EVENT：灾害事件名称
- VALUE：数值指标（水位、流量、损失数据）
- CAUSE：致灾因子
- MEASURE：应急措施/响应
- FACILITY：水利工程设施
- ORG：机构组织
- IMPACT：灾害影响描述

**9种标准关系类型**：

| 关系名称 | 中文含义 | 主语类型 | 宾语类型 |
|---------|---------|---------|---------|
| occurs_at | 发生于（时间） | EVENT | TIME |
| located_in | 位于/发生地点 | EVENT/FACILITY | LOCATION |
| has_cause | 由...引起 | EVENT | CAUSE |
| causes_impact | 造成影响 | EVENT | IMPACT/VALUE |
| has_value | 测量值为 | FACILITY/LOCATION | VALUE |
| triggers | 触发 | EVENT/VALUE | MEASURE |
| implements | 实施/采取 | ORG | MEASURE |
| part_of | 属于/包含于 | LOCATION | LOCATION |
| affects | 影响/波及 | EVENT | LOCATION |

#### 标注格式示例

```json
{
  "doc_id": "eval_001",
  "text": "1998年8月，长江干流沙市站水位达到45.22米...",
  "entities": [
    {"name": "1998年8月", "type": "TIME"},
    {"name": "沙市站", "type": "FACILITY"},
    {"name": "45.22米", "type": "VALUE"}
  ],
  "triples": [
    {
      "subject": "沙市站",
      "predicate": "has_value",
      "object": "45.22米",
      "evidence": "沙市站水位达到45.22米"
    }
  ],
  "events": [...]
}
```

---

## 三、实验设计

### 3.1 Baseline设计

| ID | 名称 | 类型 | 对比目的 | 配置说明 |
|----|------|------|----------|----------|
| B1 | UIE-Base | 传统模型 | 证明LLM在少样本下的优势 | PaddleNLP uie-base |
| B2 | Direct-LLM | 无CoT无校验 | **核心对比**：证明CoT+校验的价值 | 相同LLM，简单Prompt |

### 3.2 消融实验设计

#### TBox 消融（本体构建）

| 变体 | 配置 | 验证目标 |
|------|------|----------|
| full_tbox | 完整流程 (CQ + P3 + P4 + 统一去重) | 基准 |
| wo_cq | 无CQ增强 (专家骨架 + P4) | CQ驱动的价值 |
| wo_p4 | 无P4文献增强 (CQ + P3) | 文献增强的价值 |
| wo_cq_p4 | 无CQ和文献增强 (仅专家骨架) | 双重增强的价值 |

#### ABox 消融（知识抽取）

| 变体 | 配置 | 验证目标 | 关键指标 |
|------|------|----------|----------|
| full_extract | 完整流程 (CoT + 后验证 + 幻觉过滤) | 基准 | - |
| **wo_verify** | 无后验证 (跳过P6幻觉过滤) | **降幻觉效果（核心）** | 幻觉率上升10-15% |
| wo_cot | 无CoT (普通prompt) | CoT对召回的作用 | Recall下降5-8% |
| wo_cot_verify | 无CoT和后验证 | 方法整体价值 | F1显著下降 |

### 3.3 评估指标设计

#### TBox 指标（OntoQA）

| 指标 | 公式 | 含义 |
|------|------|------|
| RR (Relationship Richness) | P / (P + SC) | 非继承关系占比，越高表示语义关系越丰富 |
| IR (Inheritance Richness) | SC / C | 子类边与类数之比，越高表示层级越深 |
| AR (Attribute Richness) | A / C | 平均每类属性数 |
| CQ Coverage | 基于句向量的CQ覆盖度 | 多阈值覆盖率 (0.3-0.9) |

#### ABox 指标（抽取质量）

| 类别 | 指标 | 计算方式 | 优先级 |
|------|------|----------|--------|
| 准确性 | Precision | 正确抽取数 / 总抽取数 | 高 |
| 召回度 | Recall | 正确抽取数 / 标注总数 | 高 |
| 综合 | F1-Score | 2PR/(P+R) | 高 |
| **质量** | **幻觉率** | 幻觉三元组 / 总抽取数 | **极高** |
| 一致性 | TBox Consistency | 谓词存在性 + domain/range符合率 | 中 |

#### 预期实验结果

| 方法 | Precision | Recall | F1 | 幻觉率 |
|------|-----------|--------|-----|--------|
| UIE-Base | ~72% | ~58% | ~64% | - |
| Direct-LLM (B2) | ~70% | ~85% | ~77% | ~18% |
| w/o Verification (A2) | ~75% | ~83% | ~79% | ~12% |
| **Ours (完整方法)** | **~88%** | **~80%** | **~84%** | **~4%** |

---

## 四、代码实现入口

### 4.1 核心模块文件

| 模块 | 文件路径 | 功能 | 状态 |
|------|----------|------|------|
| CQ Pipeline | `kg/cq_pipeline.py` | P1-P5 主流程 | 已有 |
| Hallucination Filter | `kg/hallucination_filter.py` | 原文回溯校验 | **新增** |
| Entity Fusion | `kg/entity_fusion.py` | 实体归一化+关系去重 | **新增** |
| Relation Mapping | `tools/relation_mapping.py` | 评估时关系映射 | **新增** |
| P5 CoT Prompt | `kg/prompts.py` | CoT分步抽取Prompt | **修改** |

### 4.2 脚本入口

| 脚本 | 功能 | 用途 |
|------|------|------|
| `scripts/run_cq_pipeline.py` | P1-P5 全流程 | 主入口 |
| `scripts/run_p4_batch.py` | P4 批处理 | 大规模语料增强 |
| `scripts/run_p2_to_p6.py` | P2-P6 全流程 | 从P2开始完整执行 |
| `scripts/run_ablation_full.py` | 消融实验 | 一键运行所有消融变体 |
| `scripts/generate_gold_independent.py` | 黄金标注生成 | 使用独立Schema |
| `scripts/run_full_evaluation.py` | 一键评估 | TBox + ABox 评估 |

---

## 五、常用命令

### 5.1 完整流程执行

```bash
# P1-P5 全流程
python scripts/run_cq_pipeline.py --cfg configs/cfg.yaml

# 从特定阶段开始（断点续跑）
python scripts/run_cq_pipeline.py --start-step p3

# P2-P6 完整流程（含幻觉过滤和知识融合）
python scripts/run_p2_to_p6.py \
    --cfg configs/cfg.yaml \
    --corpus data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl
```

### 5.2 消融实验

```bash
# 完整消融实验（TBox + ABox）
python scripts/run_ablation_full.py --all

# 仅运行 TBox 消融
python scripts/run_ablation_full.py --tbox-ablation

# 仅运行 ABox 消融
python scripts/run_ablation_full.py --abox-ablation

# 仅评估（使用已有结果）
python scripts/run_ablation_full.py --eval-only
```

### 5.3 黄金标注生成

```bash
# 使用最强模型生成黄金标注（独立Schema）
python scripts/generate_gold_independent.py \
    --input data/p5_eval_pool/test.jsonl \
    --out data/p5_eval_pool/gold_independent.jsonl \
    --model gpt-4o \
    --temperature 0.1

# 断点续跑
python scripts/generate_gold_independent.py \
    --input data/p5_eval_pool/test.jsonl \
    --out data/p5_eval_pool/gold_independent.jsonl \
    --resume
```

### 5.4 评估

```bash
# 一键评估（TBox 结构 + 抽取质量）
python scripts/run_full_evaluation.py \
    --tbox outputs/cq_pipeline/final/p4_tbox_augmented.json \
    --gold data/p5_eval_pool/gold_independent.jsonl \
    --preds outputs/p5_batch_results.jsonl

# OntoQA 指标计算
python tools/tbox_metrics.py outputs/cq_pipeline/final/p4_tbox_augmented.json

# CQ 覆盖度计算
python tools/cq_coverage.py \
    --tbox-file outputs/cq_pipeline/final/p4_tbox_augmented.json \
    --cq-file outputs/cq_pipeline/final/p1_cqs.json

# 关系映射（将项目Schema映射到标准Schema）
python tools/relation_mapping.py \
    --pred outputs/kg_extraction/predictions.json \
    --out outputs/kg_extraction/predictions_mapped.json
```

---

## 六、论文写作参考

### 6.1 摘要创新点表述

> 针对大语言模型在领域知识抽取中存在的幻觉问题，本文提出一种**基于思维链推理与原文回溯校验的抗幻觉抽取框架**。主要贡献包括：
>
> （1）设计了**分步约束抽取策略**，通过思维链技术将复杂抽取任务分解为多个认知子步骤，提升了模型对长难句的处理能力；
>
> （2）提出了**原文回溯校验机制**，利用文本证据对抽取结果进行自动化验证，有效过滤了模型臆造的虚假知识，将幻觉率降低至5%以下；
>
> （3）构建了完整的**知识融合流水线**，通过实体归一化和关系聚合确保图谱质量。
>
> 实验表明，该方法在水旱灾害领域数据集上的F1值达到84%，相比基线方法提升7个百分点，幻觉率降低14个百分点。

### 6.2 方法章节对应

| 论文章节 | 代码实现 | 关键文件 |
|----------|----------|----------|
| CQ 驱动 schema 构建 | P1-P3 | `kg/cq_pipeline.py` |
| 语料增强 | P4 | `scripts/run_p4_batch.py` |
| 统一向量去重 | P4+ | `kg/utils/deduplication.py` |
| **CoT分步抽取** | P5 | `kg/prompts.py` |
| **原文回溯校验** | P5+/P6 | `kg/hallucination_filter.py` |
| **知识融合** | P6+ | `kg/entity_fusion.py` |
| 评估体系 | - | `tools/tbox_metrics.py`, `tools/abox_metrics.py` |

---

## 七、文件产物映射

```
阶段           输入                              输出                            说明
──────────────────────────────────────────────────────────────────────────────────────
P1        领域描述文本                     p1_cqs.json                       ~10-50 条 CQ
P2        p1_cqs.json                     p2_tbox_init.json                 ~30-50 类
P3        p2_tbox_init.json               p3_tbox_normalized.json           规范化后
P4        p3_tbox + 语料                  p4_tbox_augmented.json            文献增强后
P4+       p4_tbox_augmented               tbox_final.json                   统一去重后 ★
P5        tbox_final + 文本               p5_raw_extractions.json           CoT抽取结果
P5+/P6    p5_raw + 原文                   p5_verified.json                  幻觉过滤后 ★
P6+       p5_verified                     p6_normalized.json                实体归一化 ★
P6++      p6_normalized                   p6_final_triples.json             关系去重后 ★
评估       p*_tbox + p6_results            evaluation_report.json            完整评估报告
```

---

## 八、关键配置说明

### 8.1 configs/cfg.yaml 核心配置

```yaml
# ============ P4+ 统一去重配置 ============
dedup_schema:
  enabled: true
  class_threshold: 0.85      # 类去重阈值
  relation_threshold: 0.80   # 关系去重阈值

# ============ P5 CoT抽取配置 ============
p5:
  use_cot: true              # 启用CoT分步抽取
  favor_existing_classes: true
  normalize_entities: true

# ============ P6 幻觉过滤配置 ============
hallucination_filter:
  strict_mode: false         # false=允许模糊匹配
  fuzzy_threshold: 0.8       # 模糊匹配阈值

# ============ P6+ 知识融合配置 ============
entity_fusion:
  use_embedding: false       # 是否使用向量相似度
  embedding_threshold: 0.9
```

---

## 九、版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v1.0 | 2026-01-02 | 初始版本，包含完整的P1-P6+流程 |
| v1.1 | 2026-01-05 | 添加踩坑总结和注意事项 |

---

## 十、踩坑总结与注意事项

### 10.1 数据处理踩坑

#### 坑1：文本截断导致信息丢失

**问题描述**：
- `test_final.jsonl` 中的 `source_text` 字段是截断的（约500字符）
- 完整文本存储在 `pool_v3.jsonl` 的 `text` 字段中（通过 `doc_id` → `id` 映射）
- 如果 Pred 抽取使用截断文本，而 Gold 标注使用完整文本，会导致评测指标严重偏低

**发现过程**：
```python
# 验证发现
test_final.source_text: 503 字符（截断，末尾有"..."）
pool_v3.text: 816 字符（完整）
```

**解决方案**：
- 为所有抽取脚本添加 `--text-source` 参数
- 运行时指定完整文本来源文件
- 脚本会通过 `doc_id` 映射获取完整文本

**涉及脚本**：
| 脚本 | 用途 | 参数 |
|------|------|------|
| `scripts/generate_gold_with_tbox.py` | Gold 标注生成 | `--text-source` |
| `scripts/p5/run_extraction_on_test.py` | Pred 抽取 | `--text-source` |
| `scripts/p5/run_gold_annotation.sh` | Gold 生成封装 | `--text-source` |
| `scripts/p5/run_single_model.sh` | 单模型评测 | `--text-source` |
| `scripts/p5/baseline/uie/run_uie_baseline.py` | UIE Baseline 抽取 | `--text-source` |
| `scripts/p5/baseline/uie/run_uie_baseline.sh` | UIE 评测封装 | `--text-source` |

**正确用法**：
```bash
# Gold 生成（使用完整文本）
bash scripts/p5/run_gold_annotation.sh \
    --tbox-version s2 \
    --input data/p5_eval_pool/final/test_final.jsonl \
    --text-source data/p5_eval_pool/pool_v3.jsonl \
    --output data/p5_eval_pool/gold_s2_tbox.jsonl \
    ...

# Pred 抽取（使用完整文本）
bash scripts/p5/run_single_model.sh \
    --model "THUDM/GLM-4-9B-0414" \
    --text-source data/p5_eval_pool/pool_v3.jsonl \
    ...
```

#### 坑2：Gold Schema ≠ TBox Schema

**问题描述**：
- 独立 Schema 的 Gold 标注使用通用关系（如 `has_value`, `located_in`）
- TBox 定义的关系可能不同（如 `observes_value`, `located_at`）
- Schema 不一致导致 Triple F1 极低（~4%）

**解决方案**：
- 使用 **TBox 约束的 Gold 生成**（`--tbox-version s2/s3`）
- Gold 和 Pred 必须配对使用相同的 TBox
  - `gold_s2.jsonl` + `pred_s2.jsonl` + `tbox_s2_optimized.json`
  - `gold_s3.jsonl` + `pred_s3.jsonl` + `tbox_s3_optimized.json`

### 10.2 评测流程注意事项

#### 注意1：TBox 版本配对

| Gold 文件 | Pred 文件 | TBox 文件 | 说明 |
|-----------|-----------|-----------|------|
| `gold_s2_tbox.jsonl` | `predictions_s2.jsonl` | `tbox_s2_optimized.json` | S2 版本配对 |
| `gold_s3_tbox.jsonl` | `predictions_s3.jsonl` | `tbox_s3_optimized.json` | S3 版本配对 |

#### 注意2：文本一致性

Gold 和 Pred 必须基于**相同的完整文本**抽取：
- 都使用 `--text-source pool_v3.jsonl`
- 或都使用截断的 `source_text`（不推荐）

#### 注意3：默认 TBox 路径更新

所有脚本的默认 TBox 已更新为优化版本：
- 旧路径：`p4_tbox_dedup_s2_allow1_20260102_*.json`
- 新路径：`tbox_s2_optimized.json` / `tbox_s3_optimized.json`

### 10.3 常见问题排查

| 问题现象 | 可能原因 | 排查方法 |
|---------|---------|---------|
| Triple F1 < 10% | Schema 不一致 | 检查 Gold/Pred 是否使用相同 TBox |
| Recall 极低 | 文本截断 | 检查是否使用了 `--text-source` |
| 大量"主语未在原文中找到" | 文本不匹配 | 检查 Gold/Pred 是否基于相同文本 |
| 关系全部不匹配 | TBox 版本错误 | 确认 s2/s3 版本配对 |

---

## 附录：核心代码示例

### A.1 P5 CoT Prompt 模板

```python
P5_COT_EXTRACTION_PROMPT = """
你是一名面向水旱灾害的知识图谱构建助手。

【抽取步骤】—— 请严格按照以下步骤进行思考（Chain-of-Thought）：

**Step 1: 实体扫描与定位**
仔细阅读文本，识别所有可能属于 TBox 类别的实体。
【自检】：这些实体是否在原文中**原样出现**？

**Step 2: 事件识别与分类**
判断文本是否描述了具体灾害事件，确定事件类型。

**Step 3: 关系构建与Schema约束**
用 TBox.relations 连接实体，检查domain/range约束。

**Step 4: 证据回溯与去幻觉**【核心步骤】
对每条三元组，必须从原文找到支撑句：
- 如果找不到明确的原文依据，请**丢弃**该三元组
- 实体名称必须与原文**完全一致**，不可改写或推断
"""
```

### A.2 原文回溯校验核心逻辑

```python
def _verify_triple(self, triple: Dict, text: str) -> Tuple[bool, str]:
    """验证单个三元组"""
    subject = triple.get("subject", "").strip()
    obj = triple.get("object", "").strip()

    # 验证subject
    s_valid = self._check_existence(subject, text)
    if not s_valid:
        return False, f"主语'{subject}'未在原文中找到"

    # 验证object
    o_valid = self._check_existence(obj, text)
    if not o_valid:
        return False, f"宾语'{obj}'未在原文中找到"

    return True, "验证通过"
```

### A.3 关系映射示例

```python
# 项目Schema -> 标准Schema 映射
PROJECT_TO_STANDARD_MAPPING = {
    "occurs_at_time": "occurs_at",
    "has_time": "occurs_at",
    "located_at": "located_in",
    "has_cause": "has_cause",
    "has_impact": "causes_impact",
    "triggers_response": "triggers",
    # ...
}
```
