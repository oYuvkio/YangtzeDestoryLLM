
下面给你一个“代码审稿 + 实验落地清单”。我直接回答三件事：**(1) 现在的脚本是否已支持support与消融**、**(2) 还缺哪些开关才能对上论文要求**、**(3) 立刻可跑的对比矩阵与命令**。同时我把需要修改的点一一指出，并给出最小改动建议（不需要大量重构）。

---

## 结论先说

* **Support 已支持**：`--min-support` 与 `--extra-supports` 已能一次跑出多套增强版 TBox（文件名带后缀 `s{support}_allow{0/1}`）。
* **消融（Ablation）已部分支持**：

  * ✅ 是否**允许新增类**：`--allow-new-classes`
  * ✅ 合并前**同义对齐**：`--align-names`
  * ✅ **embedding 去重**（新增类/关系）：`--dedup-new --dedup-threshold`
  * ❌ **冲突策略消融**还不完整（当前只“检测并报表”，**未参与合并决策**）。
  * ❌ **P2 阶段 embedding 去重（阈值>0.7）**还没进主流程（论文硬性要求，需要加一个可开关的配置）。
* **与参考论文不一致的关键点**（必须补齐才更有说服力）：

  1. **P2 阶段**要有 `text-embedding-3-large` 的**相似度去重阈值 0.7**开关＋日志（保留/剔除对儿）；
  2. **冲突策略**要能选择（保留旧、采用新、跳过冲突项），并在实验里做**消融**；
  3. **建议聚合的支持度**统计应在**同义对齐/正则化之后**再计数（避免“同名异形”被分散支持）；
  4. **溯源可审计**：建议项要保留 `_support_sources`（doc_id 列表）与 evidence 片段摘要，方便论文附录展示。

---

## 需要立刻修的两个逻辑问题（低成本高收益）

### 1) JSONL 语料分支的建议生成“死代码”

你在处理 TXT 的 `else:` 分支里又写了一段“处理 JSONL 格式语料”，但这段**只在 TXT 分支里才会执行**。当用户传 `--corpus-jsonl` 时，前面走了 `elif use_jsonl:`，**不会进入 TXT 的 else**，于是**不会生成任何 suggestion**。
**修法（极小改动）**：把“处理 JSONL 语料”的那段从 TXT 分支里**上移到顶层**（与 TXT 处理并列）。伪补丁要点：

* 顶层：

  * 如果 `use_jsonl=True`：循环 `jsonl_docs` → `pipeline.enhance_schema()` → 写出 `p4_suggestions.jsonl` 与 `raw_suggestions`。
  * 如果 `use_jsonl=False`：再进入 TXT 分支。

### 2) 支持度聚合前应做“名称规整/同义映射”

现在 `_support` 的 key 用 `(type, name, parent_or_owner, range)`，但**未做对齐**（大小写、空格/全角、同义）。这会把相同概念的支持分裂成多个桶。
**修法**：在 “聚合建议并统计支持度” 前，**统一做**：

* `name/owner/domain/range`：`strip()`、小写/驼峰统一、中文全角→半角；
* 若 `--align-names` 开启，先调用 `SchemaAligner` 做同义对齐，再计数；
* 可选：把 `parent_or_domain_range_or_owner` 统一解包并**按字段**落桶（不要混在一个字段里）。

---

## 立即可跑的实验矩阵（命令现成）

### 推荐主矩阵（10～16 组即可写论文）

* 维度 A：`min-support ∈ {1,2,3}`
* 维度 B：`allow-new-classes ∈ {0,1}`
* 维度 C：是否同义对齐 `--align-names` ∈ {关, 开}（可先固定为开，做小消融）
* 维度 D：是否对新增项做 embedding 去重 `--dedup-new` ∈ {关, 开}

示例脚本（可存为 `scripts/run_p4_grid.sh`）：

```bash
#!/usr/bin/env bash
BASE=outputs/cq_pipeline/final/p3_tbox_dedup.json
CORP=data/corpus_for_onto/p4_only.jsonl
OUTC=outputs/ontoqa/p4_conflicts.json

for SUP in 1 2 3; do
  # 允许/禁止新增类
  for ALLOW in 0 1; do
    python scripts/run_p4_batch.py \
      --base-tbox "$BASE" \
      --corpus-jsonl "$CORP" \
      --min-support $SUP \
      --extra-supports "" \
      $( [ $ALLOW -eq 1 ] && echo "--allow-new-classes" ) \
      --align-names \
      --dedup-new --dedup-threshold 0.80 \
      --conflict-report "$OUTC" \
      --log-file "outputs/logs/p4_s${SUP}_allow${ALLOW}.log"
  done
done
```

**产物命名**：脚本会在 `outputs/cq_pipeline/final/` 生成

* `p4_tbox_augmented_s1_allow0.json`
* `p4_tbox_augmented_s1_allow1.json`
* `p4_tbox_augmented_s2_allow0.json` …（依此类推）
  每个文件会带**带时间戳的备份**（你已经实现）。

> 跑完立刻接 `scripts/run_tbox_eval.py`（OntoQA）和 `scripts/run_cq_coverage.py`（覆盖曲线），最后固定一套最优配置进入 P5 / QA 下游评测。

---

## 还缺的开关/接口（对齐论文所需）

### A. P2 阶段 embedding 去重（论文硬要求）

* 在 `configs/cfg.yaml` 增加：

```yaml
p2_embed_dedup:
  enabled: true
  model: text-embedding-3-large
  threshold: 0.70
```

* 在 `kg/cq_pipeline.py` 的 P2 输出后、P3 之前插入去重：

  * 对 **类名/关系/属性** 逐项做语义去重；
  * 记录 `dedup_pairs.jsonl`（被合并项、相似度、保留/剔除理由）；
  * 将此开关暴露为命令行 `--p2-embed-dedup-enabled`（同时也能通过 cfg 控制）。
* **实验里要做消融**：`enabled=true` vs `false`（D1/D2）。

### B. 冲突策略（Conflict Resolution）可切换

现在 `P4Applier` 只**检测**冲突并写报告，**没有影响合并**。需要：

* 新增参数 `--conflict-policy {keep_existing,use_new,skip_conflicts}`；
* 在 `merge_suggestions()` 内，对检测到的冲突项按策略处理：

  * `keep_existing`：忽略该建议；
  * `use_new`：覆写旧定义（并把旧定义写到 `replaced_by` 字段或 `history`）；
  * `skip_conflicts`：跳过该条建议；
* 把每个被处理的冲突写入 `conflict_actions.jsonl`（便于论文追溯）。
* **消融**：至少比较 `keep_existing` vs `skip_conflicts`。

### C. 支持度与溯源增强

* 聚合时把每条建议的 `doc_id` 加入 `"_support_sources": ["id1","id2",...]`；
* `--min-support` 判定**仍按计数**，但落盘保留 sources，论文里可展示“该关系被 N 篇‘水利年鉴/应急预案’共同支持”。

### D. 可复现实验元数据

* 在 `write_json_with_backup()` 同步落一个 `p4_run_meta.json`（或每个 tbox 同名 `.meta.json`），包含：

  * `base_tbox_md5`、`corpus_md5`、`cfg_digest`、`args`、`model_name/temperature`、`random_seed`。
* 这样盲审时能证明**每个结果可复现**。

---

## 论文里要展示的三类表/图（脚本产物应对应生成）

1. **TBox 结构指标（OntoQA）**

   * 表：`RR/IR/AR + |Classes|/|Relations|/|Attributes| + #Conflicts`，按不同 support/allow_new 组合比较。
2. **CQ 覆盖曲线**

   * 图：横轴阈值（0.3~0.8），纵轴覆盖率；多条线对比不同组合；标注 AUC。
3. **下游（P5/ABox、QA）**

   * 表：Event-F1 / Triple-F1（Strict/Relaxed）/ TBox 一致率；
   * 表/图：QA Acc@1 / ROUGE-L / BLEU（带 p-value / CI）。

> 这些脚本你已规划在 handoff 里：`run_tbox_eval.py`、`run_cq_coverage.py`、`run_p5_eval_grid.sh`、`exp_qa_comparison.py`，按该命名输出 csv/json 和图即可。

---

## 代码级“最小改动”提示（只列关键行，不贴整文件）

1. **把 JSONL 处理挪出 TXT 分支**

```python
if args.merge_only and agg_path.exists():
    ...
elif use_jsonl:
    # 这里直接处理 jsonl_docs，生成 raw_suggestions 与 p4_suggestions.jsonl
    ...
else:
    # 这里处理 TXT 目录
    ...
# 聚合建议 & 统计 _support 放在两种路径之后的公共位置
```

2. **聚合时做规整/同义**

```python
aligner = SchemaAligner() if align_names else None
def _norm(s):
    # 统一 name/owner/domain/range：strip/lower/全角转半角
    ...
    if aligner:
        if s['type']=='class': s['name'] = aligner.align_class_name(s['name'])
        if s['type']=='relation': s['name'] = aligner.align_relation_name(s['name'])
    return s
for s in raw_suggestions:
    s = _norm(s)
    key = (s_type, s['name'], owner_or_domain, range_)
    bucket[key]['_support'] += 1
    bucket[key].setdefault('_support_sources', []).append(s.get('doc_id'))
```

3. **冲突策略接入 `merge_suggestions`**

* 入口参数加：`conflict_policy: str = "keep_existing"`
* 在“已存在且冲突”分支里做三路分发（并记录 `conflict_actions`）。

4. **P2 embedding 去重接入点**

* 在 `kg/cq_pipeline.py` 的 P2 输出后插入：

```python
if cfg.p2_embed_dedup.enabled:
    dedup = EmbeddingDeduplicator(model=..., threshold=cfg.p2_embed_dedup.threshold)
    tbox = dedup.apply_to_tbox(tbox, log_path="outputs/cq_pipeline/process/p2_dedup_pairs.jsonl")
```

---

## 立刻可执行的对比（建议从这三组开始拿主结论）

1. **Support 阈值敏感性**（固定允许新增类=0, 开 align/去重）

```bash
for SUP in 1 2 3; do
  python scripts/run_p4_batch.py \
    --base-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
    --corpus-jsonl data/corpus_for_onto/p4_only.jsonl \
    --min-support $SUP --align-names --dedup-new --dedup-threshold 0.80 \
    --conflict-report outputs/ontoqa/p4_conflicts.json
done
```

2. **是否允许新增类**（固定 support=2）

```bash
for ALLOW in 0 1; do
  python scripts/run_p4_batch.py \
    --base-tbox outputs/cq_pipeline/final/p3_tbox_dedup.json \
    --corpus-jsonl data/corpus_for_onto/p4_only.jsonl \
    --min-support 2 $( [ $ALLOW -eq 1 ] && echo "--allow-new-classes" ) \
    --align-names --dedup-new --dedup-threshold 0.80
done
```

3. **P2 去重消融**（等你把 P2 去重开关接上后）

```bash
# D1: 关闭
python scripts/run_full_pipeline.py --p2-embed-dedup-enabled false ...
# D2: 开启（阈值=0.7）
python scripts/run_full_pipeline.py --p2-embed-dedup-enabled true --p2-embed-dedup-threshold 0.7 ...
```

随后对每一组跑：

```bash
python scripts/run_tbox_eval.py   --tbox outputs/cq_pipeline/final/p4_tbox_augmented_*.json
python scripts/run_cq_coverage.py --tbox outputs/cq_pipeline/final/p4_tbox_augmented_*.json --cqs outputs/cq_pipeline/final/p1_cqs_test.json
bash   scripts/run_p5_eval_grid.sh  # 生成 ABox/QA 指标
```

---

## 最后提醒（盲审关键）

* **数据互斥**：`p4_only.jsonl` 与 `data/p5_eval_pool/*`、`P5 构图语料` 保持**零交集**（把交集校验作为脚本第一步打印出来）。
* **审计可追踪**：每个增强项的 `_support` 与 `_support_sources` 持久化，`conflict_report` + `conflict_actions` 双落盘。
* **统计显著性**：QA 指标用 **McNemar** 或 **Bootstrap** 给出 p 值/置信区间。
* **可复现元数据**：记录 `md5`、`cfg.yaml` 摘要、`args`、LLM `model/temperature`、`seed`。

有了以上补丁和脚本，你就能：

1. 跑出**可复现**的 P4 增强多组结果；
2. 做齐 **support/新增类/对齐/去重/P2 去重/冲突策略** 等**消融对比**；
3. 在论文里用 **OntoQA + CQ覆盖 + ABox/QA** 三条证据链完整论证“P4 的真实增益”。
