# YangtzeDestoryLLM 项目全景指南

> 基于大语言模型与知识图谱的长江流域水旱灾害问答系统  
> 最后更新：2025-12-23

---

## 📚 快速导航

| 角色 | 阅读路径 |
|------|---------|
| **新开发者（0基础）** | [30秒速览](#30秒速览) → [1. 项目定位](#1-项目定位与核心价值) → [5. 快速开始](#5-快速开始) → [常见问题](#14-常见问题faq) |
| **论文写作** | [1.2 方法论来源](#12-方法论来源) → [8. 与原论文对比](#8-与原论文的对比) → [9. 论文写作映射](#9-论文写作映射) → [13. 技术亮点](#13-关键技术亮点答辩论文写作参考) |
| **代码贡献** | [3. 核心模块](#3-核心模块详解) → [4. 目录结构](#4-目录结构) → [6. 核心算法](#6-核心算法详解) |
| **实验复现** | [5.2 常用命令](#52-常用命令) → [5.3 配置说明](#53-配置说明) → [9.2 实验数据](#92-可引用的实验数据) |
| **调试问题** | [5.1.1 常见环境问题](#511-️-常见环境问题) → [14. 常见问题](#14-常见问题faq) → [Code-Rule.md](/.qoder/rules/Code-Rule.md) |

---

## 🚀 30秒速览

```bash
# 1️⃣ 安装（2分钟）
conda create -n YangtzeLLM python=3.10 && conda activate YangtzeLLM
pip install -r requirements.txt
echo "OPENAI_API_KEYS=your_key" > .env

# 2️⃣ 跑通 P1-P5 流程（5分钟）
python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash --n-cq 10

# 3️⃣ 查看输出
ls outputs/cq_pipeline/final/
# 产出：p1_cqs.json（能力问题）、p2_tbox_init.json（初始本体）、p5_events.json（抽取结果）

# 4️⃣ 计算评估指标
python tools/tbox_metrics.py outputs/cq_pipeline/final/p2_tbox_init.json
# 输出：RR=0.5319, IR=0.6471, AR=2.5000
```

**核心理念**：CQ（能力问题）驱动 → 反推 TBox（本体）→ TBox 约束抽取 ABox（实例）→ GraphRAG 问答

---

## 1. 项目定位与核心价值

本项目是一个面向**长江流域水旱灾害（洪水/干旱/枯水）**的端到端 **KG-RAG 问答系统**，作为硕士论文的核心实现。

### 1.1 核心创新点

| 创新维度 | 具体内容 |
|---------|---------|
| **CQ 驱动构建** | 以能力问题（Competency Questions）作为需求规范，反推本体模式（TBox），而非传统的"专家先定顶层类" |
| **TBox 约束抽取** | 在模式约束下抽取实例（ABox），减少开放抽取的噪声与"幻觉关系" |
| **工程化流水线** | P1-P5 五阶段可复现流程，支持断点续跑、支持度聚合、冲突检测 |
| **多维度评估** | OntoQA 结构指标 + CQ 覆盖度 + 抽取 F1 + 冲突报告的完整评估体系 |

### 1.2 方法论来源

借鉴论文《洪水本体构建的半自动化框架》的核心思想：
- **人机协同**：LLM 负责高吞吐扩展，规则/评估/人工审核兜底
- **CQ 驱动**：CQ 作为需求与评价的共同载体
- **多源增强**：权威文档 + 实例语料的双轨富集

---

## 2. 系统架构与数据流

### 2.1 全景数据流

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据流全景图                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌──────────────┐                                                           │
│  │ 原始语料      │  PDF/TXT/新闻/年鉴/预案/论文                              │
│  └──────┬───────┘                                                           │
│         ▼                                                                   │
│  ┌──────────────┐  tools/paddle_ocr.py (可选)                               │
│  │ OCR 处理     │  tools/corpus_cleaner.py                                  │
│  └──────┬───────┘                                                           │
│         ▼                                                                   │
│  ┌──────────────┐  tools/filter_corpus_light.py                             │
│  │ 语料过滤     │  tools/build_manifest.py                                  │
│  └──────┬───────┘                                                           │
│         ▼                                                                   │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                    三分法语料划分                                  │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │       │
│  │  │ P4 语料     │  │ P5 语料     │  │ EVAL 语料   │               │       │
│  │  │ (概念/制度) │  │ (事件事实) │  │ (评测池)   │               │       │
│  │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘               │       │
│  └─────────┼────────────────┼────────────────┼──────────────────────┘       │
│            │                │                │                              │
│            ▼                │                │                              │
│  ┌──────────────────────────┼────────────────┼──────────────────────┐       │
│  │      CQ 驱动 KG 构建流水线 (P1-P5)         │                      │       │
│  │                          │                │                      │       │
│  │  P1: 领域描述 → CQ 生成   │                │                      │       │
│  │         ▼                │                │                      │       │
│  │  P2: CQ → 初始 TBox      │                │                      │       │
│  │         ▼                │                │                      │       │
│  │  P3: TBox 规范化/去重     │                │                      │       │
│  │         ▼                │                │                      │       │
│  │  P4: 语料驱动增强 ◄───────┘                │                      │       │
│  │         ▼                                 │                      │       │
│  │  P5: TBox 约束抽取 ◄──────────────────────┘                      │       │
│  │         ▼                                                        │       │
│  │  events.json + triples.json                                      │       │
│  └──────────────────────────────────────────────────────────────────┘       │
│            │                                                                │
│            ▼                                                                │
│  ┌──────────────────────────────────────────────────────────────────┐       │
│  │                    KG 存储与问答                                  │       │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │       │
│  │  │ NetworkX    │  │ Neo4j       │  │ GraphRAG    │               │       │
│  │  │ (内存图)    │  │ (持久化)   │  │ (问答引擎) │               │       │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │       │
│  └──────────────────────────────────────────────────────────────────┘       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 三分法语料划分逻辑

| 语料类型 | 用途 | 特征 | 示例来源 |
|---------|------|------|----------|
| **P4 语料** | TBox 增强（概念扩展） | 制度性、定义性文本 | 防汛条例、应急预案、技术规范 |
| **P5 语料** | ABox 抽取（事件填充） | 事实性、叙述性文本 | 灾害新闻、年鉴记录、事件报告 |
| **EVAL 语料** | 评测池（黄金标注） | 代表性、覆盖性 | 人工标注的典型段落 |

### 2.3 文件产物映射

```
阶段          输入                            输出                          大小/数量
───────────────────────────────────────────────────────────────────────────
P1     领域描述文本                    p1_cqs.json                       ~10-50 条 CQ
P2     p1_cqs.json                    p2_tbox_init.json                 ~30-50 类
P3     p2_tbox_init.json              p3_tbox_normalized.json           ~30-50 类（清洗后）
       (可选) + class_hierarchy       p3_tbox_dedup.json               ~25-40 类（去重后）
P4     p3_tbox + 259 文档             p4_suggestions.jsonl (5.9K 条)   
                                      p4_corpus_suggestions_agg.json    ~200-500 建议
                                      p4_tbox_augmented_s2_*.json      ~40-60 类
P5     p4_tbox + 文本片段             p5_batch_results.jsonl            每段 0-N 事件
                                      p5_all_events.json                汇总事件
                                      p5_all_triples.json               汇总三元组
评估    p*_tbox + p5_results          OntoQA metrics (RR/IR/AR)
                                      CQ 覆盖度 (多阈值)
                                      冲突报告 (JSON)
```

---

## 3. 核心模块详解

### 3.1 CQ 驱动流水线 (P1-P5)

**核心实现**: `kg/cq_pipeline.py`

| 阶段 | 功能 | 输入 | 输出 | 关键代码 |
|------|------|------|------|----------|
| **P1** | CQ 生成 | 领域描述文本 | `p1_cqs.json` | `generate_cqs()` |
| **P2** | CQ → TBox | CQ 列表 | `p2_tbox_init.json` | `cq_to_schema()` |
| **P3** | TBox 规范化 | P2 TBox | `p3_tbox_normalized.json` | `refine_schema()` + `normalize_tbox_with_p3()` |
| **P4** | 语料增强 | P3 TBox + 语料 | `p4_tbox_enhanced.json` | `run_p4_over_corpus()` |
| **P5** | 事件抽取 | P4 TBox + 文本 | `p5_events.json` | `extract_events()` |

#### 3.1.1 TBox 数据结构

```python
@dataclass
class TBoxSchema:
    classes: List[ClassDef]      # 类定义（含 parent 继承关系）
    relations: List[RelationDef]  # 关系定义（domain → range）
    attributes: List[AttributeDef] # 属性定义（owner.name: value_type）
```

#### 3.1.2 P4 支持度聚合机制

```python
# 核心逻辑：跨文档重复出现的概念获得更高置信度
for suggestion in all_suggestions:
    key = (type, name, parent_or_domain_range, range)
    if key in buckets:
        buckets[key]["_support"] += 1
        buckets[key]["_support_sources"].append(doc_id)
    else:
        buckets[key] = {**suggestion, "_support": 1, "_support_sources": [doc_id]}

# 过滤：只保留 support >= min_support 的建议
filtered = [s for s in aggregated if s["_support"] >= min_support]
```

### 3.2 LLM 调用层

**核心实现**: `kg/llm_core.py`

| 特性 | 说明 |
|------|------|
| **多 Key 轮换** | 遇到 429 自动切换，冷却后恢复 |
| **请求模式** | SDK / HTTP POST / Auto 三种模式 |
| **JSON 强制输出** | `json_mode=True` + fence 剥离 + 子串兜底 |
| **第三方适配** | 自动识别 LongCat/Gemini 等 API 特性 |

```python
# 使用示例
llm = LLMClient(config)
response = llm.chat_messages(messages, json_mode=True)
```

### 3.3 语料处理工具链

| 工具 | 功能 | 输入 | 输出 |
|------|------|------|------|
| `tools/paddle_ocr.py` | PDF → Markdown | PDF 文件 | Markdown 文本 |
| `tools/corpus_cleaner.py` | 清洗与切分 | PDF/TXT | 分段 JSONL |
| `tools/filter_corpus_light.py` | 轻过滤 + LLM 判定 | 分段 JSONL | `light_pool.jsonl` |
| `tools/build_manifest.py` | 三分法划分 | 过滤后语料 | P4/P5/EVAL 语料 |

### 3.4 评估体系

| 评估维度 | 工具 | 指标 |
|----------|------|------|
| **TBox 结构** | `tools/tbox_metrics.py` | RR (关系丰富度), IR (继承丰富度), AR (属性丰富度) |
| **CQ 覆盖度** | `tools/cq_coverage.py` | 多阈值覆盖率 (0.3-0.9) |
| **抽取质量** | `tools/abox_metrics.py` | Event F1, Triple F1 (strict/relaxed) |
| **冲突检测** | `kg/utils/conflict_detection.py` | 悬空引用、重复定义、孤立类 |

### 3.5 检索与问答

| 组件 | 实现 | 功能 |
|------|------|------|
| **BM25 检索** | `retrievers/text_retriever.py` | 关键词匹配，jieba 分词 |
| **向量检索** | `retrievers/vector_retriever.py` | SentenceTransformer 语义召回 |
| **图检索** | `retrievers/graph_retriever.py` | 多跳子图扩展 |
| **GraphRAG** | `kg/query.py` | BM25 找种子 → 多跳扩展 → LLM 生成答案 |

---

## 4. 目录结构

```
YangtzeDestoryLLM/
├── configs/
│   └── cfg.yaml              # 全局配置（路径、LLM、过滤、实验参数）
│
├── kg/                       # 核心 KG 构建模块
│   ├── cq_pipeline.py        # P1-P5 流水线主逻辑
│   ├── prompts.py            # 各阶段 Prompt 模板
│   ├── llm_core.py           # 统一 LLM 调用层
│   ├── query.py              # GraphRAG 问答引擎
│   ├── build_from_json.py    # JSONL → NetworkX
│   ├── neo4j_adapter.py      # Neo4j 导入适配器
│   └── utils/
│       ├── deduplication.py  # Embedding 去重 (BGE 768维)
│       ├── schema_alignment.py # 同义对齐
│       ├── conflict_detection.py # 冲突检测
│       └── entity_linking.py # 实体标准化
│
├── retrievers/               # 检索器实现
│   ├── text_retriever.py     # BM25 检索
│   ├── vector_retriever.py   # 向量检索
│   └── graph_retriever.py    # 图检索
│
├── scripts/                  # 运行入口脚本
│   ├── run_cq_pipeline.py    # P1-P5 全流程
│   ├── run_p4_batch.py       # P4 批处理（断点续跑）
│   ├── p5_from_tbox.py       # 仅 P5 抽取
│   ├── run_full_evaluation.py # 一键评估
│   └── run_full_pipeline.sh  # 全流程 Shell 脚本
│
├── tools/                    # 语料处理与评估工具
│   ├── corpus_cleaner.py     # 语料清洗切分
│   ├── filter_corpus_light.py # 轻过滤
│   ├── build_manifest.py     # 三分法划分
│   ├── tbox_metrics.py       # OntoQA 指标
│   ├── cq_coverage.py        # CQ 覆盖度
│   ├── abox_metrics.py       # 抽取质量评估
│   └── ontoqa_metrics.py     # 批量对比
│
├── experiments/              # 对比/消融实验
│   ├── exp_dedup_comparison.py
│   ├── exp_p5_compare.py
│   └── exp_qa_comparison.py
│
├── data/                     # 数据目录
│   ├── corpus_for_kg/        # KG 构建语料
│   ├── corpus_for_onto/      # 本体增强语料
│   ├── manifests/            # 语料划分清单
│   └── p5_eval_pool/         # 评测池
│
├── outputs/                  # 输出目录
│   ├── cq_pipeline/final/    # P1-P5 产物
│   └── ontoqa/               # 评估报告
│
└── txts/                     # 文档
    ├── project/              # 项目文档
    └── survey/               # 论文笔记
```

---

## 5. 快速开始

### 5.1 环境配置

```bash
# 1. 创建 Conda 环境
conda create -n YangtzeLLM python=3.10
conda activate YangtzeLLM

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置 API Key（在 .env 文件中）
# 支持多 Key 轮换，遇到 429 限流自动切换
echo "OPENAI_API_KEYS=key1,key2,key3" > .env
# 或使用智谱 API
echo "ZHIPU_API_KEY=your_zhipu_key" >> .env
# 或使用 Gemini API
echo "GOOGLE_API_KEY=your_gemini_key" >> .env

# 4. 可选：配置大盘存储（服务器环境）
./setup_storage_env.sh
```

### 5.1.1 ⚠️ 常见环境问题

| 问题 | 解决方案 |
|------|----------|
| Conda 激活失败 | 使用 `source activate YangtzeLLM` 或检查 conda 路径 `/home/zjx/miniconda3/bin/python` |
| OCR/Paddle 报错 | 参见 [Code-Rule.md](/.qoder/rules/Code-Rule.md) 的 OCR 踩坑总结 |
| CUDA/NCCL 冲突 | 避免在 `~/.bashrc` 写死 `LD_LIBRARY_PATH`，优先使用 conda 环境的库 |
| 代理导致本地连接失败 | 设置 `NO_PROXY=localhost,127.0.0.1,::1` |

### 5.2 常用命令

```bash
# ============ 完整 P1-P5 流程 ============
python scripts/run_cq_pipeline.py --cfg configs/cfg.yaml

# 指定 LLM 提供商和模型
python scripts/run_cq_pipeline.py \
    --provider zhipu --model glm-4.5-flash --n-cq 30

# 从特定阶段开始（断点续跑）
python scripts/run_cq_pipeline.py --start-step p3

# ============ P4 大规模语料增强 ============
# 支持断点续跑、支持度聚合、冲突检测
python scripts/run_p4_batch.py \
    --base-tbox outputs/cq_pipeline/final/p3_tbox_normalized.json \
    --corpus-jsonl data/corpus_for_onto/p4_only.jsonl \
    --min-support 2 \
    --allow-new-classes false

# merge-only 模式（复用已生成的建议，快速生成多配置版本）
python scripts/run_p4_batch.py \
    --base-tbox outputs/cq_pipeline/final/p3_tbox_normalized.json \
    --merge-only \
    --min-support 3 \
    --allow-new-classes true

# ============ 仅 P5 抽取 ============
# 从 TBox 文件抽取事件与三元组
python scripts/p5_from_tbox.py \
    --tbox-file outputs/cq_pipeline/final/p4_tbox_enhanced.json \
    --corpus-dir data/corpus_for_kg/p5_only

# 批量抽取（支持断点续跑）
python scripts/p5_from_tbox.py \
    --tbox-file outputs/cq_pipeline/final/p4_tbox_enhanced.json \
    --corpus-jsonl data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl \
    --max-segments 100

# ============ 评估与指标计算 ============
# 一键评估（TBox 结构 + 抽取质量）
python scripts/run_full_evaluation.py \
    --tbox-file outputs/cq_pipeline/final/p4_tbox_enhanced.json \
    --gold data/p5_eval_pool/gold_annotations.json \
    --preds outputs/p5_batch_results.jsonl

# OntoQA 指标计算
python tools/tbox_metrics.py outputs/cq_pipeline/final/p4_tbox_enhanced.json

# CQ 覆盖度计算（多阈值）
python tools/cq_coverage.py \
    --tbox-file outputs/cq_pipeline/final/p4_tbox_enhanced.json \
    --cq-file outputs/cq_pipeline/final/p1_cqs.json

# 批量对比多个 TBox 版本
python tools/ontoqa_metrics.py outputs/cq_pipeline/final/*.json

# ============ 全流程 Shell 脚本 ============
# 完整流程（清洗 → 过滤 → P1-P5 → 评估）
./scripts/run_full_pipeline.sh

# 试运行（仅显示命令不执行）
./scripts/run_full_pipeline.sh --dry-run

# 从特定步骤开始
./scripts/run_full_pipeline.sh --start-step p4

# 仅运行某个步骤
./scripts/run_full_pipeline.sh --only-step p5
```

### 5.3 配置说明

`configs/cfg.yaml` 核心配置项：

```yaml
# ============ LLM 配置 ============
llm:
  base_url: https://api.longcat.chat/openai/v1  # OpenAI 兼容接口地址
  model_name: LongCat-Flash-Chat                # 默认模型
  temperature: 0.1                               # 低温度减少随机性
  timeout: 180                                   # 超时时间（秒）
  request_mode: post                             # 请求模式：sdk/post/auto
  # 注意：LongCat API 会自动禁用 response_format

# 分阶段 LLM 配置（可选，不配置则使用默认）
llm_per_stage:
  p1:
    model_name: "gpt-4o-mini"      # P1 使用 gpt-4o-mini
  p2:
    model_name: "gpt-4o-mini"
  p4:
    model_name: "gpt-4o-mini"

# ============ Embedding 配置 ============
embedding:
  model_name: "BAAI/bge-base-zh-v1.5"           # 中文向量模型（768维）
  cache_folder: "/media/data2/YangtzeDestoryLLM/models_cache"

# ============ P4 配置 ============
p4:
  min_support: 2              # 最低支持度（跨文档重复次数）
  allow_new_classes: false    # 是否允许新增类
  align_synonyms: true        # 同义词对齐
  dedup_with_embeddings: true # 向量去重
  dedup_threshold: 0.7        # 去重阈值（与论文一致）
  sleep_between_calls: false  # 是否在 LLM 调用间随机休眠

# ============ P5 配置 ============
p5:
  favor_existing_classes: true # 优先复用已有类（保守抽取）
  normalize_entities: false    # 实体标准化（地名/术语别名归一）

# ============ 语料过滤配置 ============
filtering:
  light:
    min_cn_ratio: 0.2        # 轻过滤最小汉字占比
    max_weird_ratio: 0.4     # 最大异常字符比例
  eval:
    min_cn_ratio: 0.3        # 评测池最小汉字占比
    max_weird_ratio: 0.3

# ============ 评测池配置 ============
eval_pool:
  stratify_by: topic_label   # 分层策略：source_type 或 topic_label
  target_topic_label:
    disaster_event: 150      # 灾害事件叙述
    measure_response: 180    # 防治措施/应急响应
    background_analysis: 50  # 致灾因子/背景分析
    institution_regulation: 50  # 制度/法规
    impact_assessment: 10    # 影响与损失评估
  dev_ratio: 0.6             # Dev/Test 划分比例

# ============ 去重配置 ============
dedup_schema:
  enabled: true
  threshold: 0.7             # 余弦相似度阈值（与论文对齐）
```

#### 配置优先级

```
CLI 参数 > cfg.yaml > 代码默认值
```

例如：`--min-support 3` 会覆盖 `cfg.yaml` 中的 `p4.min_support`

---

## 6. 核心算法详解

### 6.1 OntoQA 指标计算

```python
# 关系丰富度：非继承关系占比
RR = P / (P + SC)  # P=关系数, SC=子类边数

# 继承丰富度：类层级深度
IR = SC / C        # C=类数

# 属性丰富度：平均每类属性数
AR = A / C         # A=属性数
```

### 6.2 Embedding 去重

```python
class EmbeddingDeduplicator:
    def __init__(self, model_name="BAAI/bge-base-zh-v1.5", threshold=0.7):
        self.model = SentenceTransformer(model_name)
        self.threshold = threshold
    
    def deduplicate_classes(self, existing, candidates):
        # 1. 编码为 768 维向量（L2 归一化）
        existing_embs = self.model.encode(texts, normalize_embeddings=True)
        
        # 2. 计算余弦相似度（归一化后点积即余弦）
        sims = np.dot(existing_embs, cand_emb)
        
        # 3. 阈值判定
        if max_sim >= self.threshold:
            rejected.append(cand)  # 重复
        else:
            accepted.append(cand)  # 保留
```

### 6.3 P5 抽取结果清洗

```python
def _sanitize_p5_result(res, schema):
    # 1. 类型兜底
    if not isinstance(res, dict):
        return {"events": [], "triples": []}
    
    # 2. event_type 约束回退
    if ev["event_type"] not in allowed_event_types:
        ev["event_type"] = "DisasterEvent"  # 回退到基类
    
    # 3. predicate 不在 TBox 时标记（不丢弃）
    if tr["predicate"] not in allowed_predicates:
        tr["_invalid_predicate"] = True
    
    # 4. 结构补齐
    ev.setdefault("time", {"start_time": "", "end_time": ""})
    ev.setdefault("space", {"main_stream": [], "tributaries": [], "provinces": []})
```

---

## 7. 产物说明

### 7.1 TBox 产物

| 文件 | 阶段 | 说明 |
|------|------|------|
| `p1_cqs.json` | P1 | 能力问题列表 |
| `p2_tbox_init.json` | P2 | 初始 TBox |
| `p3_tbox_normalized.json` | P3 | 规范化 TBox |
| `p3_tbox_dedup.json` | P3 | 去重后 TBox |
| `p4_tbox_enhanced.json` | P4 | 增强后 TBox |
| `p4_suggestions.jsonl` | P4 | 逐文档建议（断点续跑） |
| `p4_corpus_suggestions_agg.json` | P4 | 聚合建议（含 _support） |

### 7.2 ABox 产物

| 文件 | 说明 |
|------|------|
| `p5_events.json` | 单条抽取结果 |
| `p5_batch_results.jsonl` | 批量抽取结果（断点续跑） |
| `p5_all_events.json` | 事件汇总 |
| `p5_all_triples.json` | 三元组汇总 |

### 7.3 评估产物

| 文件 | 说明 |
|------|------|
| `outputs/ontoqa/metrics*.json` | OntoQA 指标 |
| `p3_conflicts.json` | P3 冲突报告 |
| `p4_conflicts.json` | P4 冲突报告 |

---

## 8. 与原论文的对比

| 维度 | 原论文 | 本项目 |
|------|--------|--------|
| **初始本体** | 专家定 6 顶层类 | CQ 反推 TBox |
| **去重模型** | text-embedding-3-large | BGE-base-zh-v1.5 (768维) |
| **去重阈值** | 0.7 | 0.7（一致） |
| **质量控制** | 专家审核（8%/10% 拒绝率） | 支持度聚合 + 冲突检测 |
| **文档解析** | MunerU | JSONL 语料（预清洗） |
| **下游验证** | 警报优化案例 | KG-RAG 问答 + 抽取评测 |

---

## 9. 论文写作映射

### 9.1 方法章节对应

| 论文章节 | 代码实现 |
|----------|----------|
| CQ 驱动 schema 构建 | P1-P3 (`kg/cq_pipeline.py`) |
| 语料增强 | P4 (`scripts/run_p4_batch.py`) |
| TBox 约束抽取 | P5 (`extract_events()`) |
| KG-RAG 应用 | `kg/query.py` + `retrievers/*` |
| 评估体系 | `tools/tbox_metrics.py` + `tools/cq_coverage.py` |

### 9.2 可引用的实验数据

```
# 示例：带层级的 P2 TBox
C=34, P=25, A=85, SC=22
RR=0.5319, IR=0.6471, AR=2.5000

# 示例：P4 增强版本
C=48, P=19, A=131, SC=6
RR=0.7600, IR=0.1250, AR=2.7292
```

---

## 10. 常见问题

### Q1: 如何处理 LLM 限流？
系统内置多 Key 轮换机制，遇到 429 自动切换，冷却后恢复。配置多个 Key：
```bash
OPENAI_API_KEYS=key1,key2,key3
```

### Q2: P4 中断后如何继续？
P4 支持断点续跑，已处理的文档会跳过：
```bash
python scripts/run_p4_batch.py --corpus-jsonl data/p4_only.jsonl
# 自动检测 p4_suggestions.jsonl，跳过已处理文档
```

### Q3: 如何调整去重阈值？
在 `configs/cfg.yaml` 中修改：
```yaml
p4:
  dedup_threshold: 0.7  # 调整此值
dedup_schema:
  threshold: 0.7        # P2/P3 去重阈值
```

### Q4: 如何添加新的语料来源？
1. 将文件放入 `data/corpus_for_kg/raw_all/`
2. 运行清洗：`python tools/corpus_cleaner.py --input <dir>`
3. 运行过滤：`python tools/filter_corpus_light.py`
4. 运行划分：`python tools/build_manifest.py`

---

## 11. 代码规模

- Python 源文件：67+ 个
- 代码行数：约 30k（含注释与文档字符串）
- 核心模块：`kg/` (~5k 行), `tools/` (~10k 行), `scripts/` (~5k 行)

---

## 12. 联系与贡献

- 项目仓库：YangtzeDestoryLLM
- 配置文件：`configs/cfg.yaml`
- 日志目录：`logs/`
- 输出目录：`outputs/`

---

## 13. 关键技术亮点（答辩/论文写作参考）

### 13.1 工程鲁棒性设计

| 特性 | 实现 | 价值 |
|------|------|------|
| **LLM 多 Key 轮换** | `kg/llm_core.py` 检测 429 自动切换 | 长时批处理不中断 |
| **JSON 强制输出** | json_mode + fence 剥离 + 子串兜底 | 避免解析失败导致流程中断 |
| **断点续跑** | P4/P5 检测已处理文档自动跳过 | 支持 2-3 小时级别批处理 |
| **结构清洗** | `_sanitize_p5_result()` 补齐字段/类型回退 | 保证下游评测/入库不崩溃 |

### 13.2 质量控制机制

| 机制 | 原论文 | 本项目 | 优势 |
|------|--------|--------|------|
| **去重** | OpenAI Embedding | BGE-768维 + 阈值0.7 | 本地推理，成本低，语言匹配 |
| **质量过滤** | 专家审核（8%/10%拒绝率） | 支持度聚合 (min_support) | 自动化，可追溯证据来源 |
| **冲突检测** | 推理器 + 人工 | 悬空/重复/孤立检测 | 生成诊断报告，支持抽查 |
| **约束抽取** | 人工后处理 | TBox 约束 + 标记 `_invalid_predicate` | 保留错误信息用于分析 |

### 13.3 可复现性保障

```
每个阶段产出独立 JSON 文件 → 版本可追溯
支持 --dry-run → 预览执行计划
日志即时刷新 → 长时运行可监控
冲突/去重报告 → 人工抽查有依据
```

---

## 14. 常见问题（FAQ）

### Q1: 如何处理 LLM 限流？
系统内置多 Key 轮换机制，遇到 429 自动切换，冷却后恢复。配置多个 Key：
```bash
OPENAI_API_KEYS=key1,key2,key3
```

### Q2: P4 中断后如何继续？
P4 支持断点续跑，已处理的文档会跳过：
```bash
python scripts/run_p4_batch.py --corpus-jsonl data/p4_only.jsonl
# 自动检测 p4_suggestions.jsonl，跳过已处理文档
```

### Q3: 如何调整去重阈值？
在 `configs/cfg.yaml` 中修改：
```yaml
p4:
  dedup_threshold: 0.7  # 调整此值
dedup_schema:
  threshold: 0.7        # P2/P3 去重阈值
```

### Q4: 如何添加新的语料来源？
1. 将文件放入 `data/corpus_for_kg/raw_all/`
2. 运行清洗：`python tools/corpus_cleaner.py --input <dir>`
3. 运行过滤：`python tools/filter_corpus_light.py`
4. 运行划分：`python tools/build_manifest.py`

### Q5: 为什么 P4 增强后 IR 降低？
P4 新增类可能缺少有效 `parent` 引用（例如填了不存在的父类名），导致子类边减少。解决方案：
- 在 P4 Prompt 中明确要求 parent 必须来自现有类集合
- 在 P3 后人工检查并补全 class_hierarchy
- 在论文中作为"局限性与未来工作"说明

### Q6: 如何切换不同 LLM 提供商？
```bash
# OpenAI
python scripts/run_cq_pipeline.py --provider openai --model gpt-4o-mini

# 智谱 AI
python scripts/run_cq_pipeline.py --provider zhipu --model glm-4.5-flash

# Gemini（通过代理）
python scripts/run_cq_pipeline.py --provider openai --model gemini-1.5-flash
```

### Q7: 输出文件命名规则？
- 带时间戳：`p4_tbox_augmented_s2_allow1_20251212_154455.json`
- 格式：`<阶段>_<描述>_s<support>_allow<0|1>_<时间戳>.json`
- 便于对比不同配置版本

### Q8: 如何查看 LLM 调用日志？
```bash
# 实时监控（P4 批处理）
tail -f logs/kg_tbox/p4_batch_*.log

# 查看错误
grep ERROR logs/kg_tbox/*.log
```

### Q9: Neo4j 连接失败怎么办？
系统优雅降级，Neo4j 不可用时会自动使用 NetworkX 内存图。检查配置：
```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your_password
```

### Q10: 如何导出 OWL 格式本体？
当前 TBox 以 JSON 表示，可通过映射工具转换：
```python
# 未来实现：kg/converters/json_to_owl.py
# 将 classes → owl:Class
# relations → owl:ObjectProperty
# attributes → owl:DatatypeProperty
# parent → rdfs:subClassOf
```

---

## 15. 项目演进路线图

### 已完成 ✅
- [x] CQ 驱动流水线 (P1-P5)
- [x] 多 LLM 支持（OpenAI/智谱/Gemini）
- [x] 支持度聚合与冲突检测
- [x] 向量去重（BGE-768维）
- [x] OntoQA + CQ 覆盖度评估
- [x] GraphRAG 问答引擎

### 进行中 🚧
- [ ] 实体标准化（地名/术语别名归一）
- [ ] P4 父类对齐/补全机制
- [ ] 抽取 F1 评测自动化
- [ ] 问答对比实验（消融分析）

### 计划中 📅
- [ ] JSON TBox → OWL 自动转换
- [ ] Neo4j 可视化界面
- [ ] 在线 Demo 系统
- [ ] 更多领域迁移（地震/野火/公共卫生）

---

## 16. 致谢与参考

### 借鉴的开源项目
- **MunerU**: PDF 解析工具
- **PaddleOCR**: 中文 OCR 引擎
- **BGE**: 中文 Sentence Embedding
- **NetworkX**: 图数据结构
- **jieba**: 中文分词

### 参考论文
- [洪水本体构建的半自动化框架](txts/survey/water_summary.md)
- 更多参见 [方法对比文档](txts/project/survey/yangtze_method_vs_water_paper.md)


---

## 17. 与 Code-Rule.md 配合使用

本项目有两份重要文档：
- **PROJECT_OVERVIEW.md**（本文档）：项目全景指南，面向理解和使用
- **[Code-Rule.md](/.qoder/rules/Code-Rule.md)**：代码规范与踩坑总结，面向开发和调试

### 17.1 典型协作场景

| 场景 | 推荐读取顺序 |
|------|-------------|
| **首次了解项目** | PROJECT_OVERVIEW 30秒速览 → 快速开始 |
| **准备开发贡献** | PROJECT_OVERVIEW 核心模块 → Code-Rule 代码规范 |
| **OCR/Paddle 报错** | Code-Rule OCR 踩坑总结 → PROJECT_OVERVIEW 常见问题 |
| **环境安装失败** | PROJECT_OVERVIEW 常见环境问题 → Code-Rule 运行须知 |
| **代码提交前** | Code-Rule 代码规范 → Git 注释使用中文 |

### 17.2 Code-Rule.md 重点内容摘要

```yaml
运行环境:
  conda环境: YangtzeLLM
  conda路径: /home/zjx/miniconda3/bin/python
  激活命令: conda activate YangtzeLLM  # 或 source activate YangtzeLLM

OCR服务关键点:
  - 避免在 ~/.bashrc 写死 LD_LIBRARY_PATH（会导致 NCCL 冲突）
  - PaddleOCR 接口 file 字段支持 URL 或 Base64，不支持本地路径
  - 代理会劫持 localhost 连接，需设置 NO_PROXY
  - 使用 --skip-existing 和 --retry-failed 支持断点续跑

代码规范:
  - 命名: snake_case（变量/函数）、PascalCase（类）、UPPER_CASE（常量）
  - 格式: 4空格缩进，每行≤120字符
  - 注释: 使用中文，说明"为什么"而非"是什么"
  - Git提交: 使用中文注释
```

---

## 18. 代码规模与技术栈

### 18.1 代码规模统计

```
Python 源文件：67+ 个
代码行数：约 30,000 行（含注释与文档字符串）
核心模块分布：
  - kg/          ~5,000 行（本体构建与 LLM 调用）
  - tools/       ~10,000 行（语料处理与评估）
  - scripts/     ~5,000 行（运行脚本与实验）
  - retrievers/  ~3,000 行（检索器实现）
  - experiments/ ~2,000 行（对比实验）
```

### 18.2 技术栈

| 层次 | 技术 | 用途 |
|------|------|------|
| **LLM 调用** | OpenAI API / 智谱 API / Gemini API | 多阶段文本生成 |
| **向量检索** | SentenceTransformer (BGE-768维) | 去重 + CQ 覆盖度 |
| **文本检索** | jieba + BM25 | 种子实体召回 |
| **图存储** | NetworkX / Neo4j | 内存图 / 持久化 |
| **文档解析** | PaddleOCR / MunerU | PDF → Markdown |
| **配置管理** | YAML + python-dotenv | 多环境配置 |
| **数据格式** | JSON / JSONL | 中间产物与评测 |
| **评估** | 自研指标工具 | OntoQA + CQ 覆盖 + F1 |

### 18.3 依赖项精选（requirements.txt 节选）

```txt
# LLM 相关
openai>=1.0.0
zhipuai>=2.0.0
google-generativeai

# NLP 基础
jieba
sentence-transformers
transformers>=4.30.0

# 图处理
networkx>=3.0
neo4j>=5.0.0  # 可选

# 向量与检索
faiss-cpu  # 或 faiss-gpu
numpy
scipy

# 数据处理
pandas
pyyaml
python-dotenv
tqdm

# OCR（可选）
paddlepaddle
paddleocr
```

---

## 19. 项目里程碑

### 2024年
- **9月**：项目立项，确定 CQ 驱动方法论
- **10月**：完成 P1-P3 流水线，初步验证可行性
- **11月**：实现 P4 批处理与支持度聚合机制
- **12月**：完成 P5 TBox 约束抽取，建立评估体系

### 2025年
- **1月**：优化去重算法，对齐论文阈值 0.7
- **2月**：增加冲突检测与诊断报告
- **3月**（预期）：完成论文写作与实验汇总
- **4月**（预期）：答辩与系统演示
- **5月**（预期）：开源发布

---

## 20. 贡献者与致谢

### 核心开发
- 你（zjx）：项目负责人，系统架构与核心代码

### 指导老师
- （待补充）

### 技术支持
- GitHub Copilot：代码编写辅助
- Claude：文档生成与逻辑优化

### 数据来源
- 长江水利委员会：年鉴与公报
- 中国气象局：灾害事件记录
- 国家防汛抗旱总指挥部：预案与法规
- 学术论文库：相关研究文献

---

## 21. 许可证与引用

### 许可证
（待添加，建议使用 MIT 或 Apache 2.0）

### 引用格式（论文发表后更新）

```bibtex
@mastersthesis{zjx2025yangtze,
  title={基于CQ驱动的长江流域水旱灾害知识图谱构建与问答系统},
  author={zjx},
  school={（学校名称）},
  year={2025},
  type={硕士学位论文}
}
```

---

## 22. 相关资源链接

- **项目仓库**: （GitHub 链接待添加）
- **在线文档**: （ReadTheDocs 待部署）
- **Demo 系统**: （待开发）
- **参考论文**: [水旱灾害本体构建综述](txts/survey/water_summary.md)
- **方法对比**: [本项目 vs 原论文详细对比](txts/project/survey/yangtze_method_vs_water_paper.md)
- **数据集**: （Zenodo 发布计划中）

---

## 附录 A: 关键脚本用法速查

### A.0 全流程脚本 (run_full_pipeline.sh)

```bash
# 完整流程（清洗 → 过滤 → P1-P5 → 评估）
./scripts/run_full_pipeline.sh

# 常用选项
--start-step p3      # 从 P3 开始
--only-step p5       # 仅运行 P5
--skip-clean         # 跳过清洗
--skip-filter        # 跳过过滤
--dry-run            # 试运行（仅显示命令）

# 示例：从 P4 开始，试运行
./scripts/run_full_pipeline.sh --start-step p4 --dry-run
```

### A.1 语料预处理脚本

```bash
# 1. 清洗与切分（PDF/TXT → JSONL）
python tools/corpus_cleaner.py \
    --input data/raw_corpus \
    --output data/corpus_for_kg/handled_all_kg_corpus

# 2. 轻过滤（基于规则 + LLM 判定）
python tools/filter_corpus_light.py \
    --corpus-dir data/corpus_for_kg/handled_all_kg_corpus \
    --output data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl

# 3. 构建评测池（分层抽样）
python tools/build_eval_pool.py \
    --light-pool data/corpus_for_kg/p5_corpus_filtered/light_pool.jsonl \
    --output-dir data/p5_eval_pool \
    --stratify-by topic_label
```

### A.2 OCR 处理（PaddleOCR Server 模式）

```bash
# 启动 PaddleOCR Serving（需提前安装）
# 参考：https://github.com/PaddlePaddle/PaddleOCR

# 批量处理 PDF（并发 + 缓存 + 断点续跑）
python tools/paddle_ocr.py \
    --runner server \
    --api-url http://127.0.0.1:8123/layout-parsing \
    --input-dir ocr_test/pdf \
    --output-dir ocr_test/output \
    --workers 4 \
    --skip-existing \
    --retry-failed

# 关键参数说明
--file-mode auto      # 优先 base64，避免路径解析错误
--proxy-mode auto     # 本地服务禁用代理
--timeout-secs 1800   # 长文档超时时间
--cache-file logs/ocr/paddleocr_cache.jsonl  # 缓存文件
```

### A.3 批量评估脚本

```bash
# 对比多个 TBox 版本
python tools/ontoqa_metrics.py \
    outputs/cq_pipeline/final/p2_tbox*.json \
    outputs/cq_pipeline/final/p4_tbox*.json \
    --output outputs/ontoqa/comparison.md

# 计算 CQ 覆盖度（多阈值）
python tools/cq_coverage.py \
    --tbox-file outputs/cq_pipeline/final/p4_tbox_enhanced.json \
    --cq-file outputs/cq_pipeline/final/p1_cqs.json \
    --thresholds 0.3 0.4 0.5 0.6 0.7 0.8 0.9

# 抽取质量评估（需要黄金标注）
python tools/abox_metrics.py \
    --gold data/p5_eval_pool/gold_annotations.json \
    --pred outputs/p5_batch_results.jsonl \
    --mode relaxed
```

---

## 附录 B: Prompt 模板速览

### A.1 P1 CQ 生成 Prompt

```
角色：本体工程师专家
任务：生成 {n_cq} 条高层次能力问题
约束：
- 问题可通过结构化查询回答
- 覆盖风险管理周期不同阶段
- 分类：灾害事件分析/致灾因子诊断/灾害影响评估/...
输出：JSON {"cqs": [{id, question, category}, ...]}
```

### A.2 P2 CQ→TBox Prompt

```
角色：知识图谱本体工程师
输入：CQ 列表
任务：
1. 归纳实体类（含 parent 继承关系）
2. 归纳关系（domain → range）
3. 归纳属性（owner.name: value_type）
输出：JSON {"classes": [...], "relations": [...], "attributes": [...]}
```

### A.3 P4 增强 Prompt

```
角色：水旱灾害知识图谱本体工程师
输入：现有 TBox + 待分析文本
任务：识别尚未覆盖的候选类/关系/属性
输出：JSON {"suggestions": [{type, name, cn_name, definition, evidence}, ...]}
```

### A.4 P5 抽取 Prompt

```
角色：知识图谱构建助手
输入：TBox + 待抽取文本（含上下文标记）
任务：
1. 识别灾害事件（event_type 必须来自 TBox）
2. 抽取三元组（predicate 必须来自 TBox）
输出：JSON {"events": [...], "triples": [...]}
```

---

## 附录 B: 关键数据结构

### B.1 CQ 结构

```json
{
  "id": "1",
  "question": "1990年以来长江流域发生过哪些重大洪水事件？",
  "category": "灾害事件分析"
}
```

### B.2 ClassDef 结构

```json
{
  "name": "FloodEvent",
  "cn_name": "洪水事件",
  "definition": "特指长江干流或支流发生的明显洪水过程",
  "examples": ["1998年长江特大洪水"],
  "parent": "DisasterEvent"
}
```

### B.3 RelationDef 结构

```json
{
  "name": "has_cause",
  "cn_name": "致灾因子",
  "domain": "DisasterEvent",
  "range": "HazardFactor",
  "definition": "描述导致该灾害发生的主要因素",
  "functional": false
}
```

### B.4 Event 结构

```json
{
  "event_id": "evt_1998_01",
  "event_type": "FloodEvent",
  "name": "1998年长江特大洪水",
  "time": {"start_time": "1998-06-01", "end_time": "1998-09-01"},
  "space": {
    "main_stream": ["长江中下游干流"],
    "tributaries": ["洞庭湖", "鄱阳湖"],
    "provinces": ["湖北省", "湖南省", "江西省"]
  },
  "causes": ["持续性强降雨", "上游来水偏多"],
  "impacts": {
    "affected_population": "2.23亿人",
    "deaths": "4150人",
    "direct_economic_loss": "1660亿元"
  },
  "responses": [
    {"stage": "应急响应", "measures": ["启动防汛Ⅰ级应急响应"]}
  ]
}
```

### B.5 Triple 结构

```json
{
  "subject": "1998年长江特大洪水",
  "predicate": "has_cause",
  "object": "持续性强降雨",
  "event_id": "evt_1998_01",
  "evidence": "受流域范围内持续性强降雨影响..."
}
```

---

## 附录 C: 评估指标公式

### C.1 OntoQA 指标

| 指标 | 公式 | 含义 |
|------|------|------|
| RR (Relationship Richness) | P / (P + SC) | 非继承关系占比，越高表示语义关系越丰富 |
| IR (Inheritance Richness) | SC / C | 子类边与类数之比，越高表示层级越深 |
| AR (Attribute Richness) | A / C | 平均每类属性数 |

其中：
- C = 类数量
- P = 对象属性（关系）数量
- A = 数据属性数量
- SC = 子类关系数量

### C.2 CQ 覆盖度

```
Coverage(τ) = |{cq | max_sim(cq, TBox) >= τ}| / |CQ|
```

其中 `max_sim` 为 CQ 与 TBox 元素的最大余弦相似度。

### C.3 抽取 F1

```
Precision = |正确抽取| / |总抽取|
Recall = |正确抽取| / |标注总数|
F1 = 2 * P * R / (P + R)
```

支持 strict（完全匹配）和 relaxed（部分匹配）两种模式。

---

## 附录 D: 运行脚本参数速查

### D.1 run_cq_pipeline.py

```bash
--cfg              # 配置文件路径
--output-dir       # 输出目录
--start-step       # 起始阶段 (p1/p2/p3/p4/p5)
--only-stage       # 仅运行单个阶段
--provider         # LLM 提供商 (openai/zhipu/gemini)
--model            # 模型名称
--n-cq             # P1 生成 CQ 数量
--dedup-schema     # 是否去重
--corpus-jsonl     # P5 批量语料文件
--include-context  # P5 是否包含上下文
```

### D.2 run_p4_batch.py

```bash
--base-tbox        # 基线 TBox 路径
--corpus-jsonl     # 语料 JSONL 文件
--min-support      # 最低支持度
--allow-new-classes # 是否允许新增类
--merge-only       # 仅合并（跳过 LLM 调用）
--dedup-new        # 对新增元素去重
--conflict-report  # 冲突报告输出路径
--overwrite        # 覆盖已有建议
```

### D.3 p5_from_tbox.py

```bash
--tbox-file        # TBox 文件路径
--corpus-dir       # 语料目录
--corpus-jsonl     # 语料 JSONL 文件
--favor-existing   # 优先复用已有类
--normalize        # 实体标准化
--max-segments     # 最大处理片段数
```
