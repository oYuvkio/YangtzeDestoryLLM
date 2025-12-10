

现状：
0、经过我的语料处理工具：
┌原始语料 (PDF/TXT/...)
        ↓
┌───────────────────────────────────────┐
│  corpus_cleaner.py (阶段 1)           │
│  - PDF/TXT 解析提取文本               │
│  - 去页眉页脚、目录、噪声             │
│  - 按章节/段落智能切分                │
│  - 生成标准化片段 + 元数据            │
└───────────────────────────────────────┘
        ↓
   切分后的 .txt 片段（handled_corpus/）
        ↓
┌───────────────────────────────────────┐
│  filter_corpus_light.py (阶段 2)      │
│  - 粗规则过滤（汉字比例、关键词）     │
│  - LLM 质量判定（领域相关性）         │
│  - 输出 light_pool.jsonl  （去重后得到light_pool_dedup）              │
└───────────────────────────────────────┘

经过严格的筛选得到了 eval_pool.json：
2. 执行结果
数据抽样统计
统计项	数量
输入数据	1517 条
抽样后	440 条
Dev 集	264 条 (60%)
Test 集	176 条 (40%)
按 topic_label 分层抽样目标（默认配置）
主题类型	目标数量
disasterevent	150
measure_response	180
backgroundanalysis	50
institution_regulation	50
impact_assessment	10
3. 生成文件结构
plaintext
data/p5_eval_pool/
├── pool.jsonl  (440 条)  # 抽样后总数据
├── dev.jsonl   (264 条)  # 开发集（60%）
└── test.jsonl  (176 条)  # 测试集（40%）

总结
1. 核心新增参数 --stratify-by 支持按 source_type（默认）或 topic_label 分层抽样；
2. 抽样后总数据 440 条，按 6:4 拆分 Dev/Test 集，按 topic_label 分层有明确的数量目标；
3. 最终生成 pool.jsonl/dev.jsonl/test.jsonl 三个文件，存放于指定输出目录。

pool.json 参考 [text](../../data/corpus_for_kg/eval_pool)




1、我的cq问题是基于目前最强的模型，通过网页提问的，保存到了
outputs/cq_pipeline/final/p1_cqs_train.json和outputs/cq_pipeline/final/p1_cqs_test.json中

[text](../../outputs/cq_pipeline/final/p1_cqs_test.json)


2、基于以上的p1_cqs_train.json，从问题归纳了从CQ归纳类/关系/属性，得到了outputs/cq_pipeline/final/p2_tbox_init.json 



3、经过 p3的规范化、层次化得到了 outputs/cq_pipeline/final/p3_tbox_normalized.json



我的问题：
1、之前用于增强p4的语料没有经过清洗，现在有了经过清洗的语料，内容很丰富，用了其中的一部分去构建了eval_pool，那应该选什么的去增强本体呢？ 跟构建eval_pool的部分冲突吗？（需要在论文中有说服力）



2、我参考的论文要求:
● 在P2阶段(CQ扩展)使用 text-embedding-3-large 计算余弦相似度
● 阈值 > 0.7 判定为重复并剔除
● 自动过滤 + 人工微调
但我目前还没做这些

3、p4增强完之后还需要去重吗？


4、现在我该怎么做？ 怎么对比？怎么做消融实验？


我的参考论文为 [text](../survey/water_summary.md)

