#!/bin/bash
# =============================================================================
# 统一消融实验脚本（支持 --args 扩展参数）
#
# 示例：
#   bash scripts/p5/baseline/run_ablation_unified.sh all \
#     --model "gpt-4o-mini" \
#     --base-url "https://x666.me/v1/" \
#     --api-key "sk-xxx" \
#     --test-file "outputs/eval_models/gold/merge_filted_2.jsonl" \
#     --text-source "data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl" \
#     --tbox "outputs/kg_final/tbox_final.json" \
#     --output-base "outputs/eval_models_hybrid/gpt"
#
# 仅评测（跳过抽取）：
#   bash scripts/p5/baseline/run_ablation_unified.sh all --eval-only \
#     --output-base "outputs/eval_models_hybrid/gpt" \
#     --eval-test-file "outputs/eval_models_hybrid/qwen235b/full/predictions.jsonl"
#
# 追加额外参数（传给 run_extraction_on_test.py）：
#   --args "--no-graph --strict-filter"
# =============================================================================

set -e

# 禁用 HTTP/HTTPS 代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY

# =============================================================================
# Conda 环境
# =============================================================================
CONDA_ENV="YangtzeLLM"

if [ -f "/home/zjx/miniconda3/etc/profile.d/conda.sh" ]; then
    # shellcheck disable=SC1091
    . /home/zjx/miniconda3/etc/profile.d/conda.sh
elif [ -f "/home/zjx/anaconda3/etc/profile.d/conda.sh" ]; then
    # shellcheck disable=SC1091
    . /home/zjx/anaconda3/etc/profile.d/conda.sh
fi

if command -v conda >/dev/null 2>&1; then
    eval "$(conda shell.bash hook)"
    conda activate "${CONDA_ENV}"
    echo "已激活 Conda 环境: ${CONDA_ENV}"
else
    echo "[WARN] conda 未找到，跳过环境激活"
fi

# =============================================================================
# 默认配置
# =============================================================================
EXPERIMENT="all"
MODEL=""
BASE_URL=""
API_KEY=""
OUTPUT_BASE="outputs/eval_models_hybrid/ablation"

TEST_FILE="outputs/eval_models/gold/merge_filted_2.jsonl"
TEXT_SOURCE="data/corpus_for_kg/filtered_ytz_corpus/light_pool_v2_dedup.jsonl"
TBOX="outputs/kg_final/tbox_final.json"

TEMPERATURE=0.1
TOP_P=0.1
FUZZY_THRESHOLD=0.75
INTERVAL=3

RUN_EVAL=true
RUN_COMPARE=true
EVAL_TEST_FILES=()
EVAL_TBOX=""

NO_STRICT_SCHEMA=true
SKIP_EXISTING=true
SUPPORTS_SAMPLING_PARAMS=true

EVAL_ONLY=false
EXTRA_ARGS=()
ALLOW_SYSTEM_ROLE=""
EXTRA_BODY=""
WORKER_COUNT=""
WORKER_ID=""
ENABLE_ENTITY_NORMALIZE=false
FILTER_ERRORS=true
NO_TBOX_FILTER=false
ENTITY_SYNONYMS=""

print_help() {
    cat <<'EOF'
用法:
  bash scripts/p5/baseline/run_ablation_unified.sh [experiment] [options]

experiment:
  full | wo_cot | wo_graph | wo_verify | all | ablation

常用参数:
  --model           模型名称
  --base-url        API base URL
  --api-key         API Key
  --test-file       测试集文件
  --text-source     文本来源文件
  --tbox            TBox 文件
  --output-base     输出基目录
  --temperature     温度
  --top-p           Top-P
  --fuzzy-threshold 模糊匹配阈值
  --interval        请求间隔秒数
  --eval-test-file  评测用的 gold/test 文件（可多次传入或逗号分隔）
  --eval-tbox       评测用的 tbox 文件
  --eval-only       仅评测（默认包含 compare）
  --no-eval         不评测
  --no-compare      不生成对比报告
  --strict-schema   启用严格 schema（默认关闭）
  --no-skip-existing 关闭 skip-existing
  --no-sampling-params 不传 temperature/top-p
  --allow-system-role 是否启用 system role（true/false）
  --enable-entity-normalize 启用实体同义词归一化（评测阶段）
  --no-error-filter 评测阶段不过滤 error 行（对比原始抽取）
  --no-tbox-filter  不计算 TBox 过滤后版本（仅输出 raw 指标）
  --entity-synonyms 实体同义词库路径（评测阶段）
  --extra-body      额外请求体 JSON（传给 run_extraction_on_test.py）
  --worker          worker 总数（启用多进程分片）
  --id              当前 worker 编号（从 0 开始）
  --args            追加参数（空格分隔，直接传给 run_extraction_on_test.py）
  --help            查看帮助
EOF
}

# =============================================================================
# 参数解析
# =============================================================================
while [[ $# -gt 0 ]]; do
    case "$1" in
        full|wo_cot|wo_graph|wo_verify|all|ablation)
            EXPERIMENT="$1"
            shift
            ;;
        --experiment)
            EXPERIMENT="$2"
            shift 2
            ;;
        --model)
            MODEL="$2"
            shift 2
            ;;
        --base-url)
            BASE_URL="$2"
            shift 2
            ;;
        --api-key)
            API_KEY="$2"
            shift 2
            ;;
        --test-file)
            TEST_FILE="$2"
            shift 2
            ;;
        --text-source)
            TEXT_SOURCE="$2"
            shift 2
            ;;
        --tbox)
            TBOX="$2"
            shift 2
            ;;
        --output-base)
            OUTPUT_BASE="$2"
            shift 2
            ;;
        --temperature)
            TEMPERATURE="$2"
            shift 2
            ;;
        --top-p)
            TOP_P="$2"
            shift 2
            ;;
        --fuzzy-threshold)
            FUZZY_THRESHOLD="$2"
            shift 2
            ;;
        --interval)
            INTERVAL="$2"
            shift 2
            ;;
        --eval-test-file)
            IFS=',' read -r -a eval_parts <<< "$2"
            for part in "${eval_parts[@]}"; do
                if [ -n "$part" ]; then
                    EVAL_TEST_FILES+=("$part")
                fi
            done
            shift 2
            ;;
        --eval-tbox)
            EVAL_TBOX="$2"
            shift 2
            ;;
        --eval-only)
            EVAL_ONLY=true
            shift
            ;;
        --no-eval)
            RUN_EVAL=false
            shift
            ;;
        --no-compare)
            RUN_COMPARE=false
            shift
            ;;
        --strict-schema)
            NO_STRICT_SCHEMA=false
            shift
            ;;
        --no-skip-existing)
            SKIP_EXISTING=false
            shift
            ;;
        --no-sampling-params)
            SUPPORTS_SAMPLING_PARAMS=false
            shift
            ;;
        --allow-system-role)
            ALLOW_SYSTEM_ROLE="$2"
            shift 2
            ;;
        --enable-entity-normalize)
            ENABLE_ENTITY_NORMALIZE=true
            shift
            ;;
        --no-error-filter)
            FILTER_ERRORS=false
            shift
            ;;
        --no-tbox-filter)
            NO_TBOX_FILTER=true
            shift
            ;;
        --entity-synonyms)
            ENTITY_SYNONYMS="$2"
            shift 2
            ;;
        --extra-body|--extra_body)
            EXTRA_BODY="$2"
            shift 2
            ;;
        --worker)
            WORKER_COUNT="$2"
            shift 2
            ;;
        --id)
            WORKER_ID="$2"
            shift 2
            ;;
        --args)
            read -r -a arg_parts <<< "$2"
            EXTRA_ARGS+=("${arg_parts[@]}")
            shift 2
            ;;
        --help)
            print_help
            exit 0
            ;;
        *)
            echo "未知参数: $1"
            print_help
            exit 1
            ;;
    esac
done

if [ "${#EVAL_TEST_FILES[@]}" -eq 0 ]; then
    EVAL_TEST_FILES=("${TEST_FILE}")
fi
if [ -z "$EVAL_TBOX" ]; then
    EVAL_TBOX="${TBOX}"
fi

if [ -z "$MODEL" ] && [ "$EVAL_ONLY" != true ]; then
    echo "[ERROR] 未指定 --model（抽取阶段必需）"
    exit 1
fi

if [ -n "$ALLOW_SYSTEM_ROLE" ]; then
    EXTRA_ARGS+=(--allow_system_role "$ALLOW_SYSTEM_ROLE")
fi
if [ -n "$EXTRA_BODY" ]; then
    EXTRA_ARGS+=(--extra_body "$EXTRA_BODY")
fi
if [ -n "$WORKER_COUNT" ] || [ -n "$WORKER_ID" ]; then
    if [ -z "$WORKER_COUNT" ] || [ -z "$WORKER_ID" ]; then
        echo "[ERROR] 多进程模式需要同时指定 --worker 和 --id"
        exit 1
    fi
    EXTRA_ARGS+=(--worker "$WORKER_COUNT" --id "$WORKER_ID" --no-worker-suffix)
    RUN_EVAL=false
    RUN_COMPARE=false
    echo "[WARN] 多进程分片模式下默认跳过评测与对比，请合并后再评测。"
fi

OUTPUT_BASE_EFFECTIVE="${OUTPUT_BASE}"
if [ -n "$WORKER_COUNT" ] || [ -n "$WORKER_ID" ]; then
    OUTPUT_BASE_EFFECTIVE="${OUTPUT_BASE}_${WORKER_ID}"
fi

mkdir -p "${OUTPUT_BASE_EFFECTIVE}"/{full,wo_cot,wo_graph,wo_verify}

# =============================================================================
# 公共参数
# =============================================================================
COMMON_ARGS=(
    --test-file "${TEST_FILE}"
    --tbox "${TBOX}"
    --model "${MODEL}"
    --fuzzy-threshold "${FUZZY_THRESHOLD}"
    --interval "${INTERVAL}"
)

if [ -n "$TEXT_SOURCE" ]; then
    COMMON_ARGS+=(--text-source "${TEXT_SOURCE}")
fi
if [ -n "$BASE_URL" ]; then
    COMMON_ARGS+=(--base-url "${BASE_URL}")
fi
if [ -n "$API_KEY" ]; then
    COMMON_ARGS+=(--api-key "${API_KEY}")
fi
if [ "$SUPPORTS_SAMPLING_PARAMS" = true ]; then
    COMMON_ARGS+=(--temperature "${TEMPERATURE}" --top-p "${TOP_P}")
fi
if [ "$NO_STRICT_SCHEMA" = true ]; then
    COMMON_ARGS+=(--no-strict-schema)
fi
if [ "$SKIP_EXISTING" = true ]; then
    COMMON_ARGS+=(--skip-existing)
fi
if [ "${#EXTRA_ARGS[@]}" -gt 0 ]; then
    COMMON_ARGS+=("${EXTRA_ARGS[@]}")
fi

# =============================================================================
# 实验函数
# =============================================================================
run_full() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: full（完整模型）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE_EFFECTIVE}/full/predictions.jsonl" \
        2>&1 | tee "${OUTPUT_BASE_EFFECTIVE}/full/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] full 完成"
}

run_wo_cot() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: wo_cot（禁用思维链）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE_EFFECTIVE}/wo_cot/predictions.jsonl" \
        --no-cot \
        2>&1 | tee "${OUTPUT_BASE_EFFECTIVE}/wo_cot/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wo_cot 完成"
}

run_wo_graph() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: wo_graph（禁用图结构检测）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE_EFFECTIVE}/wo_graph/predictions.jsonl" \
        --no-graph \
        2>&1 | tee "${OUTPUT_BASE_EFFECTIVE}/wo_graph/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wo_graph 完成"
}

run_wo_verify() {
    echo "============================================================"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始运行: wo_verify（禁用后校验）"
    echo "============================================================"
    python scripts/p5/run_extraction_on_test.py \
        "${COMMON_ARGS[@]}" \
        --output "${OUTPUT_BASE_EFFECTIVE}/wo_verify/predictions.jsonl" \
        --no-verify \
        2>&1 | tee "${OUTPUT_BASE_EFFECTIVE}/wo_verify/predictions.log"
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] wo_verify 完成"
}

run_all() {
    echo "============================================================"
    echo "开始运行全部消融实验"
    echo "============================================================"
    run_full
    run_wo_cot
    run_wo_graph
    run_wo_verify
    echo "============================================================"
    echo "全部消融实验完成！"
    echo "============================================================"
}

run_ablation_only() {
    echo "============================================================"
    echo "开始运行消融实验（跳过 full）"
    echo "============================================================"
    run_wo_cot
    run_wo_graph
    run_wo_verify
    echo "============================================================"
    echo "消融实验完成！"
    echo "============================================================"
}

run_eval_variant() {
    local variant="$1"
    local pred_file="${OUTPUT_BASE}/${variant}/predictions.jsonl"
    if [ ! -f "$pred_file" ]; then
        echo "[WARN] ${variant} 预测文件不存在，跳过评测: ${pred_file}"
        return
    fi

    local eval_args=()
    if [ "$ENABLE_ENTITY_NORMALIZE" = true ]; then
        eval_args+=(--enable-entity-normalize)
    fi
    if [ "$FILTER_ERRORS" = false ]; then
        eval_args+=(--no-error-filter)
    fi
    if [ "$NO_TBOX_FILTER" = true ]; then
        eval_args+=(--no-tbox-filter)
    fi
    if [ -n "$ENTITY_SYNONYMS" ]; then
        eval_args+=(--entity-synonyms "$ENTITY_SYNONYMS")
    fi

    local total_eval="${#EVAL_TEST_FILES[@]}"
    for eval_file in "${EVAL_TEST_FILES[@]}"; do
        local eval_name
        eval_name="$(basename "$eval_file")"
        eval_name="${eval_name%.*}"
        local out_base="${OUTPUT_BASE}/${variant}"
        if [ "$total_eval" -gt 1 ]; then
            out_base="${OUTPUT_BASE}/${variant}/eval_${eval_name}"
        fi
        echo "============================================================"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] 开始评测: ${variant} (gold=${eval_file})"
        echo "============================================================"
        bash scripts/p5/run_single_model.sh \
            --tbox "${EVAL_TBOX}" \
            --test-file "${eval_file}" \
            --pred-file "${pred_file}" \
            --eval-only \
            --output-base "${out_base}" \
            "${eval_args[@]}"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${variant} 评测完成: ${eval_file}"
    done
}

run_compare() {
    local models=("$@")
    if [ "${#models[@]}" -eq 0 ]; then
        return
    fi

    echo "============================================================"
    echo "生成对比报告..."
    echo "============================================================"
    python scripts/p5/compare_models.py \
        --input-dir "${OUTPUT_BASE}" \
        --models "${models[*]}" \
        --version raw \
        --output "${OUTPUT_BASE}/comparison_report_raw.json"

    if [ "$NO_TBOX_FILTER" = false ]; then
        python scripts/p5/compare_models.py \
            --input-dir "${OUTPUT_BASE}" \
            --models "${models[*]}" \
            --version tbox_filtered \
            --output "${OUTPUT_BASE}/comparison_report_tbox_filtered.json"
    else
        echo "[INFO] 已开启 --no-tbox-filter，跳过 tbox_filtered 对比报告"
    fi
}

# =============================================================================
# 多 gold 汇总（横向表格）
# =============================================================================
print_multi_eval_summary() {
    python3 - <<'PY'
import json
from pathlib import Path

output_base = Path("""'"$OUTPUT_BASE"'""")
variants = """'"${RAN_VARIANTS[*]}"'""".split()
eval_files = """'"${EVAL_TEST_FILES[*]}"'""".split()

def fmt(v):
    return "N/A" if v is None else f"{v:.4f}"

def load_metrics(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

def row(version, m, eval_name):
    return [
        eval_name,
        version,
        fmt(m.get("event_f1")),
        fmt(m.get("triple_f1_strict")),
        fmt(m.get("triple_f1_relaxed")),
        fmt(m.get("entity_f1")),
        fmt(m.get("entity_f1_with_type")),
        fmt(m.get("relation_f1")),
        fmt(m.get("hallucination_rate")),
        fmt(m.get("tbox_consistency")),
    ]

headers = ["Gold", "Version", "EventF1", "TriS", "TriR", "EntF1", "EntF1+T", "RelF1", "Halluc", "TBox"]

def print_table(title, rows):
    if not rows:
        return
    widths = [max(len(h), max(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    print("")
    print(title)
    print(" ".join(h.ljust(widths[i]) for i, h in enumerate(headers)))
    print("-".join("-" * w for w in widths))
    for r in rows:
        print(" ".join(r[i].ljust(widths[i]) for i in range(len(headers))))

for variant in variants:
    rows = []
    for eval_file in eval_files:
        eval_name = Path(eval_file).stem
        base_dir = output_base / variant / f"eval_{eval_name}"
        metrics_path = base_dir / "metrics.json"
        metrics_no_tbox = base_dir / "metrics_no_tbox.json"

        data = load_metrics(metrics_path) or {}
        if "raw" in data:
            rows.append(row("raw", data["raw"], eval_name))
        else:
            rows.append(row("raw", data, eval_name))
        if "tbox_filtered" in data:
            rows.append(row("tbox_filtered", data["tbox_filtered"], eval_name))

        nt = load_metrics(metrics_no_tbox)
        if isinstance(nt, dict):
            rows.append(row("raw_only", nt, eval_name))

    print_table(f"[{variant}] 多 Gold 评测汇总", rows)
PY
}

# =============================================================================
# 主逻辑
# =============================================================================
RAN_VARIANTS=()

if [ "$EVAL_ONLY" = true ]; then
    echo "[INFO] 仅评测模式：跳过抽取"
fi

case "${EXPERIMENT}" in
    full)
        RAN_VARIANTS=("full")
        if [ "$EVAL_ONLY" != true ]; then
            run_full
        fi
        ;;
    wo_cot)
        RAN_VARIANTS=("wo_cot")
        if [ "$EVAL_ONLY" != true ]; then
            run_wo_cot
        fi
        ;;
    wo_graph)
        RAN_VARIANTS=("wo_graph")
        if [ "$EVAL_ONLY" != true ]; then
            run_wo_graph
        fi
        ;;
    wo_verify)
        RAN_VARIANTS=("wo_verify")
        if [ "$EVAL_ONLY" != true ]; then
            run_wo_verify
        fi
        ;;
    all)
        RAN_VARIANTS=("full" "wo_cot" "wo_graph" "wo_verify")
        if [ "$EVAL_ONLY" != true ]; then
            run_all
        fi
        ;;
    ablation)
        RAN_VARIANTS=("wo_cot" "wo_graph" "wo_verify")
        if [ "$EVAL_ONLY" != true ]; then
            run_ablation_only
        fi
        ;;
    *)
        echo "未知实验: ${EXPERIMENT}"
        echo "可选值: full, wo_cot, wo_graph, wo_verify, all, ablation"
        exit 1
        ;;
esac

if [ "$RUN_EVAL" = true ]; then
    for variant in "${RAN_VARIANTS[@]}"; do
        run_eval_variant "$variant"
    done
fi

if [ "$RUN_COMPARE" = true ]; then
    if [ "${#EVAL_TEST_FILES[@]}" -gt 1 ]; then
        echo "[INFO] 检测到多个 --eval-test-file，跳过 compare（输出已分目录）"
        print_multi_eval_summary
    else
        run_compare "${RAN_VARIANTS[@]}"
    fi
fi
