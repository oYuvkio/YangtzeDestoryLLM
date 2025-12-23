# 基于大语言模型与知识图谱的长江流域水旱灾害问答系统（YangtzeDestoryLLM）

> 最后更新：2025-12-23  
> 说明：本文档以当前代码实现与 `configs/cfg.yaml` 为准；方法对照与论文式描述见 `project/survey/my_method_comparison.md`、`txts/project/survey/yangtze_method_vs_water_paper.md`。

---

## 1. 项目定位

本项目面向“长江流域水旱灾害（洪水/干旱/枯水等）”硕士论文场景，构建端到端的 **KG‑RAG 问答系统**：

- **CQ（Competency Questions）驱动本体/模式（TBox）构建**：用 CQ 作为需求规范与评估载体，反推类/关系/属性。
- **在 TBox 约束下抽取实例（ABox）**：抽取统一结构的 `events/triples`，减少开放抽取噪声与“幻觉关系”。
- **将结构化知识用于 GraphRAG**：提供文本（BM25）/向量（SentenceTransformer）/图结构（多跳扩展）等检索组件；当前默认流程为 BM25 + 多跳子图扩展，将“可验证的三元组证据”组织进 Prompt 生成答案。

核心产物（论文可引用）：
- 多版本 TBox：`p2_tbox_init.json`、`p3_tbox_normalized*.json`、`p4_tbox_enhanced.json`
- TBox 约束 ABox：`p5_events.json` 或批量 `p5_batch_results.jsonl` + 汇总
- 评估报告：OntoQA（RR/IR/AR + 扩展结构指标）、CQ 覆盖度、ABox 抽取 F1、冲突报告

---

## 2. 端到端流程（语料 → TBox → ABox → QA）

### 2.1 数据准备与语料治理

面向“多源中文文档（PDF/TXT/新闻/年鉴/预案/论文）”，项目提供了可复用的语料治理工具链：

1. OCR（可选）：`tools/paddle_ocr.py`  
   - 批量 PDF → Markdown，支持断点续跑与缓存。
2. 清洗与切分：`tools/corpus_cleaner.py`  
   - PDF/TXT 多引擎解析；页眉页脚/目录/参考文献处理；语义感知分段；sidecar 元数据；并行与断点续跑。
3. 轻过滤 + LLM 质量判定（可选）：`tools/filter_corpus_light.py`  
   - 规则粗滤（汉字占比/异常字符/关键词）+ LLM 相关性判定；增量缓存；输出 `light_pool.jsonl`。
4. 三分法语料用途划分（P4/P5/EVAL）：`tools/build_manifest.py` + `filters/apply_manifest.py`  
   - 生成 `data/manifests/purpose_manifest.jsonl`，并导出：
     - `data/corpus_for_onto/p4_only.jsonl`（概念/制度/定义类语料，用于 schema 增强）
     - `data/corpus_for_kg/p5_only.jsonl`（事件事实语料，用于实例抽取/建图）
     - `data/p5_eval_pool/{pool,dev,test}.jsonl`（评测池）

### 2.2 CQ 驱动的 KG 构建流水线（P1–P5）

核心实现：`kg/cq_pipeline.py`；运行入口：`scripts/run_cq_pipeline.py`。

- P0 领域边界（输入）：`kg/cq_pipeline.py` 中 `DEMO_DOMAIN_DESC`（也可 `--domain-file` 替换）
- P1 CQ 生成：`generate_cqs()` → `outputs/cq_pipeline/final/p1_cqs.json`
- P2 初始 TBox 归纳：`cq_to_schema()` → `p2_tbox_init.json`（可选 `p2_tbox_init_dedup.json`）
- P3 TBox 规范化：`refine_schema()` + `normalize_tbox_with_p3()` →  
  - `p3_tbox_refinement.json`（别名/层级/辅助信息等）
  - `p3_tbox_normalized.json`（规范化 TBox；可选 `p3_tbox_normalized_dedup.json`）
  - `p3_conflicts.json`（模式冲突报告）
- P4 文献驱动增强：`run_p4_over_corpus()`（支持度聚合 `_support` + `min_support` 过滤；可选同义对齐/向量去重）→  
  - `p4_tbox_enhanced.json`、`p4_conflicts.json`
  - 大规模增强可用 `scripts/run_p4_batch.py`（聚合/冲突检测/多配置生成）
- P5 TBox 约束抽取：`extract_events()` →  
  - 单条：`p5_events.json`
  - 批量：`p5_batch_results.jsonl`（断点续跑）+ `p5_all_events.json` + `p5_all_triples.json` + `p5_batch_summary.json`
  - 也可用 `scripts/p5_from_tbox.py` 直接从 TBox 批量抽取（单文件/目录递归 + 断点续跑）

### 2.3 KG 存储与 GraphRAG 问答

- NetworkX（内存图）：`kg/build_from_json.py`（JSONL → `nx.DiGraph`）
- Neo4j（持久化）：`kg/neo4j_adapter.py`（结构化事件 JSONL 导入图数据库）
- 检索器：
  - `retrievers/text_retriever.py`：BM25（jieba 分词）
  - `retrievers/vector_retriever.py`：SentenceTransformer 向量检索（语义召回）
  - `retrievers/graph_retriever.py`：多跳扩展（旧 API：`hop_subgraph/format_subgraph`；新 API：`GraphRetriever`）
- GraphRAG 引擎：`kg/query.py`  
  - 当前实现：BM25 找种子 → 多跳子图扩展 → `kg/llm_core.py:draft_answer_with_graph()` 生成答案

---

## 3. 关键工程设计（与代码一致）

### 3.1 统一 LLM 调用（OpenAI 兼容接口）

实现：`kg/llm_core.py`。

- `OPENAI_API_KEYS` 多 Key 轮换（429 自动切换 + 冷却恢复），并支持 `OPENAI_API_KEY` 单 Key 向后兼容
- `request_mode=sdk/post/auto`：可在 SDK 不可用时退化为 HTTP POST
- 自动识别部分第三方 API 特性：必要时禁用 `response_format`（如 LongCat/Gemini 代理）
- `close()` 与上下文管理器：避免长时间批处理时连接资源泄露

### 3.2 JSON 强制输出与鲁棒解析

实现：`kg/cq_pipeline.py:LLMJsonClient`。

- 强制 JSON 输出（用于 P1–P5 的结构化结果）
- fence 剥离（```json ...```）+ 子串兜底截取，提升长时运行稳定性

### 3.3 模式去重 / 同义对齐 / 冲突检测 / 实体标准化

- Embedding 去重：`kg/utils/deduplication.py:EmbeddingDeduplicator`（类/关系）
- 同义对齐：`kg/utils/schema_alignment.py:SchemaAligner`（可扩展同义表）
- 冲突检测：`kg/utils/conflict_detection.py`（domain/range/owner 悬空、同名多签名、孤立类、空定义等）
- 实体标准化：`kg/utils/entity_linking.py`（地名/灾害术语归一，用于抽取后处理与评测宽松匹配）

---

## 4. 评估体系与实验入口

- TBox（OntoQA + 扩展结构指标）：
  - `tools/tbox_metrics.py`（RR/IR/AR 的鲁棒实现）
  - `tools/ontoqa_metrics.py`（批量对比、多版本 delta、层级深度/分支度/循环检测等）
- CQ 覆盖度：`tools/cq_coverage.py`（BGE 句向量，多阈值统计）
- ABox 抽取质量：`tools/abox_metrics.py`（Event F1、Triple F1 strict/relaxed、TBox consistency）
- 一键评估：`scripts/run_full_evaluation.py`（生成评估报告 JSON）
- 对比/消融实验：`experiments/`（去重策略、P5 对比、QA 对比、ablation）

---

## 5. 运行指南（常用入口）

### 5.1 环境与配置

- Conda 环境：`conda activate YangtzeLLM`
- 统一配置：`configs/cfg.yaml`（路径、LLM、embedding、P4/P5、去重阈值、三分法规则等）
- 可选大盘缓存/模型目录：`setup_storage_env.sh`（细节参考 `STORAGE_CONFIG.md`）

### 5.2 常用命令

1) CQ→TBox→抽取（P1–P5，单条/批量）：
```bash
python scripts/run_cq_pipeline.py --cfg configs/cfg.yaml
```

2) P4 大规模语料增强（聚合 + 冲突报告）：
```bash
python scripts/run_p4_batch.py --base-tbox outputs/cq_pipeline/final/p3_tbox_normalized.json --corpus-jsonl data/corpus_for_onto/p4_only.jsonl
```

3) 仅从 TBox 启动 P5 抽取（适合重复抽取/批量抽取）：
```bash
python scripts/p5_from_tbox.py --tbox-file outputs/cq_pipeline/final/p4_tbox_enhanced.json --corpus-dir data/raw_paragraphs_for_p5
```

4) 一键评估：
```bash
python scripts/run_full_evaluation.py --gold <gold.json> --preds <pred.json>
```

5) 全流程脚本（清洗→过滤→P1–P5）：
```bash
./scripts/run_full_pipeline.sh
```

---

## 6. 当前代码规模与目录结构（以仓库现状为准）

代码规模（仅统计 `.py`）：
- Python 源文件：67 个
- 代码行数：约 29k（含注释与文档字符串）

目录结构（节选）：
```
YangtzeDestoryLLM/
├── configs/                # cfg.yaml 全局配置
├── data/                   # 语料与中间产物（可按需映射到大盘）
├── experiments/            # 对比/消融实验
├── filters/                # manifest 导出工具
├── kg/                     # CQ→TBox→抽取 + 存储/问答核心
├── retrievers/             # BM25/向量/图检索
├── scripts/                # 运行入口与批处理脚本（P1-P5、P4 batch、评估、验证）
├── tools/                  # 语料清洗/过滤/评估等工具脚本
├── tests/                  # LLM 调用与 key 轮换等测试脚本
└── txts/                   # 论文与项目文档（方法对照/笔记等）
```

---

## 7. 论文写作映射（简版）

可在论文中明确对应“方法—实现—评估”的闭环：

1) CQ 驱动 schema：P1–P3（需求规范 → 归纳 → 规范化/去重/冲突检测）  
2) 语料增强：P4（支持度聚合 + 过滤 + 增量合入）  
3) TBox 约束抽取：P5（星型结构/谓词白名单 + 输出清洗 + 一致性标记）  
4) KG‑RAG 应用：GraphRAG（BM25/向量/多跳扩展 → 证据三元组 → 答案生成）  
5) 评估体系：OntoQA + CQ 覆盖度 + ABox 抽取 F1 + 冲突报告
