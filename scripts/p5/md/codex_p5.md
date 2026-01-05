已把剩余可补的部分补上，并核对了 CQLLMPipeline 的 use-verify 能力。要点如下：

cq_pipeline.py：extract_events 现在支持 use_cot（CoT prompt + 解析），所以 --no-cot 真正生效；同时 extract_events_with_verification 本身就支持 use_cot 和原文回溯校验。
run_extraction_on_test.py：use_verify=True 时改为直接调用 extract_events_with_verification，use_verify=False 时走 extract_events(use_cot=...)，从而让 CoT/Verify 两个开关都“真实切换”。
run_model_comparison.sh / run_single_model.sh：新增 --relation-mapping，对齐后可选执行关系映射，再用映射后的 gold/pred 评测。
analyze_schema_drift.py：加入轻量归一化（大小写/空白/分隔符），避免误判漂移。

