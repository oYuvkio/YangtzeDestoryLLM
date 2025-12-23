# 接力文档（YangtzeDestoryLLM 本体构建/评测复现）

## 当前任务状态
**目标**：完成论文复现的全方位对比实验与论文写作补充：
- OntoQA 指标对比（P2/P3/P4 allow0/allow1 + support 消融）；
- 选择最佳 TBox 做 P5（ABox/事件/三元组）抽取；
- 若有 gold 标注，做 ABox 指标评测并形成论文段落与误差分析。

**进度**：
- ✅ 已完成 P3(带继承) 去重与 P4 文献增强全流程（allow0 + allow1 merge-only）。
- ✅ 已修复 LLM 调用超时/代理问题、模型缓存下载问题、merge-only 流程问题。
- ✅ OntoQA 工具增强并已跑出“干净 8 版本”指标（见下文）。
- 🔄 待完成：P5 抽取（dev/test）、ABox 评测、撰写完整论文实验与结论。

**当前卡点**：
- 需要跑 P5 抽取并收集结果；
- gold 标注文件可能尚未就绪（若无 gold，ABox 评测会跳过）；
- 论文需要把 OntoQA + 下游效果整合成对比/消融实验文字。

## 已探索路径
| 方向 | 状态 | 备注 |
|------|------|------|
| P3 去重（带继承） | ✅ | 使用 outputs/cq_pipeline/final/p2_tbox_with_hierarchy.json → 生成 outputs/cq_pipeline/final_with_hierarchy/p3_tbox_dedup.json，IR 恢复到 0.375。 |
| P4 文献增强 allow0 | ✅ | LLM 全量抽取，生成 s1/s2/s3（三种 support）增强版 TBox；仅新增属性。 |
| P4 文献增强 allow1（merge-only） | ✅ | 基于 allow0 的聚合文件合并，生成 allow1 s1/s2/s3；新增类很多但无新增关系。 |
| LLM 超时/代理排查 | ✅ | VSCode SSH 注入代理导致远端请求超时；通过脚本 unset *_proxy 解决。 |
| HF 模型下载失败 | ✅ | 网络限制；通过 ModelScope 预下载到 BAAI/bge-base-zh-v1.5 解决。 |
| OntoQA 指标工具与命令 | ✅ | tools/ontoqa_metrics.py 支持显式 tboxes、增量统计、层级扩展指标；已得到干净结果。 |
| 继续做 P5/ABox 下游评测 | 🔄 | 需要跑抽取与评测并写论文段落。 |

## 关键上下文
**项目位置/环境**：/home/zjx/dev_ops/YangtzeDestoryLLM；SSH + VS Code Remote；本地代理会污染远端 shell。

**重要修复/增强**：
- scripts/run_p4_batch.py：断点续跑（按 doc_id 跳过）、LLM I/O 详细日志、调用间随机 sleep（cfg 开关）、merge-only 不再依赖语料/不初始化 LLM。
- kg/llm_core.py：支持 request_mode（sdk/post/auto）、post 请求实现、disable_response_format 开关、max_tokens 仅 cfg 显式配置才传、LLM_DEBUG/CURL 日志、修复 TabError。
- run_p4_allow0.sh：开头 unset http_proxy https_proxy all_proxy + NO_PROXY 防超时。
- tools/ontoqa_metrics.py：扩展指标 + baseline delta + 新增/移除统计。
- tools/abox_metrics.py：新增 ABox 评测 CLI（strict/relaxed、时间容忍、geo 同义、错误分解）。
- kg/cq_pipeline.py：P5 结果 JSON 兜底解析 + 清洗。

### P4 已完成产物
allow0：
- outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s1_allow0.json
- outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow0.json
- outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s3_allow0.json

allow1（merge-only）：
- outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s1_allow1.json
- outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s2_allow1.json
- outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s3_allow1.json

### 干净 OntoQA 8 版本结果（strict）
- P2：C=34, SC=22, P=25, A=85, RR=0.5319, IR=0.6471, AR=2.50
- P3：C=16, SC=6, P=19, A=85, RR=0.7600, IR=0.3750, AR=5.3125（invalid parent=3）
- P4 allow0：
  - s1：C=16, P=19, A=180, RR=0.7600, IR=0.3750, AR=11.25
  - s2：C=16, P=19, A=100, RR=0.7600, IR=0.3750, AR=6.25
  - s3：C=16, P=19, A=90, RR=0.7600, IR=0.3750, AR=5.625
- P4 allow1：
  - s1：C=183, P=19, A=426, RR=0.7600, IR=0.0328, AR=2.3279
  - s2：C=48, P=19, A=131, RR=0.7600, IR=0.1250, AR=2.7292
  - s3：C=34, P=19, A=102, RR=0.7600, IR=0.1765, AR=3.00

**解释要点**：allow1 新增类多数无 parent/无关系附着 → IR/AR 降；support 越严格越保守、结构越可靠。

## 走不通/已规避的路
- 直接 python scripts/run_p4_batch.py 在非 repo 根目录会报 ModuleNotFoundError: kg；必须在 repo 根目录并 PYTHONPATH=. 或用 bash run_p4_allow*.sh。
- 远端 shell 里保留 VSCode 注入代理会导致 LLM ProxyError/timeout；需 unset *_proxy。

## 下一步建议
### 选“主版本” TBox 做下游评测
推荐默认：allow0-s1（结构稳定 + AR 最高）。
消融/对照：allow0-s2/s3（support 消融）、allow1-s3（允许新类但更严格 support）。

### 跑 P5 抽取 +（可选）ABox 评测的一键脚本
```bash
unset http_proxy https_proxy all_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY
bash run_post_p4_and_p5_eval.sh outputs/cq_pipeline/final_with_hierarchy/p4_tbox_augmented_s1_allow0.json
```
**输出**：
- dev：outputs/p5_eval/p4_tbox_augmented_s1_allow0/dev/p5_batch_results.jsonl
- test：outputs/p5_eval/p4_tbox_augmented_s1_allow0/test/p5_batch_results.jsonl

若存在 gold（data/p5_eval_pool/dev_gold.jsonl / test_gold.jsonl），会自动评测并写到 outputs/abox/*.json。

### 如果没有 gold，先补标注再评测
按 txts/improve/5-kg抽取/todo - ABox 抽取评测.md 的格式整理 dev/test gold。
之后重跑上面的脚本或单独跑：
```bash
python3 tools/abox_metrics.py --gold data/p5_eval_pool/dev_gold.jsonl \
  --pred outputs/p5_eval/<BEST_STEM>/dev/p5_batch_results.jsonl \
  --tbox <BEST_TBOX>.json --time-tolerance-days 1 \
  --geo-syn resources/geo_synonyms.json \
  --out outputs/abox/metrics_dev_<BEST_STEM>.json
```

### 论文实验写作结构
- 表 1：OntoQA 核心指标（8 版本），来自 outputs/ontoqa/metrics_full_clean.csv。
- 表 2：消融（support / allow_new_classes）对新增元素与结构的影响（ΔC/ΔA/IR/AR）。
- 表 3：P5/ABox 抽取效果（dev/test F1 + error breakdown），对照 OntoQA 解释结构/属性变化对下游的作用。
- 局限性备注：invalid parent=3（说明已检测，后处理可置空，不影响结论）。

## 相关文件/配置
- scripts/run_p4_batch.py：P4 批量增强（断点续跑、sleep cfg、merge-only 修复、LLM I/O logging）。
- kg/llm_core.py：LLMClient 封装（post 模式、debug curl、disable_response_format、max_tokens 语义）。
- kg/cq_pipeline.py：P5 抽取与 JSON 兜底/清洗。
- configs/cfg.yaml：LLM 配置、P4 sleep 开关与区间。
- run_p4_allow0.sh：P4 allow0 全抽取（已处理代理问题）。
- run_p4_allow1_merge_only.sh：P4 allow1 merge-only（不再调用 LLM）。
- run_post_p4_and_p5_eval.sh：跑 OntoQA + P5(dev/test) 抽取 + ABox 评测的一键脚本。
- tools/ontoqa_metrics.py：OntoQA 指标计算与导出。
- tools/abox_metrics.py：ABox/事件/三元组评测工具。
- outputs/ontoqa/metrics_full_clean.*：干净 OntoQA 结果（论文表格来源）。
- outputs/cq_pipeline/final_with_hierarchy/*.json：P3/P4 最终 TBox 版本（对比/消融输入）。