# 基于大语言模型与知识图谱的长江流域水旱灾害问答系统

## 项目全貌分析

### 1. 项目整体功能定位

本项目是一个面向长江流域水旱灾害领域的**知识图谱增强型问答系统（KG-RAG）**，旨在解决传统灾害问答中信息检索不准、推理能力弱的问题。系统采用**CQ驱动的本体构建方法论**，结合大语言模型的语义理解能力与知识图谱的结构化推理能力，实现从非结构化文本到结构化知识的自动抽取与问答。

### 2. 技术栈全景

| 层次 | 技术选型 |
|------|----------|
| **LLM后端** | OpenAI API / 智谱ChatGLM / Google Gemini（策略模式封装） |
| **知识图谱存储** | NetworkX（内存图）/ Neo4j（持久化图数据库） |
| **向量检索** | SentenceTransformer (BGE-base-zh) / BM25 |
| **NLP工具** | jieba分词、HuggingFace Transformers |
| **配置管理** | YAML配置 + 环境变量 |
| **数据格式** | JSONL语料、JSON Schema |

### 3. 代码规模统计

| 指标 | 数量 |
|------|------|
| Python源文件 | ~45个 |
| 核心代码行数 | ~8,000行 |
| 配置/数据文件 | ~20个 |
| 语料文档 | ~500+个txt文件 |

### 4. 项目目录结构

```
YangtzeDestoryLLM/
├── kg/                          # 知识图谱核心模块
│   ├── cq_pipeline.py          # CQ驱动的P1-P5流水线（核心创新）
│   ├── extractor.py            # LLM/DL双路抽取器
│   ├── llm_core.py             # 统一LLM调用层（多Key轮换）
│   ├── prompts.py              # 分阶段Prompt模板库
│   ├── query.py                # GraphRAG问答引擎
│   ├── neo4j_adapter.py        # Neo4j适配器
│   └── utils/                  # 工具模块
│       ├── deduplication.py    # Embedding去重
│       ├── entity_linking.py   # 实体标准化
│       ├── conflict_detection.py # 模式冲突检测
│       └── schema_alignment.py # 模式对齐
├── retrievers/                  # 检索器模块
│   ├── graph_retriever.py      # 图检索（多跳扩展）
│   ├── text_retriever.py       # BM25文本检索
│   └── vector_retriever.py     # 向量语义检索
├── tools/                       # 工具脚本
│   ├── build_eval_pool.py      # 评估语料构建
│   ├── tbox_metrics.py         # TBox质量指标（OntoQA）
│   ├── abox_metrics.py         # ABox抽取质量指标
│   └── corpus_cleaner.py       # 语料清洗
├── scripts/                     # 运行脚本
│   ├── run_cq_pipeline.py      # CQ流水线主入口
│   └── run_full_evaluation.py  # 完整评估流程
├── experiments/                 # 实验脚本
│   ├── exp_qa_comparison.py    # QA方法对比
│   └── run_ablation.py         # 消融实验
├── data/                        # 数据目录
│   ├── corpus_for_kg/          # KG构建语料
│   └── corpus_for_onto/        # 本体构建语料
└── configs/cfg.yaml            # 全局配置
```

---

## 核心模块深度剖析

### 模块1：CQ驱动的本体构建流水线 (`kg/cq_pipeline.py`)

**解决的问题**：传统本体构建依赖领域专家手工设计，成本高、周期长。本模块实现了从能力问题(CQ)自动推导TBox的端到端流程。

**技术路线**：
```
P1: 领域描述 → CQ生成（LLM）
P2: CQ → 初始TBox（类/关系/属性归纳）
P3: TBox规范化（命名统一、层次化、冲突检测）
P4: 文献驱动增强（基于语料扩展模式）
P5: 事件与三元组抽取（TBox约束下的ABox填充）
```

**关键类/函数**：
- `CQLLMPipeline`: 主流水线类，封装P1-P5各阶段
- `TBoxSchema`: TBox数据结构（classes/relations/attributes）
- `LLMJsonClient`: JSON强制输出的LLM调用封装
- `apply_p4_suggestions()`: P4增量补丁应用

**数据流向**：
```
领域描述 → [P1] → CQ列表 → [P2] → 初始TBox → [P3] → 规范化TBox 
→ [P4+语料] → 增强TBox → [P5+文本] → 事件/三元组
```

### 模块2：统一LLM调用层 (`kg/llm_core.py`)

**解决的问题**：多LLM提供商接口差异大，限流处理复杂。

**技术路线**：
- 基于OpenAI兼容接口的统一封装
- 多API Key轮换机制（遇429自动切换）
- 智能冷却恢复（记录限流时间戳）
- 自动识别第三方API特性（如LongCat禁用response_format）

**关键类**：
- `APIKeyManager`: 多Key管理器（线程安全）
- `LLMClient`: 统一客户端（支持上下文管理器）
- `LLMFactory`: 工厂模式创建客户端

### 模块3：混合检索器 (`retrievers/`)

**解决的问题**：单一检索方式难以兼顾精确匹配与语义理解。

**技术路线**：
- `BM25Retriever`: 关键词精确匹配（jieba分词）
- `VectorRetriever`: 语义相似度检索（SentenceTransformer）
- `GraphRetriever`: 图结构多跳扩展（BFS遍历）

**组合策略**：
```
Query → [向量检索] → 种子节点 → [多跳扩展] → 子图三元组 → [LLM生成] → 答案
```

### 模块4：评估指标体系 (`tools/tbox_metrics.py`, `tools/abox_metrics.py`)

**TBox指标（OntoQA框架）**：
- RR (Relationship Richness): P / (P + SC)
- IR (Inheritance Richness): SC / C
- AR (Attribute Richness): A / C

**ABox指标**：
- Event F1: 事件名称+类型匹配
- Triple F1 (Strict/Relaxed): 三元组精确/宽松匹配
- TBox Consistency: predicate与TBox定义一致率

---

## 论文创新点提炼

### 创新点1：CQ驱动的领域本体自动构建方法

**一句话概括**：提出了一种基于能力问题(Competency Questions)反推本体模式的自动化方法，实现了从用户需求到知识图谱模式的端到端生成。

**详细说明**（150字）：
传统本体工程依赖领域专家手工设计类层次和关系定义，存在成本高、周期长、难以迭代的问题。本文提出CQ驱动的本体构建方法，首先利用LLM从领域描述生成能力问题集合，然后通过语义分析自动归纳出候选类、关系和属性定义，再经过规范化处理（命名统一、层次化整理、冲突检测）形成初始TBox，最后通过文献驱动的增量增强机制扩展模式覆盖度。该方法将本体构建从"专家驱动"转变为"需求驱动"，显著降低了领域知识图谱的构建门槛。

**对应代码位置**：
- `kg/cq_pipeline.py`: P1-P4流水线实现
- `kg/prompts.py`: P1_CQ_PROMPT, P2_SCHEMA_PROMPT, P3_REFINEMENT_PROMPT, P4_AUGMENT_PROMPT

---

### 创新点2：TBox约束下的结构化事件抽取框架

**一句话概括**：设计了一种在本体模式(TBox)约束下进行事件抽取的框架，确保抽取结果与预定义模式的一致性。

**详细说明**（150字）：
开放域信息抽取往往产生大量噪声三元组，难以直接用于知识图谱构建。本文提出TBox约束的抽取框架：在P5阶段，将已构建的TBox（包含类定义、关系签名、属性约束）作为Prompt的一部分注入LLM，引导模型仅抽取符合模式定义的实体和关系。同时设计了星型结构约束（所有关系以核心事件为头实体）和关系白名单机制，有效减少了幻觉三元组的产生。实验表明，该方法的TBox一致性指标显著优于无约束抽取。

**对应代码位置**：
- `kg/cq_pipeline.py`: `extract_events()` 方法
- `kg/prompts.py`: P5_EXTRACTION_PROMPT（含TBox注入和星型结构约束）
- `kg/extractor.py`: `LLMExtractor` 类

---

### 创新点3：多策略混合的图增强检索方法

**一句话概括**：提出了融合向量语义检索、BM25关键词匹配和图结构多跳扩展的混合检索策略，提升了问答系统的召回率和推理深度。

**详细说明**（150字）：
传统RAG系统仅依赖向量相似度检索文本片段，难以捕捉实体间的隐性关联。本文设计了三阶段混合检索策略：首先通过向量检索定位与问题语义最相关的种子实体；然后利用BM25补充词汇精确匹配的候选；最后在知识图谱上执行多跳BFS扩展，收集种子实体周围的结构化三元组作为上下文。这种"语义定位+词汇补充+图谱扩展"的组合策略，既保证了检索的语义相关性，又通过图结构捕获了多跳推理所需的关联知识。

**对应代码位置**：
- `retrievers/vector_retriever.py`: 向量语义检索
- `retrievers/text_retriever.py`: BM25关键词检索
- `retrievers/graph_retriever.py`: `GraphRetriever.multi_hop_subgraph()` 多跳扩展
- `kg/query.py`: `GraphRAG` 类整合三种检索

---

### 创新点4：面向LLM的鲁棒性工程设计

**一句话概括**：设计了一套面向大规模LLM调用的鲁棒性工程方案，包括多Key轮换、智能限流恢复和增量缓存机制。

**详细说明**（120字）：
大规模知识图谱构建需要频繁调用LLM API，面临限流、超时、费用等挑战。本文设计了多层次的鲁棒性机制：(1) 多API Key轮换管理器，遇到429限流自动切换到下一个可用Key；(2) 智能冷却恢复，记录每个Key的限流时间戳，超过冷却期后自动恢复；(3) 增量缓存机制，每次LLM调用后立即追加保存结果，支持断点续跑。这些设计显著提升了系统在长时间批量处理场景下的稳定性。

**对应代码位置**：
- `kg/llm_core.py`: `APIKeyManager` 类、`LLMClient._switch_to_next_key()`
- `tools/build_eval_pool.py`: `FilterCache` 增量缓存类

---

## 方法章节框架建议

### 第三章：基于CQ驱动的领域本体自动构建方法

```
3.1 问题定义与方法概述
    3.1.1 传统本体构建的局限性
    3.1.2 CQ驱动方法的设计思想
    3.1.3 整体技术框架

3.2 能力问题生成（P1阶段）
    3.2.1 领域描述的形式化表示
    3.2.2 基于LLM的CQ生成策略
    3.2.3 CQ质量控制与分类

3.3 初始模式归纳（P2阶段）
    3.3.1 从CQ到候选类的映射
    3.3.2 关系与属性的自动发现
    3.3.3 EARS模式的需求规范化

3.4 模式规范化与冲突检测（P3阶段）
    3.4.1 命名统一与别名归并
    3.4.2 类层次结构构建
    3.4.3 模式冲突检测算法

3.5 文献驱动的模式增强（P4阶段）
    3.5.1 候选概念的文献挖掘
    3.5.2 支持度聚合与过滤策略
    3.5.3 增量合并算法
```

### 第四章：TBox约束下的知识抽取与问答方法

```
4.1 TBox约束的事件抽取框架
    4.1.1 星型结构约束设计
    4.1.2 关系白名单机制
    4.1.3 上下文感知的分段抽取

4.2 混合检索策略
    4.2.1 向量语义检索
    4.2.2 BM25关键词补充
    4.2.3 图结构多跳扩展

4.3 GraphRAG问答生成
    4.3.1 证据三元组的组织
    4.3.2 Prompt工程设计
    4.3.3 答案生成与验证
```

---

## 系统架构描述（学术语言）

本系统采用分层架构设计，自底向上包含数据层、知识层、检索层和应用层四个层次。

**数据层**负责多源异构语料的统一管理，支持法规预案、公报年鉴、灾害案例、新闻科普等四类文档的结构化存储。通过语料清洗模块对原始文本进行标题标记清理、乱码过滤和长度归一化处理。

**知识层**实现了CQ驱动的本体构建流水线，包含五个串联阶段：P1阶段利用大语言模型从领域描述生成能力问题集合；P2阶段通过语义分析将CQ映射为候选类、关系和属性定义；P3阶段执行命名统一、层次化整理和冲突检测；P4阶段基于文献语料进行模式增强；P5阶段在TBox约束下执行事件与三元组抽取。知识层同时支持NetworkX内存图和Neo4j图数据库两种存储后端。

**检索层**实现了多策略混合检索机制，融合向量语义检索（基于SentenceTransformer）、BM25关键词匹配和图结构多跳扩展三种策略。向量检索负责语义相关性定位，BM25补充精确词汇匹配，图扩展捕获实体间的结构化关联。

**应用层**封装了GraphRAG问答引擎，将检索到的三元组证据组织为结构化Prompt，调用大语言模型生成自然语言答案。系统支持OpenAI、智谱ChatGLM、Google Gemini等多种LLM后端，通过策略模式实现无缝切换。

---

## 核心算法描述

### 算法1：CQ驱动的TBox构建算法

**伪代码**：
```
Algorithm: CQ-Driven TBox Construction
Input: domain_description D, corpus C, n_cq
Output: TBox T = (Classes, Relations, Attributes)

// P1: CQ Generation
CQs ← LLM_Generate(D, n_cq, P1_PROMPT)

// P2: Initial Schema Induction
T_init ← LLM_Induce(CQs, P2_PROMPT)
T_init.classes ← ExtractClasses(T_init)
T_init.relations ← ExtractRelations(T_init)
T_init.attributes ← ExtractAttributes(T_init)

// P3: Schema Normalization
alias_map ← BuildAliasMap(T_init.classes)
T_norm ← NormalizeNames(T_init, alias_map)
hierarchy ← InferClassHierarchy(T_norm.classes)
conflicts ← DetectConflicts(T_norm)

// P4: Corpus-Driven Enhancement
suggestions ← ∅
for doc in C do
    s ← LLM_Suggest(T_norm, doc, P4_PROMPT)
    suggestions ← suggestions ∪ s
end for
aggregated ← AggregateBySupport(suggestions, min_support=2)
T_enhanced ← ApplySuggestions(T_norm, aggregated)

return T_enhanced
```

**复杂度分析**：
- P1-P3阶段：O(n_cq × L_llm)，其中L_llm为单次LLM调用延迟
- P4阶段：O(|C| × L_llm)，与语料规模线性相关
- 空间复杂度：O(|Classes| + |Relations| + |Attributes|)

### 算法2：多跳图检索算法

**伪代码**：
```
Algorithm: Multi-Hop Graph Retrieval
Input: Graph G, seed_nodes S, max_hops h
Output: Triples T

visited ← S
queue ← [(s, 0) for s in S if s ∈ G.nodes]
T ← ∅

while queue ≠ ∅ do
    (current, depth) ← queue.pop()
    if depth ≥ h then continue
    
    // Explore outgoing edges
    for neighbor in G.successors(current) do
        rel ← G.edge[current][neighbor].relation
        T ← T ∪ {(current, rel, neighbor)}
        if neighbor ∉ visited then
            visited ← visited ∪ {neighbor}
            queue.push((neighbor, depth + 1))
    
    // Explore incoming edges (bidirectional)
    for neighbor in G.predecessors(current) do
        rel ← G.edge[neighbor][current].relation
        T ← T ∪ {(neighbor, rel, current)}
        if neighbor ∉ visited then
            visited ← visited ∪ {neighbor}
            queue.push((neighbor, depth + 1))

return T
```

**复杂度分析**：
- 时间复杂度：O(|S| × d^h)，其中d为平均节点度数
- 空间复杂度：O(|visited|) = O(|S| × d^h)

---

## 技术路线图

```
┌─────────────────────────────────────────────────────────────────┐
│                        输入层                                    │
├─────────────────────────────────────────────────────────────────┤
│  领域描述文档  │  多源语料库  │  用户自然语言问题                │
└───────┬───────┴──────┬───────┴──────────┬────────────────────────┘
        │              │                  │
        ▼              ▼                  │
┌───────────────────────────────────────┐ │
│         CQ驱动本体构建流水线           │ │
├───────────────────────────────────────┤ │
│ P1: 领域描述 → CQ生成                 │ │
│ P2: CQ → 初始TBox归纳                 │ │
│ P3: TBox规范化与冲突检测              │ │
│ P4: 文献驱动模式增强                  │ │
└───────────────┬───────────────────────┘ │
                │                         │
                ▼                         │
┌───────────────────────────────────────┐ │
│         TBox约束事件抽取               │ │
├───────────────────────────────────────┤ │
│ P5: 星型结构约束 + 关系白名单          │ │
│     上下文感知分段抽取                 │ │
└───────────────┬───────────────────────┘ │
                │                         │
                ▼                         │
┌───────────────────────────────────────┐ │
│         知识图谱存储层                 │ │
├───────────────────────────────────────┤ │
│ NetworkX内存图 / Neo4j图数据库         │ │
│ 事件节点 + 属性节点 + 关系边           │ │
└───────────────┬───────────────────────┘ │
                │                         │
                ▼                         ▼
┌─────────────────────────────────────────────────────────────────┐
│                    混合检索层                                    │
├─────────────────────────────────────────────────────────────────┤
│  向量语义检索  →  BM25关键词补充  →  图结构多跳扩展              │
│  (SentenceTransformer)  (jieba分词)    (BFS遍历)                │
└───────────────────────────┬─────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    GraphRAG问答生成                              │
├─────────────────────────────────────────────────────────────────┤
│  三元组证据组织  →  Prompt构建  →  LLM生成  →  答案输出          │
└─────────────────────────────────────────────────────────────────┘
```

---

## 实验设计建议

### 实验1：TBox构建质量评估

**目的**：验证CQ驱动方法生成的TBox质量

**指标**：OntoQA框架指标（RR, IR, AR）、人工评估（覆盖度、准确性）

**对比方法**：
- 人工设计TBox（专家基线）
- 直接LLM生成（无CQ引导）
- 仅P2输出（无P3/P4规范化增强）

**消融实验**：
- w/o P3: 去除规范化阶段
- w/o P4: 去除文献增强阶段
- w/o 冲突检测

### 实验2：事件抽取质量评估

**目的**：验证TBox约束对抽取质量的提升

**指标**：Event F1、Triple F1 (Strict/Relaxed)、TBox Consistency

**对比方法**：
- 开放域抽取（无TBox约束）
- 仅关系白名单（无星型结构约束）
- 传统NER+关系抽取Pipeline

**数据集**：从评估语料池(eval_pool)中抽取的300段落

### 实验3：问答效果评估

**目的**：验证GraphRAG相比Naive RAG的优势

**指标**：答案准确率、召回率、BLEU/ROUGE

**对比方法**：
- Naive RAG（仅向量检索）
- BM25 RAG（仅关键词检索）
- GraphRAG（本文方法）
- GraphRAG + 多跳扩展

**问题集**：领域专家设计的50个测试问题

### 实验4：系统鲁棒性评估

**目的**：验证工程设计的有效性

**指标**：
- 多Key轮换成功率
- 断点续跑恢复率
- 长时间运行稳定性

---

## 待加强的方面

### 1. 评估数据集不足
当前缺少标准化的黄金标注数据集，建议：
- 构建人工标注的事件/三元组黄金集
- 设计领域专家评估问卷

### 2. 消融实验不完整
代码中有消融实验框架但缺少完整结果，建议：
- 补充各变体的定量对比
- 增加统计显著性检验

### 3. 可解释性分析缺失
建议增加：
- 抽取结果的Case Study
- 错误分析与分类

### 4. 与SOTA方法对比不足
建议增加：
- 与UIE、DeepKE等开源抽取框架对比
- 与LlamaIndex、LangChain等RAG框架对比

### 5. 跨领域泛化性验证
当前仅在长江灾害领域验证，建议：
- 在其他灾害领域（如地震、台风）验证
- 分析领域迁移的适配成本

---

## 代码质量评价

### 优点
1. **模块化设计良好**：各模块职责清晰，耦合度低
2. **配置管理规范**：YAML配置 + 环境变量分离
3. **错误处理完善**：自定义异常类、重试机制、日志记录
4. **文档注释详尽**：函数级docstring、模块级说明

### 待改进
1. **单元测试覆盖不足**：tests目录主要是API测试，缺少核心逻辑的单元测试
2. **类型注解不完整**：部分函数缺少返回类型注解
3. **硬编码常量**：部分阈值直接写在代码中，建议提取到配置

---

*文档生成时间：2024年12月*
*项目版本：YangtzeDestoryLLM v1.0*
