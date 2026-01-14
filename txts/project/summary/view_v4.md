# Hybrid-Only + Graph-CoT + 后校验 知识图谱构建流程 v4.0

> 当前主线：**舍弃 CQ 增强**，采用 **专家骨架 + 语料聚类的混合本体（Hybrid TBox）**，并用 **图结构嵌入的增强 CoT + 后校验（原文回溯 + Schema 一致性）** 完成 ABox 抽取与评测。
>
> 最后更新：2026-01-13

---

## 快速导航

| 角色 | 阅读路径 |
|------|---------|
| **论文写作** | [核心创新点](#11-核心创新点) → [Pipeline架构](#13-完整pipeline架构图) → [消融实验](#32-消融实验设计) |
| **代码开发** | [阶段详解](#14-各阶段详细说明) → [代码入口](#四代码实现入口) → [常用命令](#五常用命令) |
| **实验复现** | [数据准备](#二数据准备) → [Gold/Pred一致性](#22-goldpred一致性强制要求) → [指标计算](#53-指标计算与诊断) |

---

## 一、方法设计

### 1.1 核心创新点

| 序号 | 创新点 | 解决问题 | 对应实现 |
|------|--------|----------|----------|
| 1 | **Hybrid TBox：专家骨架 + 语料聚类** | 纯 CQ/TBox 生成不稳定、噪声多 | `kg/hybrid_ontology.py` |
| 2 | **支持度/置信度筛选** | 聚类噪声与弱关联进入 Schema | `kg/hybrid_ontology.py`（质量筛选阶段） |
| 3 | **图结构嵌入 Prompt** | 复杂段落漏抽、关系连接不系统 | `kg/graph_structure.py` + `kg/prompts.py` |
| 4 | **增强 CoT（图结构驱动链式步骤）** | 抽取步骤不显式、输出不稳定 | `kg/graph_structure.py:get_cot_steps` |
| 5 | **后校验：原文回溯 + Schema 一致性** | 幻觉、关系不合法、方向混乱 | `kg/hallucination_filter.py` + `kg/cq_pipeline.py:_filter_triples_by_schema` |
| 6 | **Gold/Pred 同链路 + 同输出** | 标注与预测流程不一致导致评估失真 | `kg/extraction_output.py` + `kg/utils/text_source.py` |

### 1.2 与旧 CQ-Enhanced 主线的关系

当前主线的关键变化：
- **不再依赖 CQ（P1-P4）驱动本体增强**，TBox 由 Hybrid 构建直接得到。
- **抽取主线统一为：图结构 Prompt + CoT + 后校验**，Gold 与 Pred 共享同一抽取链路与输出格式（仅阈值/严格程度不同）。
- CQ 相关代码仍保留在仓库中，但在 **v4 主线不作为必经流程**。

### 1.3 完整Pipeline架构图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Hybrid-Only KG Pipeline (v4)                     │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ╔═══════════════════════════════════════════════════════════════════╗  │
│  ║                      【TBox：Hybrid 本体构建】                     ║  │
│  ╠═══════════════════════════════════════════════════════════════════╣  │
│  ║  专家骨架(expert_skeleton.json)                                     ║  │
│  ║             │                                                       ║  │
│  ║             ▼                                                       ║  │
│  ║  语料词汇挖掘(逐条JSONL + resume) → 聚类 → 标签化 → 融合对齐        ║  │
│  ║             │                                    │                  ║  │
│  ║             └──────────────→ 支持度/置信度筛选 ←──┘                  ║  │
│  ║                              │                                      ║  │
│  ║                              ▼                                      ║  │
│  ║                         tbox_final.json                              ║  │
│  ╚═══════════════════════════════════╪═══════════════════════════════╝  │
│                                      │                                  │
│  ╔═══════════════════════════════════╪═══════════════════════════════╗  │
│  ║                  【ABox：抽取 + 后校验 + 融合】                    ║  │
│  ╠═══════════════════════════════════════════════════════════════════╣  │
│  ║  输入文本(完整text)                                                 ║  │
│  ║     │                                                               ║  │
│  ║     ▼                                                               ║  │
│  ║  文本类型检测 → 选择图结构(GraphStructure)                           ║  │
│  ║     │                                                               ║  │
│  ║     ▼                                                               ║  │
│  ║  图结构嵌入 Prompt + 增强 CoT 链式步骤 → LLM 抽取(events/triples)     ║  │
│  ║     │                                                               ║  │
│  ║     ▼                                                               ║  │
│  ║  后校验1：原文回溯(实体/事件 grounding, fuzzy/strict)                 ║  │
│  ║  后校验2：Schema 一致性(predicate + domain/range, strict/loose)       ║  │
│  ║     │                                                               ║  │
│  ║     ▼                                                               ║  │
│  ║  轻量归一化 → 实体融合/关系去重(P6) → final_triples.json              ║  │
│  ╚═══════════════════════════════════════════════════════════════════╝  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 1.4 各阶段详细说明

#### H1-H4：Hybrid 本体构建（TBox）
- **输入**：JSONL 语料（逐行 `{"id": "...", "text": "..."}`），以及 `data/expert_skeleton.json`。
- **H1 词汇挖掘**：LLM 从每条 `text` 抽取候选实体词/关系词；支持 `progress_path` + `resume`，可中断续跑。
- **H2 聚类**：对词向量聚类（SentenceTransformer），得到候选簇。
- **H3 标签化与融合**：LLM 给簇打标签并与专家骨架对齐，避免重复概念膨胀。
- **H4 质量筛选**：
  - 支持度：频次过滤低质量类/关系；
  - 置信度：基于共现/强度过滤弱关联。
- **输出**：`outputs/kg_final/tbox_final.json`（用于抽取/评测）。

#### P5：图结构 Prompt + 增强 CoT 抽取
- 文本类型检测：`kg/graph_structure.py:get_graph_structure_for_text`（关键词评分 + 兜底通用结构）。
- Prompt 模板：`kg/prompts.py:P5_GRAPH_COT_EXTRACTION_PROMPT`
  - 结构：图结构提示 + 知识图谱Schema(JSON) + 事件结构参考 + 核心约束 + 链式步骤 + 输出格式。
- CoT 步骤：`kg/graph_structure.py:GraphStructure.get_cot_steps`
  - Step1 实体识别并标注 S/I/O 角色
  - Step2 按路径连接关系
  - Step3 证据回溯
  - Step4 JSON 输出

#### P5+：后校验（原文回溯 + Schema 一致性）
- 原文回溯：`kg/hallucination_filter.py:HallucinationFilter`
  - 严格模式：仅精确匹配
  - 宽松模式：模糊匹配（`fuzzy_threshold`）
- Schema 一致性：`kg/cq_pipeline.py:CQLLMPipeline._filter_triples_by_schema`
  - 严格：不合法直接剔除到 `schema_filtered_triples`
  - 宽松：不剔除但标记 `_schema_warning`

#### P6：融合（实体归一化 + 关系去重）
- `kg/entity_fusion.py:fuse_knowledge`
- 产出 `final_triples.json` 作为“构建出的知识图谱核心ABox”（聚合后的三元组）。

---

## 二、数据准备

### 2.1 关键数据文件

| 名称 | 位置 | 格式 | 用途 |
|------|------|------|------|
| 专家骨架 | `data/expert_skeleton.json` | JSON | Hybrid TBox 的 anchor |
| 语料（示例） | `data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl` | JSONL | Hybrid 本体构建/抽取语料 |
| 评测池（完整文本） | `data/p5_eval_pool/pool_v3.jsonl` | JSONL | `doc_id/id → text` 映射，保证不截断 |
| 测试集（索引/截断） | `data/p5_eval_pool/final/test_final.jsonl` | JSONL | 只作为 doc_id 列表与对齐依据 |
| Hybrid 最终TBox | `outputs/kg_final/tbox_final.json` | JSON | 抽取与评测的统一 Schema |

### 2.2 Gold/Pred一致性（强制要求）

**要求：Gold 与 Pred 必须使用完全一致的输入文本（完整 text）**：
- 测试集 `test_final.jsonl` 中的 `source_text` 可能被截断，**禁止直接用它做抽取输入**。
- 必须提供 `--text-source`，并确保它包含测试集 doc_id 的完整 `text`（推荐使用生成测试集的源语料，例如 `light_pool_v2_dedup.jsonl`）。

实现位置：
- `kg/utils/text_source.py`：统一 doc_id 解析与 text_source 映射逻辑
- `scripts/generate_gold_with_tbox.py` 与 `scripts/p5/run_extraction_on_test.py`：共享相同的 text_source 读取逻辑

---

## 三、实验设计

### 3.1 评测目标

在固定 Hybrid TBox 下，对不同抽取配置/不同模型的 ABox 质量进行对比：
- 事件质量：Event F1
- 三元组质量：Strict / Relaxed Triple F1
- 幻觉过滤：过滤率、证据质量（coverage/similarity）
- Schema 一致性：predicate 合法率 + domain/range 符合率

### 3.2 消融实验设计

#### ABox 消融（当前已支持）

| 变体 | 目的 | Pred 侧关键开关 |
|------|------|-----------------|
| full | 图结构 + CoT + 后校验 | 默认（`--no-cot`/`--no-verify` 都不加） |
| wo_cot | 去掉 CoT（同时去掉图结构 CoT 步骤） | `--no-cot` |
| wo_verify | 去掉后校验（不做原文回溯与 Schema 过滤） | `--no-verify` |
| wo_schema_strict | 关闭严格 Schema（仅打 warning） | `--no-strict-schema` |
| strict_vs_fuzzy | 严格匹配 vs 模糊匹配 | `--strict-filter` / `--fuzzy-threshold` |

> 说明：当前代码中“图结构嵌入”与“CoT 模式”绑定（CoT 即使用图结构 Prompt）。如果你需要 **wo_graph 但保留 CoT** 的单独消融，需要新增开关（例如 `--no-graph`）把 Prompt 切到非图结构版本。

#### TBox 消融（推荐可做）

| 变体 | 目的 | 做法 |
|------|------|------|
| expert_only | 仅专家骨架 | 直接用 `data/expert_skeleton.json` 作为 `--tbox` |
| hybrid_full | 专家+聚类+筛选 | 用 `outputs/kg_final/tbox_final.json` |

> 说明：目前 Hybrid 过程的更多开关（如禁用聚类/禁用筛选）尚未以 CLI 参数暴露；若要做更细粒度 TBox 消融，建议在 `kg/hybrid_ontology.py` 与 `scripts/run_p2_to_p6.py` 增加参数（例如 `--hybrid-wo-cluster/--hybrid-wo-quality`）。

---

## 四、代码实现入口

### 4.1 核心模块

| 模块 | 文件路径 | 作用 |
|------|----------|------|
| Hybrid 本体构建 | `kg/hybrid_ontology.py` | 专家骨架 + 词汇挖掘 + 聚类 + 融合 + 支持度/置信度筛选 |
| 图结构 | `kg/graph_structure.py` | 文本类型检测 + 图结构节点/路径 + CoT 步骤生成 |
| Prompt 模板 | `kg/prompts.py` | `P5_GRAPH_COT_EXTRACTION_PROMPT`、CoT JSON 解析等 |
| 后校验 | `kg/hallucination_filter.py` | 原文回溯（严格/模糊） |
| Schema 校验 | `kg/cq_pipeline.py` | `extract_events_with_verification` + `_filter_triples_by_schema` |
| 统一输出 | `kg/extraction_output.py` | Gold/Pred 输出格式统一（默认不保留 `source_text`） |
| 文本映射 | `kg/utils/text_source.py` | 统一 `doc_id → 完整text` |

### 4.2 脚本入口（主线）

| 脚本 | 用途 |
|------|------|
| `scripts/run_p2_to_p6.py` | 主入口：Hybrid TBox + 批量抽取 + 融合（支持 resume/log） |
| `scripts/generate_gold_with_tbox.py` | 生成 Gold（图结构 Prompt + CoT + 后校验） |
| `scripts/p5/run_extraction_on_test.py` | 生成 Pred（与 Gold 同链路，默认不重试、记录 error） |
| `tools/abox_metrics.py` | 指标计算（Event/Triple/Entity/Relation/TBox consistency 等） |

---

## 五、常用命令

### 5.1 Hybrid 本体构建（仅TBox）

```bash
conda activate YangtzeLLM

python scripts/run_p2_to_p6.py \
  --corpus_dir data/corpus_for_kg/filtered_ytz_corpus \
  --ontology_corpus data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --output_dir outputs/kg_final \
  --tbox_mode hybrid \
  --only_tbox \
  --expert_skeleton data/expert_skeleton.json \
  --ontology_resume \
  --log-file logs/kg_final/hybrid_v4.log
```

产物：
- `outputs/kg_final/tbox_final.json`
- `outputs/kg_final/hybrid_ontology/`（含 `vocab_mining.jsonl`、`filter_report.json` 等）

### 5.2 构建知识图谱（批量抽取 + 融合，产出 final_triples.json）

支持 `corpus_dir` 直接传 JSONL 文件（每行含 `id/doc_id` + `text`）：

```bash
conda activate YangtzeLLM

python scripts/run_p2_to_p6.py \
  --corpus_dir data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --output_dir outputs/kg_build_v4 \
  --tbox_mode hybrid \
  --tbox_file outputs/kg_final/tbox_final.json \
  --only_extraction \
  --use_cot \
  --strict_filter \
  --fuzzy_threshold 0.8 \
  --strict-schema \
  --resume-extraction \
  --log-file logs/kg_build_v4/extraction_v4.log
```

产物：
- `outputs/kg_build_v4/extractions.jsonl`（逐条输出，支持断点续跑）
- `outputs/kg_build_v4/final_triples.json`（聚合后的图谱三元组）

### 5.3 生成 Gold（严格 Schema + 原文回溯）

```bash
conda activate YangtzeLLM

python scripts/generate_gold_with_tbox.py \
  --input data/p5_eval_pool/final/test_final.jsonl \
  --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --output data/p5_eval_pool/gold_hybrid_tbox.jsonl \
  --model "LongCat-Flash-Chat" \
  --base-url "https://api.longcat.chat/openai/v1" \
  --temperature 0.1 \
  --top-p 0.1 \
  --use-cot \
  --use-verification \
  --verification-threshold 0.85 \
  --strict-schema \
  --resume \
  --interval 5 \
  2>&1 | tee outputs/eval_models_hybrid/gold_v4.log
```

### 5.4 生成 Pred（宽松 Schema + 模糊阈值）

```bash
conda activate YangtzeLLM

python scripts/p5/run_extraction_on_test.py \
  --test-file data/p5_eval_pool/final/test_final.jsonl \
  --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --model "Qwen/Qwen3-8B" \
  --base-url "https://api.siliconflow.cn/v1/" \
  --temperature 0.1 \
  --top-p 0.1 \
  --output outputs/eval_models_hybrid/predictions_qwen_v4.jsonl \
  --fuzzy-threshold 0.75 \
  --no-strict-schema \
  --skip-existing \
  --interval 10 \
  2>&1 | tee outputs/eval_models_hybrid/predictions_qwen_v4.log
```

### 5.5 指标计算与诊断

建议采用“对齐 → 过滤 error →（可选）关系映射/实体归一化/方向归一化 → 评测”的固定流程：

```bash
# 1) 对齐 Pred 到 Gold（按 doc_id）
python scripts/p5/align_pred_to_gold.py \
  --gold data/p5_eval_pool/gold_hybrid_tbox.jsonl \
  --pred outputs/eval_models_hybrid/predictions_qwen_v4.jsonl \
  --out outputs/eval_models_hybrid/predictions_qwen_v4_aligned.jsonl \
  --report outputs/eval_models_hybrid/predictions_qwen_v4_align_report.json

# 2) 过滤掉 Gold/Pred 中包含 error 的行
python scripts/p5/filter_gold_errors.py \
  --gold data/p5_eval_pool/gold_hybrid_tbox.jsonl \
  --pred outputs/eval_models_hybrid/predictions_qwen_v4_aligned.jsonl \
  --gold-out outputs/eval_models_hybrid/gold_filtered.jsonl \
  --pred-out outputs/eval_models_hybrid/pred_filtered.jsonl

# 3)（可选）关系映射 / 实体同义词归一化 / 三元组方向归一化
# 关系映射
python scripts/p5/apply_relation_mapping.py \
  --pred outputs/eval_models_hybrid/pred_filtered.jsonl \
  --gold outputs/eval_models_hybrid/gold_filtered.jsonl \
  --mapping configs/relation_mapping.json \
  --out-pred outputs/eval_models_hybrid/pred_mapped.jsonl \
  --out-gold outputs/eval_models_hybrid/gold_mapped.jsonl

# 实体同义词归一化（若配置存在）
python scripts/p5/normalize_entities.py \
  --gold outputs/eval_models_hybrid/gold_mapped.jsonl \
  --pred outputs/eval_models_hybrid/pred_mapped.jsonl \
  --synonyms configs/entity_synonyms.json \
  --gold-out outputs/eval_models_hybrid/gold_entity_norm.jsonl \
  --pred-out outputs/eval_models_hybrid/pred_entity_norm.jsonl

# 方向归一化（基于 TBox domain/range + 强制规则）
python scripts/p5/normalize_triple_direction.py \
  --gold outputs/eval_models_hybrid/gold_entity_norm.jsonl \
  --pred outputs/eval_models_hybrid/pred_entity_norm.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --gold-out outputs/eval_models_hybrid/gold_normalized.jsonl \
  --pred-out outputs/eval_models_hybrid/pred_normalized.jsonl

# 4) 指标计算
python tools/abox_metrics.py \
  --gold outputs/eval_models_hybrid/gold_normalized.jsonl \
  --pred outputs/eval_models_hybrid/pred_normalized.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --out outputs/eval_models_hybrid/metrics.json

# 5) 诊断报告（可选）
python scripts/p5/diagnose_extraction.py \
  --gold outputs/eval_models_hybrid/gold_normalized.jsonl \
  --pred outputs/eval_models_hybrid/pred_normalized.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --output outputs/eval_models_hybrid/diagnosis_report.json
```

---

## 六、统一输出格式（Gold/Pred/基线）

统一输出由 `kg/extraction_output.py:build_extraction_record` 生成，核心字段：

```json
{
  "doc_id": "...",
  "use_cot": true,
  "use_verify": true,
  "entities": [{"name": "...", "type": "..."}],
  "events": [{"event_id": "...", "event_type": "...", "name": "..."}],
  "triples": [{"subject": "...", "predicate": "...", "object": "...", "evidence": "..."}],
  "filtered_triples": [{"triple": {...}, "reason": "..."}],
  "schema_filtered_triples": [{"triple": {...}, "reason": "..."}],
  "hallucination": {"original_count": 0, "filtered_count": 0, "rate": 0.0},
  "error": ""
}
```

说明：
- v4 主线默认 **不输出 `source_text`**（避免体积过大/泄露；评测依赖 doc_id 对齐与 text_source 映射）。
- 任意异常（JSON 解析失败、限流、超时等）会写入 `error` 字段，用于 `--retry-errors` 或后续过滤。

---

## 七、下一步：消融实验建议（v4主线）

建议优先做 **ABox 消融**（固定同一份 Gold，Pred 侧替换开关即可）：

1) 以 `full` 为基准跑一份 Pred（当前已完成）  
2) 逐个改动单一因素：
- `--no-cot`（去掉图结构 CoT）
- `--no-verify`（去掉原文回溯与 Schema 校验）
- `--no-strict-schema`（Schema 宽松）
- `--strict-filter` 与 `--fuzzy-threshold`（匹配策略）

每跑完一个变体，都用 [5.5](#55-指标计算与诊断) 的固定评测流程生成 `metrics.json`，最后汇总对比即可。

