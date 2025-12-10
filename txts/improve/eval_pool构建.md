那现在 eval_pool不需要使用llm来过滤了吧？   现在的代码还需要更改吗？ 


这是我的建议：把 EVAL 构建改为纯规则与随机种子（无 LLM） 


任务：将 build_eval_pool.py 改为纯规则评测集构建，不再调用任何 LLM。数据来源为已清洗语料 + 现成元数据（topic_label、source_type 等），或用正则/词典自动标注。

[改动点]
1) 去除/屏蔽 LLM 判定逻辑
   - 删除/禁用所有模型打分或领域相关性判断。
   - 仅使用以下确定性过滤器：
     a) 文本长度：min_chars <= len(text) <= max_chars
     b) 时间/地点/数值证据（正则检测至少命中1类）：
        - 时间：\b(19|20)\d{2}年|\b(19|20)\d{2}-\d{1,2}-\d{1,2}
        - 地点：省/市/县/流域/湖泊等词典匹配（例如 {长江上游, 湖北省, 武汉市, 鄱阳湖}）
        - 数值：\d+(\.\d+)?\s?(m³/s|m|亿元|万人|hm²|km²|天)
     c) 叙事结构关键词（至少命中1类）：
        - 事件：{洪水, 干旱, 汛情, 枯水, 伏旱, 洪峰}
        - 影响：{受灾, 经济损失, 减产, 超警, 饮水困难}
        - 响应/措施：{防汛响应, 抗旱响应, 调度, 泄洪, 预警}
   - 以上规则用于确定“事实性段落”，作为 EVAL 候选池。

2) topic_label 分层来源
   - 若输入里已有 topic_label（来自早期过滤产物），直接复用，不再重算。
   - 若缺失：用规则自动赋值（映射表）：
     - 命中事件类词 + 时间/地点 → disasterevent
     - 命中响应/措施类词 → measure_response
     - 命中宏观分析词（趋势/成因/背景/ENSO/厄尔尼诺/气候） → backgroundanalysis
     - 命中法规/制度类词（条例/规定/预案/制度/职责） → institution_regulation
     - 仅含损失/面积/人数等影响量化 → impact_assessment
   - 将映射写成字典 + 规则函数，日志打印每条样本最终标签与命中依据。

3) 分层抽样与拆分
   - 对候选池按 topic_label 设定目标配额（与现有默认一致即可），采用 StratifiedShuffleSplit（seed 固定）。
   - 6:4 划分 dev/test，保证每类占比接近目标。
   - 输出文件结构与字段保持不变：pool.jsonl / dev.jsonl / test.jsonl。

4) 互斥保证
   - 若引入 manifest（purpose=EVAL），只从目的为 EVAL 的样本里抽；否则在当前输入内通过 doc_id/rel_path 去重。
   - 与 P4/P5 数据集合保持 doc_id（或 section_id）级互斥（若提供 manifest 则严格按 manifest 过滤）。

5) 统计与日志
   - 打印：输入量、规则命中计数（时间/地点/数值/关键词）、每类样本数量、最终 dev/test 分布。
   - 将 seed、阈值、命中率写入日志文件，便于盲审复现。

[CLI]
python tools/build_eval_pool.py \
    --input-jsonl "data/corpus_for_kg/filtered_ytz_corpus/light_pool_dedup.jsonl" \
    --out-dir "data/corpus_for_kg/eval_pool" \
    --min-chars 250 \
    --max-chars 2000 \
    --stratify-by topic_label \
    --log-file "logs/kg_eval/build_eval_pool.log" \
    --seed 42 \
    --use-manifest "data/manifests/purpose_manifest.jsonl" \
    --require-purpose "EVAL"

[验收]
- 代码中不再出现任何 LLM/embedding 调用。
- 日志包含：规则命中统计、各类分布、seed、输入输出文件指纹（md5）。
- 与 P4/P5 样本集合无交集（按 doc_id/section 校验）。
