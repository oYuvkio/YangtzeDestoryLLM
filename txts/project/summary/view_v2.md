# Hybrid + Graph-CoT 知识图谱构建流程 v2.0

> 基于专家引导 + 聚类混合本体构建，图结构提示的链式 CoT 抽取 + 双重校验
> 最后更新：2026-01-10

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
| 1 | **专家引导 + 聚类混合本体** | CQ 驱动噪声与覆盖不足 | 领域先验与数据驱动的混合本体构建 |
| 2 | **支持度/置信度筛选** | 聚类噪声、弱关联 | 面向质量约束的概念与关系筛选机制 |
| 3 | **图结构 CoT 抽取** | 复杂文本漏抽 | 图结构驱动的链式推理抽取 |
| 4 | **双重校验（原文+Schema）** | 幻觉与关系不一致 | 面向一致性的后校验过滤 |
| 5 | **Gold/Pred 同链路** | 标注与预测不一致 | 统一抽取流程与输出格式 |

### 1.2 流程变化对比

| 阶段 | v1 流程 | v2 流程 | 变化类型 | 代码改动 |
|------|---------|---------|----------|----------|
| 本体构建 | CQ 驱动 | **专家骨架 + 聚类混合** | **替换** | 新增模块 |
| 本体筛选 | 无 | **支持度/置信度筛选** | **新增** | 新增模块 |
| 抽取 | CoT | **图结构嵌入 + CoT** | **增强** | Prompt更新 |
| 校验 | 原文回溯 | **原文回溯 + Schema 校验** | **增强** | 新增过滤 |
| Gold/Pred | 不同Prompt | **同一Pipeline** | **统一** | 脚本改造 |

### 1.3 完整Pipeline架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         完整Pipeline架构                                 │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ╔═══════════════════════════════════════════════════════════════════╗  │
│  ║                    【本体构建阶段 TBox】                            ║  │
│  ╠═══════════════════════════════════════════════════════════════════╣  │
│  ║                                                                   ║  │
│  ║  ┌────────────┐     ┌────────────┐     ┌────────────┐            ║  │
│  ║  │ 专家骨架   │───→ │ 语料聚类   │───→ │ 混合融合   │            ║  │
│  ║  └────────────┘     └────────────┘     └──────┬─────┘            ║  │
│  ║                                               │                   ║  │
│  ║                                               ▼                   ║  │
│  ║                                    ┌───────────────────┐          ║  │
│  ║                                    │ 支持度/置信度筛选 │          ║  │
│  ║                                    └─────────┬─────────┘          ║  │
│  ║                                              │                    ║  │
│  ║                                              ▼                    ║  │
│  ║                                    ┌───────────────────┐          ║  │
│  ║                                    │   Master TBox     │          ║  │
│  ╚══════════════════════════════════════╪══════════════════╝  │
│                                         │                       │
│  ╔══════════════════════════════════════╪══════════════════╗  │
│  ║                    【知识抽取阶段 ABox】                 ║  │
│  ╠══════════════════════════════════════╪══════════════════╣  │
│  ║                                      ▼                   ║  │
│  ║  ┌────────────┐              ┌───────────────────┐       ║  │
│  ║  │ 原始文本   │────────────→│ 图结构 CoT 抽取   │       ║  │
│  ║  │ (+上下文)  │              │ (路径驱动推理)    │       ║  │
│  ║  └────────────┘              └─────────┬─────────┘       ║  │
│  ║                                        │                 ║  │
│  ║                                        ▼                 ║  │
│  ║                              ┌───────────────────┐       ║  │
│  ║                              │ 原文回溯 + Schema │       ║  │
│  ║                              │ 双重校验过滤      │       ║  │
│  ║                              └─────────┬─────────┘       ║  │
│  ╚══════════════════════════════╪══════════════════╝  │
│                                         │                       │
│  ╔══════════════════════════════════════╪══════════════════╗  │
│  ║                    【知识融合阶段】                   ║  │
│  ╠══════════════════════════════════════╪══════════════════╣  │
│  ║                                      ▼                   ║  │
│  ║                              ┌───────────────────┐       ║  │
│  ║                              │ 实体归一化 + 去重 │       ║  │
│  ║                              └─────────┬─────────┘       ║  │
│  ╚══════════════════════════════╪══════════════════╝  │
│                                         │                       │
│                                         ▼                       │
│                              ┌───────────────────┐             │
│                              │  高质量知识图谱   │             │
│                              └───────────────────┘             │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.4 各阶段详细说明

| 阶段 | 功能 | 输入 | 输出 | 改动状态 |
|------|------|------|------|----------|
| **H1** | 专家骨架定义 | 专家规则 | expert_skeleton.json | **新增** |
| **H2** | 语料聚类挖掘 | 语料库 | clustering_result.json | **新增** |
| **H3** | 混合融合 | 骨架 + 聚类 | fused_tbox.json | **新增** |
| **H4** | 支持度/置信度筛选 | 融合TBox + 语料统计 | master_tbox.json | **新增** |
| **P5** | 图结构 CoT 抽取 | 文本+TBox | 候选三元组 | **增强** |
| **P5+** | 原文回溯校验 | 三元组+原文 | 过滤后三元组 | **增强** |
| **P5++** | Schema 一致性校验 | 三元组+TBox | 合法三元组 | **新增** |
| **P6** | 实体归一化+关系去重 | 三元组 | 融合结果 | **保留** |

---

## 二、数据准备

### 2.1 语料三分法划分

与 v1 一致，仍采用 P4/P5/EVAL 三分法，但 **P4 语料仅用于混合本体构建**。

### 2.2 Gold/Pred 数据一致性

**强制要求**：Gold 与 Pred 使用 **同一 TBox + 同一文本来源 + 同一抽取链路**。

关键参数：
- `--tbox` 指向同一版本（s2/s3）
- `--text-source` 指向完整文本（避免截断）
- Gold/Pred 都使用 `CQLLMPipeline.extract_events_with_verification`

---

## 三、实验设计

### 3.1 Baseline设计（不变）

| ID | 名称 | 类型 | 对比目的 |
|----|------|------|----------|
| B1 | UIE-Base | 传统模型 | 证明LLM在少样本下优势 |
| B2 | Direct-LLM | 无CoT无校验 | 对比 CoT + 校验的价值 |

### 3.2 消融实验设计

#### TBox 消融（本体构建）

| 变体 | 配置 | 验证目标 |
|------|------|----------|
| full_hybrid | 专家骨架 + 聚类 + 支持度/置信度筛选 | 基准 |
| wo_cluster | 仅专家骨架 | 聚类扩展的价值 |
| wo_quality | 无支持度/置信度筛选 | 质量筛选的价值 |

#### ABox 消融（知识抽取）

| 变体 | 配置 | 验证目标 |
|------|------|----------|
| full_extract | 图结构 + CoT + 双重校验 | 基准 |
| wo_graph | 无图结构提示 | 图结构引导的价值 |
| wo_cot | 无 CoT | CoT 对召回的价值 |
| wo_verify | 无后校验 | 幻觉过滤效果 |
| wo_schema | 无 Schema 校验 | 关系一致性价值 |

### 3.3 评估指标设计

与 v1 保持一致，新增 **Schema 一致性** 与 **幻觉率** 作为关键指标。

---

## 四、代码实现入口

### 4.1 核心模块文件

| 模块 | 文件路径 | 功能 | 状态 |
|------|----------|------|------|
| Hybrid Ontology | `kg/hybrid_ontology.py` | 专家+聚类混合本体构建 | **新增** |
| Graph Structure | `kg/graph_structure.py` | 图结构定义与类型检测 | **新增** |
| Graph-CoT Prompt | `kg/prompts.py` | 图结构 CoT Prompt | **修改** |
| Verification | `kg/hallucination_filter.py` | 原文回溯校验 | 已有 |
| Schema Check | `kg/cq_pipeline.py` | Schema 一致性过滤 | **增强** |
| Output Normalizer | `kg/extraction_output.py` | Gold/Pred 输出统一 | **新增** |

### 4.2 脚本入口

| 脚本 | 功能 | 用途 |
|------|------|------|
| `scripts/run_p2_to_p6.py` | Hybrid 本体 + 抽取 + 融合 | 主入口 |
| `scripts/generate_gold_with_tbox.py` | Gold 生成（TBox约束） | 评测标注 |
| `scripts/p5/run_extraction_on_test.py` | Pred 抽取 | 模型评测 |
| `scripts/p5/run_gold_annotation.sh` | Gold 生成封装 | 一键运行 |
| `scripts/p5/run_single_model.sh` | 单模型评测 | 抽取 + 评测 |

---

## 五、常用命令

### 5.1 本体构建（Hybrid）

```bash
python scripts/run_p2_to_p6.py \
  --corpus_dir data/corpus_for_kg/filtered_ytz_corpus \
  --output_dir outputs/kg_final \
  --tbox_mode hybrid \
  --only_tbox \
  --expert_skeleton data/expert_skeleton.json
```

### 5.2 知识图谱构建（抽取+融合）

```bash
python scripts/run_p2_to_p6.py \
  --corpus_dir data/corpus_for_kg/filtered_ytz_corpus \
  --output_dir outputs/kg_final \
  --tbox_mode hybrid \
  --tbox_file outputs/kg_final/tbox_final.json \
  --only_extraction \
  --use_cot \
  --strict_filter \
  --strict-schema
```

### 5.3 Gold 生成（与 Pred 同链路）

```bash
bash scripts/p5/run_gold_annotation.sh \
  --tbox-version s2 \
  --input data/p5_eval_pool/final/test_final.jsonl \
  --text-source data/p5_eval_pool/pool_v3.jsonl \
  --output data/p5_eval_pool/gold_s2_tbox_full.jsonl \
  --use-cot \
  --use-verification \
  --verification-threshold 0.85 \
  --strict-schema
```

### 5.4 Pred 抽取（图结构 CoT + 后校验）

```bash
bash scripts/p5/run_single_model.sh \
  --model "Qwen/Qwen3-8B" \
  --base-url "https://api.siliconflow.cn/v1/" \
  --temperature 0.1 \
  --relation-mapping configs/relation_mapping.json \
  --tbox outputs/cq_pipeline/final/tbox_s3_optimized.json \
  --text-source data/p5_eval_pool/pool_v3.jsonl \
  --output-base outputs/eval_models_tbox_s3 \
  --test-file data/p5_eval_pool/gold_s3_tbox_full_0108.jsonl \
  --retry-errors
```

---

## 六、统一输出格式（Gold/Pred）

```json
{
  "doc_id": "...",
  "source_text": "...",
  "entities": [{"name": "...", "type": "..."}],
  "events": [...],
  "triples": [
    {
      "subject": "...",
      "subject_type": "...",
      "predicate": "...",
      "object": "...",
      "object_type": "...",
      "evidence": "..."
    }
  ],
  "filtered_triples": [
    {"triple": {...}, "reason": "..."}
  ],
  "schema_filtered_triples": [
    {"triple": {...}, "reason": "..."}
  ],
  "hallucination": {
    "enabled": true,
    "original_count": 0,
    "valid_count": 0,
    "filtered_count": 0,
    "schema_filtered_count": 0,
    "rate": 0.0
  }
}
```

---

## 七、版本历史

| 版本 | 日期 | 更新内容 |
|------|------|----------|
| v2.0 | 2026-01-10 | Hybrid 本体构建 + 图结构 CoT 抽取 + Gold/Pred 统一 |
| v1.0 | 2026-01-02 | CQ 驱动流程与 CoT + 原文回溯 |
