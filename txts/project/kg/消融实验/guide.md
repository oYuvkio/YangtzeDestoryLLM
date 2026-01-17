根据上下文，我需要先读取相关文件，然后给出 `--no-graph` 参数的实现计划。

我需要继续读取 `kg/cq_pipeline.py` 的剩余部分，特别是 `extract_events_with_verification` 方法：

继续读取 `extract_events_with_verification` 方法的剩余部分：

现在我已经完全理解了代码结构。让我给出 `--no-graph` 参数的实现计划：

---

## `--no-graph` 参数实现计划

### 背景分析

通过代码审查，我发现：
- `--no-cot` 和 `--no-verify` 已在 `run_extraction_on_test.py` 中实现
- 图结构检测逻辑在 `extract_events()` 和 `extract_events_with_verification()` 中，当 `use_cot=True` 时会调用 `get_graph_structure_for_text()` 进行文本类型检测

### 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `scripts/p5/run_extraction_on_test.py` | 添加 `--no-graph` 参数 |
| `kg/cq_pipeline.py` | 在 `extract_events()` 和 `extract_events_with_verification()` 中添加 `use_graph` 参数 |

### 详细修改方案

#### 1. `scripts/p5/run_extraction_on_test.py`

```python
# 在 --no-verify 后添加（约 147 行）
parser.add_argument("--no-graph", action="store_true",
                    help="禁用图结构检测（用于消融实验，默认开启图结构检测）")

# 在 use_verify 定义后添加（约 170 行）
use_graph = not args.no_graph

# 修改 pipeline 调用（约 310 行和 318 行），传入 use_graph 参数
res = pipeline.extract_events_with_verification(..., use_graph=use_graph)
res = pipeline.extract_events(..., use_graph=use_graph)

# 修改日志输出和元数据，添加 use_graph 字段
```

#### 2. `kg/cq_pipeline.py`

**`extract_events()` 方法（约 540 行）：**
```python
def extract_events(
    self,
    paragraph: str,
    schema: TBoxSchema,
    save_path: Optional[Path] = None,
    favor_existing_classes: bool = True,
    use_cot: bool = True,
    use_graph: bool = True,  # 新增参数
) -> Dict[str, Any]:
```

修改图结构检测逻辑：
```python
if use_cot:
    if use_graph:
        graph_structure, type_id, confidence = get_graph_structure_for_text(paragraph)
        if confidence < GRAPH_TYPE_CONFIDENCE_THRESHOLD:
            graph_structure = get_graph_structure("general_disaster")
    else:
        # 禁用图结构检测时，直接使用通用结构
        graph_structure = get_graph_structure("general_disaster")
        type_id = "general_disaster"
    # ... 后续逻辑不变
```

**`extract_events_with_verification()` 方法（约 930 行）：**
```python
def extract_events_with_verification(
    self,
    paragraph: str,
    schema: TBoxSchema,
    ...,
    use_cot: bool = True,
    use_graph: bool = True,  # 新增参数
    ...,
) -> Dict[str, Any]:
```

同样修改图结构检测逻辑（约 980 行）。

### 消融实验效果

| 参数组合 | 效果 |
|----------|------|
| 默认（无参数） | 完整 Graph-CoT：文本类型检测 + 图结构驱动 CoT |
| `--no-graph` | 禁用文本类型检测，统一使用 `general_disaster` 通用结构 |
| `--no-cot` | 禁用 CoT，使用普通 P5_EXTRACTION_PROMPT |
| `--no-graph --no-cot` | 完全禁用图结构和 CoT（最简基线） |

---

**请确认此计划是否可以开始实施？**


