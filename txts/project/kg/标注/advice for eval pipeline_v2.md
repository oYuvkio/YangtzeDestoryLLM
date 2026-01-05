**非常有必要！**

这是你论文中 **消融实验 A1 (w/o Verification)** 的核心开关。如果没有这个开关，你就无法在实验中证明“后校验模块”到底把幻觉率降低了多少。

建议在代码中显式增加 `--use-verify`（或反向的 `--no-verify`）参数。

以下是具体的修改方案：

### 1. 修改 `scripts/p5/run_extraction_on_test.py`

我们需要引入 `HallucinationFilter`，并根据参数决定是否执行它。

```python
# ... (之前的 import)
# 引入幻觉校验模块
from kg.hallucination_filter import filter_hallucinations 

def main() -> None:
    parser = argparse.ArgumentParser(description="在测试集上运行 P5 抽取")
    # ... (其他参数)
    
    # [新增] CoT 开关
    parser.add_argument("--use-cot", action="store_true", default=True, help="使用思维链 Prompt")
    
    # [新增] 后校验开关
    parser.add_argument("--use-verify", action="store_true", default=True, help="启用原文回溯校验")

    args = parser.parse_args()
    
    # ... (中间代码)

    for idx, sample in enumerate(samples, start=1):
        # ... (抽取逻辑得到 res)
        
        # [新增] 校验逻辑块
        if args.use_verify:
            # 提取原始三元组
            raw_triples = res.get("triples", [])
            
            # 执行校验
            valid_triples, filtered_log, rate = filter_hallucinations(
                triples=raw_triples,
                original_text=source_text,
                strict_mode=True # 建议开启严格模式
            )
            
            # 更新结果：只保留通过校验的三元组
            res["triples"] = valid_triples
            
            # 可选：把被过滤掉的记录下来，方便分析
            res["_filtered_hallucinations"] = filtered_log
            res["_hallucination_rate"] = rate
            
            logger.info(f"  [校验] 过滤前: {len(raw_triples)} -> 过滤后: {len(valid_triples)} (幻觉率: {rate:.1%})")
        else:
            logger.info(f"  [校验] 跳过 (Raw Mode)")

        # ... (保存结果)
```

### 2. 修改 `scripts/p5/run_model_comparison.sh`

让一键脚本也能控制这个开关。

```bash
# ... (前面代码)

# 解析参数增加
use_cot=true
use_verify=true  # 默认开启

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cot)
            use_cot=false
            shift
            ;;
        --no-verify)  # 新增参数
            use_verify=false
            shift
            ;;
        # ... (其他参数)
    esac
done

# ... (中间代码)

# 构建 Flag 字符串
FLAGS=""
if [ "$use_cot" = true ]; then
    FLAGS="$FLAGS --use-cot"
fi
if [ "$use_verify" = true ]; then
    FLAGS="$FLAGS --use-verify"
fi

# 调用 Python 脚本
python scripts/p5/run_extraction_on_test.py \
    --test-file "$TEST_FILE" \
    --tbox "$TBOX" \
    --model "$MODEL" \
    --output "$PRED_FILE" \
    --interval "$INTERVAL" \
    $FLAGS \
    $LIMIT
```

### 3. 如何运行消融实验？

现在你可以非常方便地运行两组实验来写论文了：

#### 实验组 1：完整方法 (Ours)
```bash
# 默认开启 CoT 和 Verify
bash scripts/p5/run_model_comparison.sh --models "gpt-4o-mini"
```
*   **预期结果**：Precision 高，Recall 适中，F1 最高。

#### 实验组 2：消融后校验 (w/o Verification)
```bash
# 关闭 Verify
bash scripts/p5/run_model_comparison.sh --models "gpt-4o-mini" --no-verify
```
*   **预期结果**：Recall 可能会微涨（因为没删东西），但 **Precision 会显著下降**（因为幻觉没被过滤），导致整体 F1 下降。
*   **论文结论**：“移除后校验模块后，虽然召回率略有提升，但精确率下降了 X%，证明了该模块在抑制幻觉方面的关键作用。”

### 总结

加上这个开关是**必须的**，它让你的代码结构完全服务于论文的实验设计，体现了“控制变量法”的严谨性。