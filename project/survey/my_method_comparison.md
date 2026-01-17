# 「我的方法」论文式方法文档（对照《洪水本体构建的半自动化框架》）

> 对照论文：《洪水本体构建的半自动化框架》（以下简称“原论文”）  
> 我的项目：`YangtzeDestoryLLM`（长江流域水旱灾害 KG‑RAG 问答系统）  
> 核心代码：`kg/cq_pipeline.py`、`scripts/run_cq_pipeline.py`、`kg/prompts.py`、`kg/utils/*`、`retrievers/*`、`kg/query.py`  

---

## 0. 摘要

本项目面向长江流域水旱灾害领域，旨在构建一个“本体/知识图谱增强的大模型问答系统”，解决传统灾害问答在**检索不准、语义约束弱、跨段落推理能力不足**等问题。方法上，我参考原论文“CQ 驱动、人机协同、渐进式富集本体”的核心思想，设计并实现了一个**CQ→TBox→语料增强→TBox 约束 ABox 抽取→GraphRAG 问答**的端到端流水线。与原论文相比，我将“专家初始本体”改为“领域描述边界+LLM 归纳初始模式”，在模式规范化、文献增强与抽取阶段引入**冲突检测、支持度聚合、向量去重、星型结构/关系白名单约束、实体标准化**等鲁棒性设计，并进一步扩展到**混合检索+多跳图增强的 GraphRAG 应用**。项目产出包括 CQ 列表、分阶段 TBox（`p2/p3/p4_*.json`）、TBox 约束下的事件/三元组（`p5_events.json`）以及可在 NetworkX/Neo4j 上运行的 KG‑RAG 问答系统。

---

## 1. 方法动机

### a) 我为什么选择参考这篇论文

- **问题契合**：原论文关注“灾害领域的专用本体如何半自动、高可信地构建”，而我的系统同样需要一个**结构化语义骨架（TBox）**来约束抽取与推理，否则纯 RAG/纯 LLM 容易出现幻觉和语义漂移。
- **方法吸引点**：原论文提出的“CQ 驱动 + LLM 扩展 + 专家验证”的人机协同策略，天然适合我当前数据规模大、知识更新快、人工成本有限的硕士课题场景。

### b) 我对原论文方法的理解

- **核心思想**：以领域需求为导向，先由专家给出高层本体边界，再用 LLM 生成/筛选 CQ，通过 CQ 反推 TBox 的类与关系；随后用权威文档与网页新闻逐步**补充 schema 与实例**，最后以案例验证本体在风险沟通任务中的价值。
- **优势**：CQ 使本体建设紧贴应用需求；多源渐进富集缓解单源偏差；专家审核显著降低 LLM 幻觉风险；OntoQA + CQ 覆盖度评估提供可量化质量证据。
- **局限**：阶段间人工介入较多（CQ 筛选、层级确认等）；文档解析依赖 MunerU 与英文权威材料；最终应用偏向“风险沟通/警报生成”，与其他应用（如知识问答）耦合较弱。

### c) 我的改进/调整思路

- **可借鉴部分**：CQ 驱动的 schema 扩展、渐进式文献增强、抽取‑验证闭环、OntoQA 指标评估。
- **需调整部分**：
  - 原论文 Stage1 的“专家初始本体”在我的场景中成本过高、周期过长，因此改为“专家/文献提炼的领域描述边界 + LLM 归纳初始 TBox”。
  - 原论文 Stage3 依赖 MunerU 做 PDF→Markdown；我的语料主要为中文年鉴/新闻 txt，故采用**已清洗后的文本语料直接驱动增强**。
- **新增设计**：
  1. **P3 模式规范化 + 冲突检测**，把原论文中“去重+人工审核”的理念工程化为可复现的自动检查。
  2. **P4 支持度聚合（min_support）与可控增量合并**，降低单篇文献噪声。
  3. **P5 星型结构+关系白名单约束**，提升 ABox 抽取与 TBox 一致性。
  4. **混合检索+多跳 GraphRAG**，将构建出的本体/KG 真正落到“长江灾害问答”应用上（原论文未覆盖）。

---

## 2. 方法设计（重点）

### a) 方法整体框架

**原论文框架**：
```
阶段1：专家制定初始本体
→ 阶段2：CQ驱动的LLM扩展
→ 阶段3：权威文档富集
→ 阶段4：实例填充
→ 阶段5：案例验证
```

**我的框架（P1–P7）**：
```
阶段0：领域边界描述（专家/文献归纳）          # DEMO_DOMAIN_DESC
→ 阶段1(P1)：领域描述 → LLM生成CQ            # generate_cqs
→ 阶段2(P2)：CQ → 初始TBox(classes/relations/attributes)  # cq_to_schema
→ 阶段3(P3)：TBox规范化（别名合并/层级推断/冲突检测/向量去重） # refine_schema + normalize_tbox_with_p3
→ 阶段4(P4)：语料驱动模式增强（suggestions收集→支持度聚合→过滤→增量补丁合入） # run_p4_over_corpus
→ 阶段5(P5)：TBox约束下事件与三元组抽取（星型结构+白名单+上下文分段） # extract_events/run_p5_batch
→ 阶段6：KG存储与混合检索（NetworkX/Neo4j + 向量/BM25/多跳图扩展） # retrievers/*
→ 阶段7：GraphRAG问答与评估验证（OntoQA、ABox、QA对比、鲁棒性） # tools/* + experiments/*
```

**框架对比分析**：

| 对比维度 | 原论文 | 我的方法 | 差异原因 |
|---------|-------|---------|---------|
| 阶段划分 | 5个阶段 | 0+P1–P7共7个阶段 | 我增加了“模式规范化”“GraphRAG 应用”两层 |
| 初始语义边界 | 专家手工顶层本体 | 领域描述边界 + LLM 归纳初始 TBox | 降低专家成本、快速迭代 |
| schema 扩展来源 | CQ + 权威文档(FEMA等) | CQ + 中文多源 txt 语料 | 数据来源与语言环境不同 |
| 实例填充方式 | 网页新闻实例化 | TBox 约束事件/三元组抽取 | 更强调与 TBox 一致 |
| 落地应用 | 警报优化 | KG‑RAG 问答（混合检索+多跳推理） | 研究目标从“风险沟通”扩展到“知识问答” |

---

### b) 输入与输出

**原论文**：
- 输入：领域需求、权威文档（FEMA 等）、网页新闻、NWS 警报、专家初始本体。
- 输出：洪水本体（TBox + ABox）、Neo4j 知识图谱、优化警报。

**我的方法**（由代码确定）：
- 输入：
  1. **领域描述/边界**：`kg/cq_pipeline.py` 中 `DEMO_DOMAIN_DESC`，可由 `--domain-file` 替换（`scripts/run_cq_pipeline.py`）。
  2. **语料库**：`data/corpus_for_onto/*.txt`、`data/corpus_for_kg/*.txt` 或 `--corpus-jsonl`（清洗/分段后 JSONL）。
  3. **LLM 配置**：`configs/cfg.yaml` 与环境变量（`OPENAI_API_KEYS` / `ZHIPU_API_KEY` / `GEMINI_API_KEY`），由 `kg/llm_core.py` 统一管理。
- 输出：
  1. **CQ 列表**：`outputs/cq_pipeline/final/p1_cqs.json`。
  2. **初始/规范化/增强 TBox**：`p2_tbox_init.json`、`p3_tbox_normalized.json`、`p4_tbox_enhanced.json`。
  3. **TBox 约束抽取结果（ABox）**：`p5_events.json` 或批量 `p5_batch_results.jsonl`、`p5_all_events.json`、`p5_all_triples.json`。
  4. **可查询 KG 与问答输出**：NetworkX 图对象或 Neo4j 图数据库中的三元组，以及 GraphRAG 的最终答案与评测指标。

---

### c) 各阶段详细设计（逐一对比）

#### 阶段0：领域边界描述（初始语义约束）

##### 原论文做法
- 专家基于访谈与需求分析直接制定 6 个顶层类和子类层级，形成初始本体边界。

##### 我的做法
- 以“领域描述文档”替代初始本体：在 `DEMO_DOMAIN_DESC` 中用条目化语言给出灾害类型、阶段、致灾因子、区域、影响、脆弱性与措施等边界。
- 该描述既是 **P1 提示的约束输入**，也是后续 schema 的语义锚点。
- 与原论文关系：**调整**（把专家的结构化初始本体，改为可快速编辑的文本边界）。

##### 关键代码
```python
# kg/cq_pipeline.py
DEMO_DOMAIN_DESC = """
- 灾害类型：直接影响流域的洪水、干旱、枯水等；
- 灾害阶段：事前预防、监测预警、应急处置、灾后恢复；
- 致灾因子：降水异常、厄尔尼诺/拉尼娜、水库调度、人类活动等；
...（其余条目）
"""
# 注释说明：该文本作为 P1 CQ 生成的领域范围约束，
# 对应原论文“阶段1 初始本体边界定义”。
```

##### 数据流转
```
[领域描述:str] → P1 Prompt 注入 → [约束后的 CQ 列表]
```

---

#### 阶段1（P1）：CQ 生成

##### 原论文做法
- 输入：初始本体 + 领域上下文。
- GPT‑4o 生成 CQ，人工筛选后得到训练/测试 CQ 集。

##### 我的做法
- 输入：领域描述文本（阶段0）。
- 使用 `P1_CQ_PROMPT` 约束模型覆盖风险管理全周期、多类别 CQ。
- 输出：结构化 CQ（`id/question/category`），保存为：
  - 构建集（训练集）：`outputs/cq_pipeline/final/p1_cqs_train.json`
  - 测试集：`outputs/cq_pipeline/final/p1_cqs_test.json`
- 说明：CQ 生成后可进行人工快速清洗（去掉重复/过泛/不可回答问题），再按比例切分 train/test；其中 **train 用于驱动 TBox 构建（P2‑P4）**，**test 仅用于评估（CQ 覆盖度）**。
- 与原论文关系：**借鉴 + 工程化复现**（保留“train/test 分离”的评测思想，但将“初始本体上下文”替换为“领域边界描述”）。

##### 关键代码
```python
# kg/cq_pipeline.py（P1 关键实现，逐行解释）
def generate_cqs(self, domain_desc: str, n_cq: int = 30, save_path=None):
    # 1) 将“领域描述边界”注入 P1 提示，明确 CQ 生成范围与数量
    user_prompt = P1_CQ_PROMPT.format(
        domain_desc=domain_desc,  # 领域边界（阶段0产物）
        n_cq=n_cq,                # 需要生成的 CQ 数量
    )
    # 2) 调用统一 JSON 客户端：system 提示强制 JSON，user 为 P1 prompt
    res = self.client.call(
        "只输出 JSON，字段按提示填写。",  # system 约束
        user_prompt,                    # user prompt
    )
    # 3) 读取模型返回的 CQ 数组；若为空则退化为空列表
    raw_cqs = res.get("cqs", []) or []
    cqs = []
    # 4) 逐条解析为 CQ 数据类，缺 question 的条目直接跳过
    for i, item in enumerate(raw_cqs, start=1):
        q = item.get("question")
        if not q:
            continue
        cqs.append(
            CQ(
                id=str(item.get("id", i)),         # CQ 编号
                question=q,                        # CQ 内容
                category=item.get("category", ""), # CQ 类别
            )
        )
    # 5) 可选持久化，便于后续 P2 复现
    if save_path:
        self._dump_json({"cqs": [asdict(cq) for cq in cqs]}, save_path)
    return cqs
```
```python
# kg/prompts.py（节选）
P1_CQ_PROMPT = """
角色：你是一名本体工程师专家...
你的任务：生成 {n_cq} 条能力问题（CQ），覆盖不同类别...
输出格式：仅输出 JSON，顶层字段 "cqs"。
"""
```

##### 数据流转
```
domain_desc → LLMJsonClient.call(P1_CQ_PROMPT) → raw_cqs(JSON)
→ 解析为 CQ 数据类 → p1_cqs.json
```

---

#### 阶段2（P2）：CQ → 初始 TBox 归纳

##### 原论文做法
- LLM 从 CQ 中提取新类与关系，形成候选术语集（TBox）。

##### 我的做法
- 将 CQ 列表序列化为 JSON 注入 `P2_SCHEMA_PROMPT`。
- 模型输出三部分：`classes/relations/attributes`，构成 `TBoxSchema`。
- 与原论文关系：**直接借鉴**（CQ 反推 schema）。

##### 关键代码
```python
# kg/cq_pipeline.py（P2 关键实现，逐行解释）
def cq_to_schema(self, cqs: List[CQ], save_path=None) -> TBoxSchema:
    # 1) 将 CQ 列表序列化为 JSON，作为 P2 的“可计算需求输入”
    cq_json = json.dumps(
        {"cqs": [asdict(c) for c in cqs]},
        ensure_ascii=False,
        indent=2,
    )
    # 2) 注入 P2 提示：要求模型从 CQ 中归纳类/关系/属性
    user_prompt = P2_SCHEMA_PROMPT.format(cq_json=cq_json)
    # 3) 调用 LLM，system 提示强化“本体工程师角色+JSON输出”
    res = self.client.call(
        "你是本体工程师，请严格输出 JSON。",
        user_prompt,
    )
    # 4) 解析为 TBoxSchema（过滤缺字段项，避免脏输出）
    schema = self._parse_tbox(res)
    # 5) 可选保存 P2 输出
    if save_path:
        self._dump_json(schema.to_dict(), save_path)
    return schema
```

##### 数据流转
```
CQs(List[CQ]) → cq_json(str) → LLM(P2) → 初始 TBox(dict)
→ TBoxSchema → p2_tbox_init.json
```

---

#### 阶段3（P3）：TBox 规范化与冲突检测

##### 原论文做法
- 候选实体/关系先用 embedding 去重（阈值 0.7），再由专家审核合并，最终确定层级与关系。

##### 我的做法
1. **P3‑LLM 输出规范化建议**：  
   - `P3_REFINEMENT_PROMPT` 让模型给出 `class_hierarchy` 与 `merged_class_aliases`。
2. **按别名映射进行结构化合并**：  
   - `normalize_tbox_with_p3` 把 P2 的同义类合并为 canonical 类，并把关系/属性的 domain/range/owner 映射到 canonical。
3. **向量去重（可选）**：  
   - `EmbeddingDeduplicator` 使用 `BAAI/bge-base-zh-v1.5`，默认阈值 0.75（P4 新增部分可设 0.8）。
4. **冲突检测（自动化自检）**：  
   - `detect_schema_conflicts` 检测悬空 domain/range、孤立类、重复签名、空定义等。
- 与原论文关系：**借鉴 + 增强**（把“人工审核”前置为可复现的自动规范化/检测）。

##### 关键代码
```python
# kg/cq_pipeline.py（P3 生成）
def refine_schema(self, schema: TBoxSchema, save_path=None):
    # 1) 序列化 P2 的初始 TBox
    schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)
    # 2) 注入 P3 Prompt，让模型输出“层级结构+别名合并+清洗关系”
    user_prompt = P3_REFINEMENT_PROMPT.format(schema_json=schema_json)
    # 3) 调用 LLM 得到 p3_result（dict）
    res = self.client.call("请清洗模式并输出 JSON。", user_prompt)
    # 4) 可选保存原始 P3 结果
    if save_path:
        self._dump_json(res, save_path)
    return res
```
```python
# kg/cq_pipeline.py（P3-Norm 合并）
# 1) 构建别名→规范名映射 alias_map（来自 P3 的 merged_class_aliases）
alias_map = {"FloodEventAlias": "FloodEvent", ...}
# 2) 合并类：按 canonical_name 聚合 cn_name/definition/examples
for cls in schema.classes:
    canonical = alias_map.get(cls.name, cls.name)
    merged_classes[canonical] = merge_defs(merged_classes.get(canonical), cls)
# 3) 清洗关系：将 domain/range 映射为规范类名
new_relations = []
for r in p3_result["relations"]:
    new_relations.append(
        RelationDef(
            name=r["name"],
            cn_name=r.get("cn_name",""),
            domain=alias_map.get(r["domain"], r["domain"]),
            range=alias_map.get(r["range"], r["range"]),
            definition=r.get("definition",""),
            functional=bool(r.get("functional", False)),
        )
    )
```
```python
# kg/utils/conflict_detection.py
conflicts = detect_schema_conflicts(tbox_dict)
summary = summarize_conflicts(conflicts)
```

##### 数据流转
```
p2_tbox_init.json → LLM(P3) → class_hierarchy/aliases
→ normalize_tbox_with_p3 → p3_tbox_normalized.json
→ (optional) EmbeddingDeduplicator → p3_tbox_normalized_dedup.json
→ conflict_detection → p3_conflicts.json
```

---

#### 阶段4（P4）：语料驱动的模式增强

##### 原论文做法
- 权威 PDF/新闻经 MunerU 解析为 Markdown；LLM 分类句子并提取概念/实例；概念候选去重后人工审核并插入本体。

##### 我的做法
1. **逐文献 suggestions 收集**：  
   `enhance_schema(schema, doc_text)` 使用 `P4_AUGMENT_PROMPT` 输出 `suggestions`（type=class/relation/attribute）。
2. **跨文献支持度聚合**：  
   `run_p4_over_corpus` 对同名建议统计 `_support`（出现次数）。
3. **过滤与可控合并**：  
   - `min_support>=2` 的建议才保留；  
   - `allow_new_classes=False`（默认）时，仅补充关系/属性，不随意新增类；  
   - 可选 `align_names=True` 用 `SchemaAligner` 做同义归一；  
   - 可选 `dedup_new=True` 再做向量去重。
4. **增量补丁合入**：  
   `apply_p4_suggestions` 把过滤后的建议写回 TBox。
- 与原论文关系：**借鉴 + 工程化调整**（保持“文献驱动富集”，但弱化 MunerU/人工审核依赖，用支持度+去重实现可复现过滤）。

##### 关键代码
```python
# kg/cq_pipeline.py（两阶段 P4 核心逻辑，逐行解释）
collected = []
# 1) 第一阶段：逐篇文献调用 LLM 收集 suggestions
for fp in corpus_path.glob("*.txt"):
    text = fp.read_text(encoding="utf-8")
    res = self.enhance_schema(base_schema, text)  # LLM(P4)
    sug = res.get("suggestions", []) or []        # 候选补丁
    for s in sug:
        s["_source"] = fp.name                    # 记录来源便于追溯
    collected.extend(sug)

# 2) 第二阶段：跨文献聚合支持度 _support
buckets = {}
for s in collected:
    key = (
        s.get("type"), s.get("name"),
        s.get("parent_or_domain_range_or_owner") or s.get("owner") or s.get("domain") or "",
        s.get("range") or "",
    )
    if key not in buckets:
        s["_support"] = 1
        buckets[key] = s
    else:
        buckets[key]["_support"] += 1
aggregated = list(buckets.values())

# 3) 过滤：低支持度/不允许新增类的候选直接丢弃
filtered = []
for s in aggregated:
    if int(s.get("_support", 1)) < min_support:
        continue
    if s.get("type") == "class" and not allow_new_classes:
        continue
    filtered.append(s)

# 4) 增量合并：将过滤后的 suggestions 写回 TBox
merged = apply_p4_suggestions(base_schema, {"suggestions": filtered})
```

##### 数据流转
```
p3_tbox_normalized.json + corpus/*.txt
→ LLM(P4) per‑doc suggestions
→ AggregateBySupport(min_support)
→ (align_names/dedup_new)
→ apply_p4_suggestions
→ p4_tbox_enhanced.json
```

---

#### 阶段5（P5）：TBox 约束事件与三元组抽取

##### 原论文做法
- 从网页新闻中抽取实例，新闻实例直接填充 ABox；权威文档中提取的实例经规则/LLM合入；专家把关幻觉。

##### 我的做法
1. **TBox 约束的单段抽取**：  
   `extract_events(paragraph, schema)` 将 `schema_json + EVENT_SCHEMA_HINT + paragraph` 注入 `P5_EXTRACTION_PROMPT`。  
   Prompt 强制**星型结构**（所有三元组 head 为同一事件）与**关系白名单**（predicate 必须来自 TBox.relations）。
2. **抽取一致性清洗**：  
   `_sanitize_p5_result` 对 LLM 输出做约束校验：  
   - event_type 不在类集合则回退到 `DisasterEvent`；  
   - predicate 不在关系集合则标记 `_invalid_predicate=True`；  
   - 补齐字段避免下游 KeyError。
3. **批量抽取与上下文拼接**：  
   `scripts/run_cq_pipeline.py` 支持从 `light_pool.jsonl` 读取片段（`load_segments_for_p5`），可选 `include_context` 拼接前后文。
4. **实体标准化（可选）**：  
   `normalize_extraction_result` 把地名/灾害术语归一（`kg/utils/entity_linking.py`）。
- 与原论文关系：**借鉴 + 增强**（仍是多源实例填充，但强调“先有 TBox 再约束 ABox”，并引入自动清洗与批量工程）。

##### 关键代码
```python
# kg/cq_pipeline.py（P5 关键实现，逐行解释）
# 1) 把当前 TBox 注入 Prompt，让模型“在 schema 约束下”抽取
schema_json = json.dumps(schema.to_dict(), ensure_ascii=False, indent=2)
user_prompt = P5_EXTRACTION_PROMPT.format(
    schema_json=schema_json,             # 允许的类/关系/属性集合
    event_schema=EVENT_SCHEMA_HINT,      # 事件 JSON 输出模板
    paragraph=paragraph.strip(),         # 待抽取文本（可带上下文）
    class_usage_hint="优先使用 TBox 中已有的类名...",  # 复用/细化偏好
)
# 2) 调用 LLM，强制返回 events/triples 的 JSON
res = self.client.call("仅输出 JSON，不要解释。", user_prompt)
# 3) 结果清洗：回退非法 event_type，标记非法 predicate，补齐字段
res = self._sanitize_p5_result(res, schema)
```
```python
# scripts/run_cq_pipeline.py（批量）
segments = load_segments_for_p5(  # 1) 读取清洗后的 JSONL 片段
    Path(args.corpus_jsonl),
    max_segments=args.max_segments,
)
for seg in segments:
    # 2) 可选拼接前后文，形成结构化输入
    text = build_extraction_input(seg, include_context=args.include_context)
    # 3) 调用 P5 抽取，受当前 TBox 约束
    p5_res = pipeline.extract_events(text, tbox)
    # 4) 可选实体标准化、增量落盘（断点续跑）
```

##### 数据流转
```
p4_tbox_enhanced.json + segment(text/context)
→ LLM(P5) → events/triples
→ _sanitize_p5_result
→ (optional) EntityNormalizer
→ p5_events.json / p5_batch_results.jsonl
```

---

#### 阶段6：知识图谱存储与混合检索（GraphRAG 上下文构建）

##### 原论文做法
- 以 Neo4j 存储 KG，主要用于警报语义增强；无检索‑问答模块。

##### 我的做法
- **双后端存储**：  
  - 轻量实验用 NetworkX（内存图）；  
  - 规模化持久化用 Neo4j（`kg/neo4j_adapter.py`）。
- **三阶段混合检索**：  
  1. 向量语义检索（`retrievers/vector_retriever.py`，BGE‑base‑zh）；  
  2. BM25 关键词补充（`retrievers/text_retriever.py`）；  
  3. 图结构多跳扩展（`retrievers/graph_retriever.py` 的 BFS 多跳子图）。
- 与原论文关系：**自主设计**（面向问答落地）。

##### 关键代码（多跳扩展思想）
```python
# retrievers/graph_retriever.py（概念）
triples = GraphRetriever.multi_hop_subgraph(seed_nodes, max_hops=h)
# 注释：在知识图谱上做 BFS 多跳扩展，为 LLM 提供结构化证据。
```

##### 数据流转
```
p5_all_triples.json → NetworkX/Neo4j
→ [Vector seeds + BM25] → seed_nodes
→ multi_hop_subgraph → 结构化证据 triples
```

---

#### 阶段7：GraphRAG 问答与评估验证

##### 原论文做法
- 用 OntoQA 指标（RR/IR）与 CQ 覆盖度验证本体；再做警报案例验证。

##### 我的做法
1. **TBox 结构指标（OntoQA）**：  
   `tools/tbox_metrics.py` 计算 RR/IR/AR，与原论文公式一致：  
   - `RR = P/(P+SC)`，`IR = SC/C`。
2. **CQ 覆盖度评估（使用 test_cqs，避免数据泄漏）**：  
   - 测试集 CQ：`outputs/cq_pipeline/final/p1_cqs_test.json`  
   - 覆盖度实现：`tools/cq_coverage.py`（将类/关系/属性转为“富语义文本”，与 CQ 问句做最大相似度匹配，多阈值统计覆盖率）  
   - 一键评估入口：`scripts/run_full_evaluation.py`（同时输出 OntoQA + CQ 覆盖 + 抽取指标）
3. **ABox 抽取质量**：  
   `tools/abox_metrics.py`（严格/松弛三元组 F1、事件 F1），对比无约束抽取。
4. **问答效果**：  
   `experiments/exp_qa_comparison.py`、`scripts/run_full_evaluation.py` 对比 Naive RAG vs GraphRAG。
5. **鲁棒性工程评估**：  
   多 Key 轮换、断点续跑、长时间批处理稳定性（`kg/llm_core.py`）。
- 与原论文关系：**借鉴 + 扩展**（保留 OntoQA 思路，新增 QA 与工程鲁棒性评测）。

---

### d) 模块功能与协同

**原论文模块划分**（复述）：
- 专家模块、LLM 模块、数据处理模块（MunerU/爬虫）、Neo4j 存储模块。

**我的模块划分**：

| 模块名称 | 功能描述 | 对应代码文件 | 与原论文对应关系 |
|---------|---------|-------------|-----------------|
| 领域边界与CQ模块 | 领域描述约束、CQ 生成 | `kg/cq_pipeline.py`, `kg/prompts.py`, `scripts/run_cq_pipeline.py` | 对应原论文阶段1‑2（CQ 部分），输入形式调整 |
| 初始模式归纳模块 | CQ→初始 TBox | `kg/cq_pipeline.py:cq_to_schema` | 对应原论文阶段2 |
| 模式规范化模块 | 别名合并、层级推断、向量去重 | `kg/cq_pipeline.py:normalize_tbox_with_p3`, `kg/utils/deduplication.py` | 对应原论文候选去重/层级确认，工程化增强 |
| 冲突检测模块 | 悬空关系/孤立类/空定义检查 | `kg/utils/conflict_detection.py` | 原论文未显式提出（新增） |
| 文献增强模块 | suggestions 收集、支持度聚合、增量合并 | `kg/cq_pipeline.py:run_p4_over_corpus`, `apply_p4_suggestions` | 对应原论文阶段3，但无需 MunerU |
| TBox 约束抽取模块 | 星型结构+白名单抽取、批量分段 | `kg/cq_pipeline.py:extract_events`, `scripts/run_cq_pipeline.py:run_p5_batch` | 对应原论文阶段4，约束更强 |
| 实体标准化模块 | 地名/术语别名归一 | `kg/utils/entity_linking.py` | 对应原论文人工校正（自动化） |
| KG 存储模块 | NetworkX/Neo4j 双后端 | `kg/neo4j_adapter.py`, `kg/query.py` | Neo4j 对应原论文，NetworkX 为新增 |
| 混合检索模块 | 向量+BM25+多跳图扩展 | `retrievers/*`, `kg/query.py` | 原论文无（新增） |
| 评估模块 | OntoQA、ABox、QA、鲁棒性评测 | `tools/*`, `experiments/*` | OntoQA 对应原论文，其余为新增 |

**模块协同流程**：
```
领域描述 → CQ模块(P1)
→ 初始模式归纳(P2)
→ 规范化/冲突检测(P3)
→ 语料增强(P4)
→ TBox约束抽取(P5)
→ KG存储(Neo4j/NetworkX)
→ 混合检索+多跳扩展
→ GraphRAG问答
→ 指标评估与案例验证
```

---

### e) 关键技术点详解

#### 技术点1：多 LLM 后端统一与多 Key 轮换

**原论文做法**：
- 单一 GPT‑4o；温度 0.1；无工程级轮换说明。

**我的做法**：
- `kg/llm_core.py` 提供 OpenAI 兼容统一接口，支持 OpenAI/智谱/Gemini；  
- `APIKeyManager` 实现 429 限流自动切换、冷却恢复与线程安全。

**关键代码**：
```python
# kg/llm_core.py
key = manager.get_current_key()
...
except RateLimitError:
    manager.mark_rate_limited(key)  # 429 自动轮换
```

---

#### 技术点2：JSON 强制输出与鲁棒解析

**原论文做法**：
- 依赖模型遵循 JSON 输出，人工或简单规则兜底。

**我的做法**：
- `LLMJsonClient.call(..., json_mode=True)` 强制 JSON；  
- `_safe_load` 自动剥离 Markdown code fence，失败时截取 `{...}` 子串再解析。

**关键代码**：
```python
# kg/cq_pipeline.py
raw = self.llm.chat_messages(messages, json_mode=True)
obj = json.loads(cleaned)  # 失败则 re.search 截取 JSON 子串
```

---

#### 技术点3：Embedding 去重（模式与增量建议）

**原论文做法**：
- `text-embedding-3-large`，余弦相似度阈值 0.7。

**我的做法**：
- 中文场景改用 `BAAI/bge-base-zh-v1.5`；  
- P3 默认阈值 0.75；P4 新增建议阈值 0.8（更严格）。

**关键代码**：
```python
# kg/utils/deduplication.py
sims = np.dot(existing_embs, cand_emb)
if max_sim >= self.threshold: rejected.append(...)
```

---

#### 技术点4：支持度聚合的文献增强策略

**原论文做法**：
- 单篇文献提取→去重→人工审核合入。

**我的做法**：
- 跨文献统计 `_support`，只合入高频、稳定概念；  
- 默认禁止新增类（`allow_new_classes=False`），降低噪声扩张。

**关键代码**：
```python
# kg/cq_pipeline.py
if sup < min_support: continue
if s["type"]=="class" and not allow_new_classes: continue
```

---

#### 技术点5：TBox 约束抽取 Prompt（星型结构+白名单）

**原论文做法**：
- 实例抽取未显式强制“事件为中心”的结构约束。

**我的做法**：
- `kg/extractor.py` 与 `P5_EXTRACTION_PROMPT` 强制所有三元组 head 为同一核心事件；  
- predicate 仅允许来自 TBox。

**关键代码**：
```python
# kg/extractor.py（节选）
1) 核心事件识别
2) 星型结构：relations 以核心事件为 head
3) 关系约束：relation ∈ allowed_relations
```

---

#### 技术点6：抽取结果一致性清洗

**原论文做法**：
- 主要依赖人工拒绝幻觉候选。

**我的做法**：
- `_sanitize_p5_result` 自动回退非法 event_type、标记非法 predicate、补齐字段，提升可用性与可评测性。

---

#### 技术点7：实体标准化/消歧

**原论文做法**：
- 依赖专家合并细粒度概念与别名。

**我的做法**：
- `EntityNormalizer` 内置长江地名/灾害术语别名表 + 包含式模糊匹配；批量归一 triples/events。

---

#### 技术点8：混合检索与多跳 GraphRAG

**原论文做法**：
- 无 RAG/GraphRAG 检索问答设计。

**我的做法**：
- 语义 seeds（向量）+ 词汇补充（BM25）+ 图上 BFS 多跳扩展；  
- `kg/query.py` 组织 triples 证据注入 Prompt 生成答案。

---

### f) 关键算法/公式

**原论文公式**（复述）：
- 关系丰富度：`RR = P / (P + SC)`  
- 继承丰富度：`IR = SC / C`

**我的方法中涉及的关键计算**：
1. **OntoQA 指标**：`tools/tbox_metrics.py` 直接实现 RR/IR/AR，保持与原论文可比性。  
2. **多跳图检索 BFS**：在 `retrievers/graph_retriever.py` 上实现 multi‑hop 子图扩展（伪代码见 `txts/project/project_summary.md`）。

---

## 3. 与原论文方法的系统对比

### a) 方法本质对比

| 维度 | 原论文 | 我的方法 |
|-----|-------|---------|
| 核心思想 | 人机协同的半自动化本体构建 | CQ 驱动的 TBox 构建 + TBox 约束 ABox 抽取 + GraphRAG 落地 |
| 方法定位 | 面向公众风险沟通的洪水本体 | 面向长江灾害问答的领域本体/知识图谱工程 |
| 技术路线 | 专家框架 + LLM 扩展 + 多源富集 | 领域描述边界 + LLM 端到端 P1‑P5 + 混合检索/图推理 |

### b) 具体环节对比（对应）

| 环节 | 原论文 | 我的方法 | 我的理由 |
|-----|-------|---------|---------|
| 初始本体定义 | 专家定义 6 顶层类 | 领域描述文本替代初始本体 | 降低专家成本，便于快速迭代 |
| CQ 生成 | GPT‑4o, 温度0.1, 人工筛选 | LLM 生成 CQ，自动保存 | 先保证流程可复现，再按需人工精修 |
| 实体去重 | text‑embedding‑3‑large, τ=0.7 | BGE‑base‑zh, τ=0.75/0.8 | 中文语料适配、阈值更稳健 |
| 文档解析 | MunerU(PDF→MD) | 直接使用清洗 txt/JSONL | 数据形态不同，避免额外工具依赖 |
| schema 富集 | 单篇提取 + 人工审核 | suggestions 支持度聚合 + 可控合并 | 降低单文档噪声与幻觉 |
| 实例填充 | 新闻/权威文档实例化 | TBox 约束事件/三元组抽取 | 更强调一致性与可检索性 |
| 质量控制 | 专家拒绝 8%/10% 候选 | 冲突检测 + 清洗 + 可选人工复核 | 自动化前置自检，缩小人工负担 |
| 应用验证 | 警报优化案例 | GraphRAG 问答 + OntoQA/ABox/QA 多维评测 | 课题目标不同，需要问答落地 |

### c) 我的方法特点

- **借鉴**：CQ 驱动 schema、渐进式多源富集、OntoQA 评估范式。  
- **简化**：弱化“专家初始本体”和“文档解析工具”依赖。  
- **增强**：P3 自动规范化/冲突检测；P4 支持度聚合；P5 强约束抽取；实体标准化。  
- **新增**：混合检索 + 多跳 GraphRAG 问答应用；多 LLM 后端与鲁棒性工程。  
- **未涉及**：面向公众风险沟通的警报个性化生成（非本课题重点）。  

---

## 4. 实现细节与代码示例

### a) 项目结构（与方法阶段对应）

```
YangtzeDestoryLLM/
├── kg/
│   ├── cq_pipeline.py          # P1-P5 主流水线
│   ├── prompts.py              # P1-P5 Prompt 模板
│   ├── llm_core.py             # 多后端 LLM 调用 + 多Key轮换
│   ├── extractor.py            # 星型结构抽取器（LLM/DL基线）
│   ├── query.py                # GraphRAG 问答引擎
│   ├── neo4j_adapter.py        # Neo4j 存储适配
│   └── utils/
│       ├── deduplication.py    # 向量去重（P3/P4）
│       ├── conflict_detection.py # 冲突检测（P3/P4）
│       ├── schema_alignment.py # 同义对齐（P4）
│       └── entity_linking.py   # 实体标准化（P3/P5）
├── retrievers/                 # 混合检索与多跳扩展（阶段6）
├── tools/                      # OntoQA/ABox 指标（阶段7）
├── scripts/run_cq_pipeline.py  # 端到端运行入口（P1-P5）
└── experiments/                # QA/消融/鲁棒性评测
```

### b) 核心代码示例（阶段联动）

```python
# scripts/run_cq_pipeline.py（主链路节选）
cqs = pipeline.generate_cqs(domain_desc, n_cq, save_path="p1_cqs.json")
tbox = pipeline.cq_to_schema(cqs, save_path="p2_tbox_init.json")
p3_res = pipeline.refine_schema(tbox, save_path="p3_tbox_refinement.json")
tbox = pipeline.normalize_tbox_with_p3(tbox, p3_res, save_path="p3_tbox_normalized.json")
tbox = pipeline.run_p4_over_corpus(tbox, corpus_dir, save_aug_tbox_path="p4_tbox_enhanced.json")
p5_res = pipeline.extract_events(paragraph, tbox, save_path="p5_events.json")
```

### c) 完整数据流转（简化全景）

```
[领域描述 DEMO_DOMAIN_DESC]
   ▼
P1 generate_cqs → p1_cqs.json
   ▼
P2 cq_to_schema → p2_tbox_init.json
   ▼
P3 refine_schema + normalize_tbox_with_p3
   ▼
p3_tbox_normalized.json (+p3_conflicts.json)
   ▼
P4 run_p4_over_corpus → p4_tbox_enhanced.json
   ▼
P5 extract_events/run_p5_batch → p5_events.json / p5_all_triples.json
   ▼
NetworkX/Neo4j 存储
   ▼
Hybrid Retrieval + Multi-hop Expansion
   ▼
GraphRAG Answer + Evaluation
```

---

## 5. 总结

### a) 我的方法核心思想（≤20字）

CQ 驱动构建 TBox，并约束抽取与问答。

### b) 我的方法流程速记（3–5步）

1. 领域描述边界 → 生成 CQ  
2. CQ → 初始 TBox → 规范化/冲突检测  
3. 多源语料支持度增强 TBox  
4. TBox 约束抽取事件/三元组并标准化  
5. 图存储 + 混合检索 + 多跳 GraphRAG 问答与评估

### c) 与原论文的关系总结

| 类型 | 具体内容 |
|-----|---------|
| 借鉴 | CQ 驱动 schema、渐进式富集、OntoQA 评估 |
| 调整 | 初始本体→领域描述；权威 PDF 富集→中文 txt 语料增强 |
| 自主设计 | P3 冲突检测/规范化工程、P4 支持度聚合、P5 强约束抽取、GraphRAG 应用 |
| 未涉及 | 面向公众的警报个性化生成 |

### d) 我的主要工作

1. 设计并实现 CQ 驱动的 P1‑P5 自动化流水线（可复现）。  
2. 提出一套面向中文灾害语料的 schema 增强与抽取约束策略。  
3. 将构建出的本体/KG 落地到混合检索‑多跳 GraphRAG 问答系统，并完成多维评估。  
