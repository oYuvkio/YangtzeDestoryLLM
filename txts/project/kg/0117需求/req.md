1、我现在运行了ner的demo脚本，如下：
CUDA_VISIBLE_DEVICES=0,1,2 python -m scripts.p5.baseline.yayi_uie batch \
    --test-file outputs/eval_models/gold/merge_filted_3.jsonl \
    --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
    --tbox outputs/kg_final/tbox_final.json \
    --task-type ner \
    --output outputs/eval_models/yayi_uie/predictions_ner.jsonl \
    --skip-existing
输出文件为：
outputs/eval_models/yayi_uie/predictions_ner.jsonl
输出的raw_output为：
[ner] {"Location": ["长江", "长江下游地区"], "FloodEvent": ["2016年、2020年长江流域大洪水"], "HazardFactor": ["洪水"]}
你需要正确解析到 "entities": [] 字段中，修改这部分代码。
可参考re的脚本，re部分是解析成功了的
CUDA_VISIBLE_DEVICES=0,1,2 python -m scripts.p5.baseline.yayi_uie batch \
    --test-file outputs/eval_models/gold/merge_filted_3.jsonl \
    --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
    --tbox outputs/kg_final/tbox_final.json \
    --task-type re \
    --output outputs/eval_models/yayi_uie/predictions_re.jsonl \
    --skip-existing

解析之后的entity的形式我认为应该是
"entities": [{"Location": ["长江", "长江下游地区"],....}]

3、我目前提取gold和test的实体和三元组的输出格式要与上述对齐，且在Prompt中的few-shot示例也需要对齐，你需要修改这部分代码

#gold提取
conda activate YangtzeLLM && python scripts/generate_gold_with_tbox.py \
  --input data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --output data/p5_eval_pool/gold_hybrid_tbox_longcat_0113.jsonl \
  --model "LongCat-Flash-Chat" \
  --base-url "https://api.longcat.chat/openai/v1" \
  --temperature 0.1 \
  --top-p 0.1 \
  --use-cot \
  --use-verification \
  --verification-threshold 0.85 \
  --strict-schema \
  --resume \
  --interval 2 \
  --rate-limit-retries 2
  2>&1 | tee outputs/eval_models_hybrid/gold_hybrid_tbox_longcat_0113.log


#pred提取
conda activate YangtzeLLM && python scripts/p5/run_extraction_on_test.py \
  --test-file data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --text-source data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl \
  --tbox outputs/kg_final/tbox_final.json \
  --model "gpt-4o-mini" \
  --base-url "https://x666.me/v1/" \
  --api-key "sk-SgzHNynm92rMPoR2cw33XQvBShqoa4JdD6qf2pMmmZ9VmZHh" \
  --temperature 0.1 \
  --top-p 0.1 \
  --output outputs/eval_models_hybrid/predictions_gpt-4o-mini_0113.jsonl \
  --fuzzy-threshold 0.75 \
  --no-strict-schema \
  --skip-existing \
  --interval 10 \
  2>&1 | tee outputs/eval_models_hybrid/predictions_gpt-4o-mini_0113.log
  
注意：无需关注事件提取，这部分代码修改可以忽略

5、修改后计算pred和gold的指标需查看是否需要更改 tools/abox_metrics.py，scripts/p5/run_single_model.sh