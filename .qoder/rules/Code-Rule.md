---
trigger: manual
---

## 代码规范

### 通用规范
1. **命名规范**
   - 变量名、函数名使用小写字母和下划线（snake_case）
   - 类名使用大驼峰命名法（PascalCase）
   - 常量使用全大写字母和下划线
   - 避免使用单字母变量名（除了循环计数器）

2. **代码格式**
   - 使用4个空格进行缩进，不使用Tab
   - 每行代码不超过120个字符
   - 函数之间空两行，类方法之间空一行
   - 运算符两边留空格
   - 逗号后面加空格

3. **注释规范**
   - 使用中文注释
   - 复杂逻辑必须添加注释说明
   - 函数和类使用文档字符串（docstring）
   - 注释应该说明"为什么"而不仅是"是什么"

4. **错误处理**
   - 使用具体的异常类型，避免使用裸except
   - 记录异常信息用于调试
   - 对于可预见的错误，提前进行检查和处理

### Python特定规范
1. 遵循PEP 8代码风格指南
2. 使用类型注解（Type Hints）提高代码可读性
3. 使用f-string进行字符串格式化
4. 合理使用列表推导式和生成器表达式
5. 避免可变默认参数

### 代码质量
1. 保持函数功能单一，遵循单一职责原则
2. 避免代码重复（DRY原则）
3. 保持适当的代码复杂度
4. 编写可测试的代码
5. 使用有意义的变量和函数名

### 代码复用原则（重要）
1. **优先复用/改进已有代码**：在新增功能时，首先检查是否存在可复用或可扩展的现有代码
2. **避免创建重复脚本**：不要创建功能相似的新脚本，而是在已有脚本上添加参数支持
3. **扩展而非重写**：当需要新功能时，优先通过添加参数、配置项或条件分支来扩展现有代码
4. **合并重复代码**：发现功能相似的多个文件时，应合并为一个并删除冗余文件
5. **检查清单**：
   - 新增功能前，先搜索是否有类似功能的现有实现
   - 新增脚本前，先检查 `scripts/` 目录下是否有可扩展的脚本
   - 新增工具函数前，先检查 `tools/` 和 `kg/` 目录下是否有可复用的函数

### 代码版本管理
1. **版本控制工具**
   - 使用 Git 进行版本控制
   - 提交信息必须使用中文
   - 遵循本文档第 8 节的 Git 工作流规范

2. **提交前检查**
   - 确保代码通过基本测试
   - 检查是否有敏感信息泄露（API Key、密码等）
   - 确认 .gitignore 正确配置

3. **分支命名规范**
   - 功能分支：`feature/功能描述`（如 `feature/p4-支持度聚合`）
   - 修复分支：`fix/问题描述`（如 `fix/json解析错误`）
   - 开发分支：`dev`
   - 主分支：`main`

4. **提交频率**
   - 小步提交，频繁推送
   - 每完成一个独立功能点即可提交
   - 避免一次提交包含过多不相关的修改

5. **详细规范参见**
   - 第 8 节：Git 工作流规范（提交信息格式、分支管理、代码审查）

## 运行和对话
### 运行须知
1. 运行该项目需要在conda环境下运行，在执行cli命令行程序前需要先激活conda环境： conda activate YangtzeLLM。如果不行，则使用 source activate YangtzeLLM
2. conda位于: /home/zjx/miniconda3/bin/python
3. Yangtze环境位于: /home/zjx/miniconda3/envs/YangtzeLLM

### 语言
1. 需要使用中文与我对话
2. 在git提交的时候生成的注释需要使用中文

## OCR/Paddle 服务踩坑总结（必读）

### 1. 环境与依赖（Torch/NCCL）
1. 不要在 `~/.bashrc` 里全局写死 `LD_LIBRARY_PATH=/usr/local/cuda/lib*`，容易让旧版 NCCL 抢先被加载，触发 `libtorch_cuda.so: undefined symbol: ncclGroupSimulateEnd` 之类错误（`import torch`/`paddleocr` 直接失败）。
2. 如必须设置 CUDA 路径，优先保证 conda 环境的 `$CONDA_PREFIX/lib` 在前，或临时 `env -u LD_LIBRARY_PATH ...` 运行命令。

### 2. PaddleOCR Serving 接口关键点（layout-parsing）
1. 服务端接口：`POST /layout-parsing`，请求/响应为 JSON，成功返回 `errorCode=0`。
2. `file` 字段支持两类输入：
   - **URL**（服务端可访问的 http/https 地址）
   - **Base64**（文件内容 base64 编码）
3. 不要把“本地文件路径字符串”直接填到 `file`（尤其包含中文/空格），服务端可能会按 base64 解码，导致 `500` 并出现：
   - `ValueError: string argument should contain only ASCII characters`
4. 如需本地文件解析，推荐使用 base64 上传；或先把文件放到一个服务端可访问的静态文件服务，再用 URL 方式。

### 3. 代理导致的“端口可用但连接被拒绝”
1. `urllib` 默认会读取环境变量 `http_proxy/https_proxy`，即使是 `localhost/127.0.0.1` 也可能被代理劫持，表现为 `Connection refused`（实际上在连代理端口）。
2. 处理方式：
   - 对本地服务请求默认禁用代理；或设置 `NO_PROXY=localhost,127.0.0.1,::1`；
   - 必须走代理访问远端服务时再显式启用代理。

### 4. `tools/paddle_ocr.py` 使用规范（批处理 + 缓存 + 并发）
1. 推荐命令（服务端模式）：
   - `python tools/paddle_ocr.py --runner server --workers 4 --skip-existing --retry-failed`
2. 关键参数说明：
   - `--api-url`：服务端地址（默认 `http://127.0.0.1:8123/layout-parsing`）
   - `--file-mode`：默认 `auto`（优先 base64，避免路径触发服务端 base64 解码错误）
   - `--proxy-mode`：默认 `auto`（本地服务禁用代理；远端按环境代理）
   - `--timeout-secs`：默认 `1800`，用于长文档处理
   - `--retry-failed`：重试缓存中失败项
3. 缓存文件：默认 `logs/ocr/paddleocr_cache.jsonl`（启动时会加载，支持断点续跑）。
4. 失败状态区分（写入缓存的 `status`）：
   - `failed_timeout`：请求超时（不重试）
   - `failed_parse`：解析错误（最多重试 2 次）
   - `failed_unavailable`：服务不可用/连接拒绝（默认不写缓存，避免污染；需要时加 `--cache-unavailable`）
   - `failed_other`：其他错误
5. 并发安全：
   - server 模式可多线程并发请求；
   - local 模式（PaddleOCRVL 本地推理）非线程安全，强制单线程。
6. 资源与稳定性：
   - base64 会把 PDF 读入内存并上传，大文件建议降低 `--workers`（如 1~2）。
   - 服务端模型提示 “batch size only supports 1” 属正常现象，但会影响吞吐。

### 5. 不保存图片/去除图片引用
1. OCR 输出 Markdown 中常包含 `imgs/...` 图片引用；如果不需要图片，应在写出前移除引用，并在处理结束后统一清理 `output_root/**/imgs/`（避免并发竞态）。

---

## 项目特定规范

### 1. LLM 调用规范

#### 1.1 统一调用入口
- **必须**通过 `kg/llm_core.py` 的 `LLMFactory` 或 `LLMClient` 调用 LLM
- **禁止**直接导入 `openai`/`zhipuai` 等 SDK 进行调用
- **原因**：统一管理 Key 轮换、限流处理、日志记录

```python
# ✅ 正确做法
from kg.llm_core import LLMFactory
llm = LLMFactory.create_from_config(cfg)
response = llm.chat_messages(messages, json_mode=True)

# ❌ 错误做法
import openai
client = openai.OpenAI(api_key="...")
response = client.chat.completions.create(...)
```

#### 1.2 JSON 输出处理
- 使用 `kg/cq_pipeline.py` 的 `LLMJsonClient` 处理 JSON 输出
- 自动处理 Markdown fence 剥离和格式兜底
- 使用 `_parse_tbox()` 等辅助函数进行结构化解析

```python
# ✅ 推荐做法
from kg.cq_pipeline import LLMJsonClient
client = LLMJsonClient(llm)
result = client.call(system_prompt, user_prompt)  # 自动解析 JSON
```

#### 1.3 温度参数设置
- **生成 CQ/TBox**：temperature = 0.1（保证稳定性）
- **创意扩展**：temperature = 0.3-0.5（适度随机性）
- **对话问答**：temperature = 0.7（更自然的回复）

#### 1.4 重试和错误处理
- 使用配置文件中的 `max_retries` 和 `timeout` 参数
- 捕获 `RateLimitError` (429) 让系统自动切换 Key
- 记录失败请求到日志，包含 prompt 摘要和错误信息

```python
try:
    response = llm.chat_messages(messages)
except Exception as e:
    logger.error(f"LLM调用失败: {e}, prompt前100字: {user_prompt[:100]}")
    raise
```

### 2. 数据文件规范

#### 2.1 文件命名约定
- **TBox 文件**：`p{阶段}_tbox_{描述}_{时间戳}.json`
  - 示例：`p4_tbox_augmented_s2_allow1_20251223_154500.json`
- **CQ 文件**：`p1_cqs_{描述}.json`
- **抽取结果**：`p5_{描述}.json` 或 `p5_{描述}.jsonl`
- **评估报告**：`{指标名}_metrics_{时间戳}.{json|csv|md}`

#### 2.2 JSON 格式规范
- 使用 4 空格缩进（`json.dumps(..., indent=4)`）
- 包含元数据字段：`_version`、`_created_at`、`_source`
- 大文件使用 JSONL 格式（每行一个 JSON 对象）

```python
# ✅ 标准输出格式
output = {
    "_version": "2.0",
    "_created_at": datetime.now().isoformat(),
    "_source": "P4 batch processing",
    "classes": [...],
    "relations": [...],
    "attributes": [...]
}
with open(path, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)
```

#### 2.3 批处理稳定性（断点与流式写出）
1. **长批任务必须流式写文件**：逐条写入 JSONL，并在每条写入后 `flush()`，避免中断丢结果。
2. **日志必须覆盖进度**：至少输出当前条目索引与总数，必要时记录关键统计（如过滤率）。
3. **断点续跑需可复用输出**：支持 `--skip-existing` 或基于 `doc_id` 跳过已完成样本。

#### 2.4 JSONL 规范
- 每行必须是完整的 JSON 对象
- 不要在行尾添加逗号
- 适用于大规模批处理结果（P4 suggestions、P5 batch results）

```python
# ✅ JSONL 写入
with open(path, "a", encoding="utf-8") as f:
    f.write(json.dumps(item, ensure_ascii=False) + "\n")
```

### 3. 配置文件规范

#### 3.1 配置优先级
```
CLI 参数 > cfg.yaml > 代码默认值
```

#### 3.2 读取配置的标准模式
```python
from pathlib import Path
import yaml

def load_config(cfg_path: str = "configs/cfg.yaml") -> dict:
    """加载配置文件，带默认值兜底"""
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg

# 使用 pick 函数处理优先级
def pick(*vals, default=None):
    """从左到右选择第一个非空值"""
    for v in vals:
        if v not in (None, ""):
            return v
    return default

# 示例
provider = pick(args.provider, cfg["llm"]["provider"], "openai")
```

#### 3.3 敏感信息管理
- API Key **必须**放在 `.env` 文件中，**禁止**硬编码
- `.env` 文件**必须**加入 `.gitignore`
- 使用 `python-dotenv` 加载环境变量

```python
# ✅ 正确做法
from dotenv import load_dotenv
import os
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

# ❌ 错误做法
api_key = "sk-xxxxx"  # 禁止硬编码
```

### 4. 日志规范

#### 4.1 日志级别使用
- `DEBUG`：详细的调试信息（中间变量、循环迭代）
- `INFO`：关键流程节点（阶段开始/结束、文件保存）
- `WARNING`：可恢复的异常（跳过某个文档、使用默认值）
- `ERROR`：严重错误（文件读取失败、LLM 调用失败）

```python
import logging
logger = logging.getLogger(__name__)

# 示例
logger.info(f"开始 P4 批处理，共 {len(docs)} 个文档")
logger.warning(f"文档 {doc_id} 缺少 text 字段，跳过")
logger.error(f"无法读取文件 {path}: {e}")
```

#### 4.2 日志文件组织
- 按模块划分：`logs/kg_tbox/`, `logs/corpus_filter/`, `logs/ocr/`
- 使用日期后缀：`p4_batch_20251223.log`
- 配置日志轮转（避免单文件过大）

```python
# 使用 tools/logging_utils.py 初始化
from tools.logging_utils import init_logging
init_logging(cfg["logging"])
```

#### 4.3 关键操作必须记录
- LLM 调用（记录 prompt 长度、响应时间、tokens 使用）
- 文件读写（记录路径、大小、行数）
- 批处理进度（每处理 N 个记录一次）
- 异常情况（记录完整堆栈）

### 5. 错误处理最佳实践

#### 5.1 异常类型
```python
# ✅ 使用具体异常
try:
    with open(path, "r") as f:
        data = json.load(f)
except FileNotFoundError:
    logger.error(f"文件不存在: {path}")
    raise
except json.JSONDecodeError as e:
    logger.error(f"JSON 解析失败: {path}, 错误: {e}")
    raise

# ❌ 避免裸 except
try:
    ...
except:  # 不推荐
    pass
```

#### 5.2 错误恢复策略
- **可恢复错误**：记录日志 + 跳过 + 继续处理
- **严重错误**：记录日志 + 清理资源 + 抛出异常

```python
# 批处理中的错误处理示例
for doc_id, doc in docs:
    try:
        result = process_doc(doc)
        results.append(result)
    except Exception as e:
        logger.warning(f"处理文档 {doc_id} 失败: {e}，跳过")
        continue  # 继续处理其他文档
```

#### 5.3 断点续跑实现模式
```python
# 标准模式
processed_ids = set()
if output_file.exists() and not args.overwrite:
    # 加载已处理的 ID
    with open(output_file) as f:
        for line in f:
            item = json.loads(line)
            processed_ids.add(item["id"])
    logger.info(f"已处理 {len(processed_ids)} 个，将跳过")

# 过滤未处理的
to_process = [doc for doc in docs if doc["id"] not in processed_ids]
```

### 6. 性能优化建议

#### 6.1 批处理优化
- 使用生成器避免一次性加载大文件
- 并发调用 LLM（注意线程安全）
- 缓存中间结果（P4 suggestions）

```python
# ✅ 使用生成器
def read_jsonl(path):
    with open(path) as f:
        for line in f:
            yield json.loads(line)

# ✅ 并发调用（注意 API 限流）
from concurrent.futures import ThreadPoolExecutor
with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(process, doc) for doc in docs]
    results = [f.result() for f in futures]
```

#### 6.2 内存优化
- 大规模数据使用 JSONL 逐行处理
- 及时释放不再使用的对象
- 避免在循环中累积大列表

```python
# ✅ 逐行写入，避免内存累积
with open(output_path, "w") as f:
    for item in process_large_dataset():
        f.write(json.dumps(item, ensure_ascii=False) + "\n")
```

### 7. 测试规范

#### 7.1 测试文件组织
- 测试文件放在 `tests/` 目录
- 命名规则：`test_{模块名}.py`
- 使用 pytest 框架

```python
# tests/test_llm_core.py
import pytest
from kg.llm_core import LLMFactory

def test_key_rotation():
    """测试多 Key 轮换机制"""
    # 测试代码
    pass
```

#### 7.2 必须测试的功能
- LLM Key 轮换逻辑
- JSON 解析兜底机制
- 断点续跑逻辑
- 配置文件加载
- 数据结构转换（TBox/Event）

### 8. Git 工作流规范

#### 8.1 提交信息规范
```
<类型>: <简短描述>（中文）

<详细说明>（可选）

类型：
- feat: 新功能
- fix: 修复 bug
- docs: 文档更新
- refactor: 代码重构
- test: 测试相关
- chore: 构建/工具相关
```

示例：
```
feat: 实现 P4 支持度聚合机制

- 添加 min_support 参数过滤低频建议
- 记录 _support_sources 便于溯源
- 更新配置文件默认值为 2
```

#### 8.2 分支管理
- `main`: 稳定版本
- `dev`: 开发分支
- `feature/xxx`: 功能分支
- `fix/xxx`: 修复分支

#### 8.3 代码审查检查清单
- [ ] 遵循代码规范（snake_case、4空格缩进）
- [ ] 添加必要的注释和文档字符串
- [ ] 使用中文注释和 Git 提交信息
- [ ] 敏感信息不在代码中硬编码
- [ ] 添加错误处理和日志记录
- [ ] 更新相关文档（README/PROJECT_OVERVIEW）

### 9. 文档规范

#### 9.1 代码文档字符串
```python
def extract_events(
    self, 
    paragraph: str, 
    schema: TBoxSchema, 
    save_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    从段落中抽取灾害事件和三元组。
    
    Args:
        paragraph: 待抽取的文本段落
        schema: TBox 模式（约束抽取范围）
        save_path: 可选的结果保存路径
        
    Returns:
        包含 events 和 triples 的字典
        
    Raises:
        ValueError: 当 paragraph 为空时
        
    示例:
        >>> result = client.extract_events(text, schema)
        >>> print(len(result["events"]))
    """
    pass
```

#### 9.2 模块级文档
每个 Python 文件顶部添加模块说明：
```python
"""
TBox 指标计算模块。

实现 OntoQA 框架的核心指标：
- RR (Relationship Richness): 关系丰富度
- IR (Inheritance Richness): 继承丰富度  
- AR (Attribute Richness): 属性丰富度

用法:
    from tools.tbox_metrics import compute_tbox_metrics
    metrics = compute_tbox_metrics(tbox)
"""
```

### 10. 安全注意事项

#### 10.1 输入验证
```python
# ✅ 验证路径安全性
def safe_load_json(path: str) -> dict:
    path = Path(path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"文件不存在: {path}")
    if path.suffix != ".json":
        raise ValueError("仅支持 .json 文件")
    with open(path) as f:
        return json.load(f)
```

#### 10.2 避免命令注入
```python
# ❌ 危险做法
os.system(f"rm {user_input}")  # 可能导致命令注入

# ✅ 安全做法
from pathlib import Path
Path(user_input).unlink(missing_ok=True)
```

#### 10.3 大文件处理
- 设置文件大小限制（避免 OOM）
- 使用流式处理大文件
- 添加超时机制

```python
# ✅ 检查文件大小
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
if Path(path).stat().st_size > MAX_FILE_SIZE:
    raise ValueError(f"文件过大: {path}")
```

### 11. 数据处理与评测流程规范（重要）

#### 11.1 数据源一致性检查

**教训**：在评测实验中，Pred 和 Gold 使用了不同的文本源（截断 vs 完整），导致指标严重偏低。

**规范**：
1. **始终验证数据完整性**：处理前检查关键字段是否截断或缺失
2. **建立数据映射机制**：当存在多个数据文件时，添加 `--text-source` 类参数支持数据映射
3. **文档化数据流**：记录每个处理阶段的输入/输出文件及其字段含义

```python
# ✅ 正确做法：添加数据源映射支持
parser.add_argument("--text-source", type=str, default=None,
                    help="完整文本来源文件，用 id 映射获取完整数据")

# 处理时优先使用完整数据
if text_lookup and doc_id in text_lookup:
    text = text_lookup[doc_id]  # 优先使用映射的完整文本
else:
    text = sample.get("source_text", "")  # 备选方案
```

#### 11.2 评测数据对齐原则

**教训**：Gold 使用独立 Schema，Pred 使用项目 TBox，导致关系类型完全不匹配，Triple F1 极低（~4%）。

**规范**：
1. **Schema 配对使用**：Gold 和 Pred 必须使用相同的 TBox 版本
2. **版本命名清晰**：文件名中包含版本标识（如 `gold_s2.jsonl` 对应 `tbox_s2_optimized.json`）
3. **配对检查清单**：

| 配对项 | 必须一致 | 检查方法 |
|--------|---------|----------|
| TBox 版本 | Gold 和 Pred 使用相同 TBox | 对比 `--tbox` 参数 |
| 文本来源 | 都使用完整文本或都使用截断文本 | 对比 `--text-source` 参数 |
| doc_id 集合 | Gold 覆盖 Pred 的所有 doc_id | 脚本检查交集 |

```bash
# ✅ 正确的评测命令（确保配对）
python tools/abox_metrics.py \
    --gold data/p5_eval_pool/gold_s2_tbox.jsonl \    # S2 版本 Gold
    --pred outputs/predictions_s2.jsonl \            # S2 版本 Pred
    --tbox outputs/cq_pipeline/final/tbox_s2_optimized.json  # S2 TBox
```

#### 11.3 数据截断风险识别

**场景识别**：以下情况可能存在数据截断：
- `source_text` 字段长度明显短于 `text` 字段
- 字段值末尾带有 `...` 或 `[truncated]` 标记
- 文件名包含 `final`、`filtered`、`processed` 等加工标识

**验证脚本示例**：
```python
# 检查文本截断
import json
from pathlib import Path

def check_truncation(processed_file, source_file):
    """检查处理后文件是否存在截断"""
    source_lookup = {}
    with open(source_file) as f:
        for line in f:
            d = json.loads(line)
            source_lookup[d.get("id", d.get("doc_id"))] = len(d.get("text", ""))

    truncated = 0
    with open(processed_file) as f:
        for line in f:
            d = json.loads(line)
            doc_id = d.get("doc_id", d.get("id"))
            processed_len = len(d.get("source_text", d.get("text", "")))
            source_len = source_lookup.get(doc_id, 0)
            if processed_len < source_len * 0.8:  # 80% 阈值
                truncated += 1
                print(f"⚠️ {doc_id}: {processed_len} vs {source_len} chars")

    print(f"共 {truncated} 条可能被截断")
```

#### 11.4 评测脚本参数设计规范

为避免数据不一致问题，评测相关脚本应遵循以下参数设计：

```python
# 标准参数集
parser.add_argument("--input", required=True, help="输入文件（doc_id 列表来源）")
parser.add_argument("--text-source", help="完整文本来源文件（可选，优先于 input 中的文本）")
parser.add_argument("--tbox", required=True, help="TBox 约束文件（明确版本）")
parser.add_argument("--output", required=True, help="输出文件（文件名应包含版本标识）")
```

#### 11.5 踩坑检查清单

评测实验前，完成以下检查：

- [ ] **文本完整性**：确认使用完整文本而非截断文本
- [ ] **Schema 一致性**：确认 Gold 和 Pred 使用相同 TBox 版本
- [ ] **字段映射正确**：确认 doc_id 映射关系正确（`test.doc_id` → `source.id`）
- [ ] **版本标识清晰**：文件名包含版本信息（s2/s3）
- [ ] **路径更新**：使用最新的优化版文件路径（如 `tbox_s2_optimized.json`）

---

### 12. 常见错误和调试技巧

#### 12.1 LLM 调用失败
**症状**：429 限流、连接超时、JSON 解析失败

**排查步骤**：
1. 检查 API Key 是否有效（`echo $OPENAI_API_KEYS`）
2. 查看日志文件中的完整错误信息
3. 降低并发数或增加重试间隔
4. 检查 prompt 长度是否超过模型限制

```bash
# 查看最近的错误日志
grep ERROR logs/kg_tbox/*.log | tail -20
```

#### 12.2 JSON 解析失败
**症状**：`json.JSONDecodeError`

**排查步骤**：
1. 检查 LLM 返回的原始文本（记录到日志）
2. 查看是否有 Markdown fence 未剥离
3. 检查是否有非法字符（特殊引号、控制字符）

```python
# 调试技巧：保存原始响应
logger.debug(f"LLM 原始响应: {raw_response[:500]}")
with open("debug_response.txt", "w") as f:
    f.write(raw_response)
```

#### 12.3 断点续跑不生效
**症状**：重复处理已完成的文档

**排查步骤**：
1. 检查输出文件路径是否正确
2. 确认 ID 提取逻辑与写入时一致
3. 检查是否使用了 `--overwrite` 参数

```python
# 调试技巧
logger.info(f"已处理 ID 数量: {len(processed_ids)}")
logger.info(f"待处理数量: {len(to_process)}")
logger.debug(f"已处理 ID 样例: {list(processed_ids)[:5]}")
```

#### 12.4 内存溢出
**症状**：`MemoryError` 或进程被 killed

**排查步骤**：
1. 检查是否一次性加载了大文件
2. 使用 JSONL 逐行处理替代 JSON 整体加载
3. 降低并发数
4. 增加交换空间或使用更大内存机器

```python
# 监控内存使用
import psutil
process = psutil.Process()
logger.info(f"内存使用: {process.memory_info().rss / 1024 / 1024:.2f} MB")
```

---

## 快速参考

### 命令速查

```bash
# 激活环境
conda activate YangtzeLLM

source activate YangtzeLLM  # 备用命令

# 运行 P1-P5 完整流程
python scripts/run_cq_pipeline.py --cfg configs/cfg.yaml

# 运行 P4 批处理（断点续跑）
python scripts/run_p4_batch.py --base-tbox <path> --corpus-jsonl <path>

# 查看日志
tail -f logs/kg_tbox/p4_batch_*.log

# 检查配置
python scripts/verify_config.py

# 运行测试
pytest tests/ -v
```

### 环境变量速查

```bash
# 必需的环境变量
export OPENAI_API_KEYS=key1,key2,key3  # 多 Key 逗号分隔
export ZHIPU_API_KEY=your_key          # 智谱 API
export GOOGLE_API_KEY=your_key         # Gemini API

# 可选的环境变量
export NO_PROXY=localhost,127.0.0.1,::1  # 禁用本地代理
export HF_ENDPOINT=https://hf-mirror.com  # HuggingFace 镜像
export HF_HOME=/path/to/cache             # 模型缓存目录
```

### 文件路径速查

```yaml
配置文件: configs/cfg.yaml
环境变量: .env
日志目录: logs/
输出目录: outputs/cq_pipeline/
语料目录: data/corpus_for_kg/
模型缓存: /media/data2/YangtzeDestoryLLM/models_cache/
```

---
