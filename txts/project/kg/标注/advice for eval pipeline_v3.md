
# 建议一：
你的修改思路非常清晰，整体方案是合理的。但在 **`argparse` 参数设计** 和 **Shell 脚本逻辑** 上存在一个常见的逻辑陷阱，如果不修正，消融实验可能无法生效。

以下是详细的代码审查（Code Review）和修正建议：

### 🔴 关键问题：Argparse 的 `default=True` 陷阱

在 `run_extraction_on_test.py` 中，你写了：
```python
parser.add_argument("--use-verify", action="store_true", default=True, help="启用原文回溯校验")
```
**问题**：`action="store_true"` 的机制是：如果命令行出现了这个参数，变量设为 `True`；如果没有出现，变量设为 `default` 值。
*   如果 `default=True`：
    *   不传参数 -> `True`
    *   传 `--use-verify` -> `True`
    *   **结论：你永远无法在命令行把它关掉！**

**修正方案**：建议改为反向逻辑参数 `--no-verify`，或者将默认值设为 `False` 并显式开启。为了符合“默认开启最佳配置”的直觉，建议使用 **`--no-verify`**。

---

### ✅ 修正后的代码实现

#### 1. 修改 `scripts/p5/run_extraction_on_test.py`

**改动点**：
1.  引入 `HallucinationFilter`。
2.  参数改为 `--no-verify`。
3.  逻辑判断改为 `if not args.no_verify:`。

```python
# ... (imports)
# [新增] 引入幻觉校验模块 (确保路径正确)
try:
    from kg.hallucination_filter import filter_hallucinations
except ImportError:
    # 容错处理，防止模块未找到导致脚本崩溃
    def filter_hallucinations(*args, **kwargs):
        return [], [], 0.0
    print("[WARN] 未找到 kg.hallucination_filter，校验功能将不可用")

def main() -> None:
    parser = argparse.ArgumentParser(description="在测试集上运行 P5 抽取")
    # ... (其他参数)
    
    # [修改] CoT 参数逻辑优化
    parser.add_argument("--no-cot", action="store_true", help="禁用思维链 Prompt (默认开启 CoT)")
    
    # [修改] 后校验参数逻辑优化 (默认开启，通过 --no-verify 关闭)
    parser.add_argument("--no-verify", action="store_true", help="禁用原文回溯校验 (默认开启校验)")

    args = parser.parse_args()
    
    # 逻辑转换
    use_cot = not args.no_cot
    use_verify = not args.no_verify
    
    logger = setup_logger()
    logger.info(f"配置状态: CoT={use_cot}, Verification={use_verify}")

    # ... (中间代码)

    for idx, sample in enumerate(samples, start=1):
        # ... (抽取逻辑得到 res)
        
        # [新增] 校验逻辑块
        if use_verify:
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
            
            # 记录元数据，方便后续分析被过滤掉的内容
            res["_meta_hallucination"] = {
                "is_filtered": True,
                "original_count": len(raw_triples),
                "filtered_count": len(filtered_log),
                "rate": rate,
                "logs": filtered_log
            }
            
            if len(filtered_log) > 0:
                logger.info(f"  [校验] 过滤幻觉: {len(raw_triples)} -> {len(valid_triples)} (幻觉率: {rate:.1%})")
        else:
            # 如果不校验，也记录一下状态
            res["_meta_hallucination"] = {"is_filtered": False}

        # ... (保存结果)
```

#### 2. 修改 `scripts/p5/run_model_comparison.sh`

**改动点**：适配 Python 脚本的 `--no-verify` 参数逻辑。

```bash
# ... (前面代码)

# 默认状态
NO_COT=false
NO_VERIFY=false

# 解析命令行参数
while [[ $# -gt 0 ]]; do
    case $1 in
        --no-cot)
            NO_COT=true
            shift
            ;;
        --no-verify)  # 新增参数处理
            NO_VERIFY=true
            shift
            ;;
        # ... (其他参数)
    esac
done

# ... (中间代码)

# 构建 Flag 字符串
FLAGS=""
if [ "$NO_COT" = true ]; then
    FLAGS="$FLAGS --no-cot"
fi
if [ "$NO_VERIFY" = true ]; then
    FLAGS="$FLAGS --no-verify"
fi

echo "运行配置: CoT=$( [ "$NO_COT" = true ] && echo "OFF" || echo "ON" ) | Verify=$( [ "$NO_VERIFY" = true ] && echo "OFF" || echo "ON" )"

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

---

### 🔍 审查总结

1.  **逻辑合理性**：**合理**。增加后校验开关是进行消融实验（Ablation Study）的必要条件，能够量化“后校验模块”对 Precision 和 Hallucination Rate 的贡献。
2.  **代码安全性**：
    *   修正了 `argparse` 的布尔值陷阱。
    *   增加了 `ImportError` 的容错处理。
    *   在结果 JSON 中增加了 `_meta_hallucination` 字段，这对你写论文时的案例分析（Case Study）非常有用（可以直接看到哪些具体的幻觉被过滤了）。
3.  **实验设计匹配度**：
    *   **Baseline (Ours)**: 不传参（默认开启 CoT + Verify）。
    *   **Ablation 1 (-CoT)**: 传 `--no-cot`。
    *   **Ablation 2 (-Verify)**: 传 `--no-verify`。

**建议**：直接采用上述修正后的代码。在运行消融实验前，建议先用 `--limit 5` 跑一个小样本，检查日志中是否正确输出了 `[校验] 过滤幻觉...` 或 `配置状态: Verification=False`，以确保开关生效。




# 建议二

发现的问题（按严重度）

高：--no-cot 实际不生效。run_extraction_on_test.py 里只是计算 use_cot 并写入输出字段，但未影响 pipeline.extract_events 的实际提示词/流程，导致 CoT 消融与默认结果一致。run_extraction_on_test.py (lines 121-179), run_extraction_on_test.py (line 245)

高：评测脚本未纳入“关系映射”步骤，导致 gold 的独立关系与 pred 的项目关系直接评测，F1 会系统性偏低；而你已新增 apply_relation_mapping.py 却未在流程中使用。run_model_comparison.sh (lines 158-179)

中：--favor-existing-classes 使用 store_true 且默认 True，无法关闭该行为（参数实际“不可切换”）。run_extraction_on_test.py (lines 112-113)

低：analyze_schema_drift.py 未做关系名归一化（大小写/空白/标点），对边界情况统计可能不准。analyze_schema_drift.py (lines 41-58)

假设/待明确

如果评测采用标准关系（独立 schema），tbox_consistency 的口径是否仍要求基于项目 TBox？若使用标准关系映射后直接算 TBox 一致性，可能被低估（因为标准关系未必在项目 TBox 中）。


建议修正方向（可选）


让 use_cot 真正影响抽取（需要 CQLLMPipeline 支持切换 prompt）。
在 run_model_comparison.sh 中插入 apply_relation_mapping.py，并将评测改为对映射后的 pred/gold 进行。
将 --favor-existing-classes 改为互斥开关（--favor-existing-classes/--no-favor-existing-classes）。


