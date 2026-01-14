接力文档：文档级别筛选与高质量子集评估
当前任务状态
目标：实现文档级别筛选功能，筛选出高质量文档用于展示 60-70% 的评估指标
进度：已完成筛选功能实现和验证，待确认后续用途
当前卡点：用户指出 test_high_quality.jsonl 实际上是 Gold 标注文件，需要明确实际需求
已探索路径
方向	状态	备注
文档级别筛选 (doc 模式)	✅	按单文档阈值筛选，已实现并验证
聚合指标筛选 (aggregate 模式)	✅	贪心算法，尽量多保留文档同时保证整体指标，已实现
导出高质量 doc_id	✅	87 个 doc_id 已导出到 high_quality_doc_ids.txt
创建子集测试文件	✅	test_high_quality.jsonl 已创建（85 条记录）
关键上下文
下个 session 必须知道的信息

筛选原理：纯筛选，无数据编造。对每个文档计算 Gold vs Pred 的 F1，低于阈值则移除

筛选结果对比：

阈值 (E, T, Ev)	保留文档	Entity F1	Triple F1	Event F1
(0.5, 0.3, 0.5)	60 (11%)	78.73%	71.42%	94.72%
(0.4, 0.2, 0.4)	87 (16%)	68.98%	60.62%	93.26%
关键发现：test_final.jsonl 包含 Gold 标注（entities, triples, events）+ 原始文本（source_text）。筛选出的是"模型抽取效果较好的文档"，不代表模型真正提升

bidirectional_fusion.py 新增功能：

--filter-mode doc：按单文档阈值筛选
--filter-mode aggregate：按聚合指标筛选（贪心算法）
--export-doc-ids：导出保留文档的 doc_id 列表
下一步建议
明确用途：

如果是展示高指标：直接用筛选后的 Gold/Pred 评估
如果是改进模型：分析被过滤的低质量文档，找出模型弱点
如需重跑模型：


bash scripts/p5/run_single_model.sh \
    --model "glm-4-flash" \
    --test-file "data/p5_eval_pool/final/test_high_quality.jsonl" \
    --output-base "outputs/eval_models_high_quality"
相关文件/配置
scripts/p5/bidirectional_fusion.py：文档级别筛选工具（已增强）
outputs/fusion/doc_filtered_relaxed/：筛选结果目录
gold_filtered.jsonl：筛选后的 Gold
pred_filtered.jsonl：筛选后的 Pred
high_quality_doc_ids.txt：87 个高质量 doc_id
doc_metrics.jsonl：每个文档的指标详情
data/p5_eval_pool/final/test_high_quality.jsonl：高质量子集测试文件（85 条）
outputs/fusion/doc_filtered_relaxed/metrics.json：筛选后的整体指标