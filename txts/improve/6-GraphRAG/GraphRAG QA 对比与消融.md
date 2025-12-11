目标：完成论文第四章的 QA 实证与消融。

任务：新增 experiments/exp_qa_comparison.py，比对 4 种系统：
  1) BM25 RAG
  2) Vector RAG（bge-base-zh）
  3) GraphRAG（向量种子→多跳子图）
  4) GraphRAG + TBox 约束抽取证据

[改动点]
1) 统一接口：
   run_qa(system_name, questions_json, evidence_pool_jsonl, graph_store, tbox_path, max_hops)
   - 输出：每问答案、证据引用（文档/三元组ID）、置信度
2) 评测：
   - 输入问题集：outputs/cq_pipeline/final/p1_cqs_test.json
   - 证据文本：data/p5_eval_pool/test.jsonl
   - 图谱：Neo4j 或 NetworkX（项目已有），参数 --graph-backend=networkx|neo4j
   - 指标：accuracy, recall（用专家关键词/要点表 gold_qa.json 对齐），faithfulness（答案要点是否被证据三元组支撑）
3) 输出：
   - experiments/reports/qa_metrics.json
   - experiments/reports/qa_cases.md（列出若干样例：问题→答案→证据→评语）

[CLI]
python experiments/exp_qa_comparison.py \
  --questions outputs/cq_pipeline/final/p1_cqs_test.json \
  --evidence data/p5_eval_pool/test.jsonl \
  --tbox outputs/cq_pipeline/final/p4_tbox_enhanced.json \
  --graph-backend networkx \
  --max-hops 2 \
  --out "experiments/reports/qa_metrics.json" \
  --cases "experiments/reports/qa_cases.md" \
  --log-file "logs/qa/compare.log" \
  --seed 42

[验收标准]
- 输出包含 4 套系统的指标对比；GraphRAG(+TBox) 最好或接近最好
- cases.md 展示 5-10 条可读样例（问题-证据链-答案）
