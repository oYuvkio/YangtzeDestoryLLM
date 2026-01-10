

---

# 项目优化需求文档：CQ-Enhanced 知识图谱构建与评测

## 1. 项目背景
当前项目是一个基于 CQ（Competency Questions）驱动的长江流域水旱灾害知识图谱构建流程。
- **当前状态**：已完成 P1-P6 流程，包含 CoT 抽取和原文回溯校验。
- **存在问题**：评测指标不够全面；模型容易混淆“通用知识”与“具体事件”；Schema 注入方式对中文 LLM 不够友好；数值和实体归一化逻辑过于简单。

## 2. 任务清单

请按以下四个模块对代码进行修改和增强：

---

### 模块一：评测指标增强 (Evaluation Metrics)

**目标**：在 `tools/abox_metrics.py` 中增加“置信度校准误差”和“证据质量”两个新指标。

#### 1.1 新增：置信度校准误差 (ECE)
**逻辑**：计算模型输出的 `confidence` (high/medium/low) 与实际准确率的偏差。
**映射规则**：`high`=0.9, `medium`=0.7, `low`=0.5。
**参考代码实现**：
请在 `tools/abox_metrics.py` 中添加 `compute_ece` 函数，并在 `compute_full_metrics` 中调用。

```python
import numpy as np

def compute_ece(predictions, gold_triples, n_bins=5):
    """
    计算置信度校准误差 (Expected Calibration Error)
    需在主评测循环中标记每个预测三元组是否正确 (is_correct)
    """
    conf_map = {"high": 0.9, "medium": 0.7, "low": 0.5}
    data = []
    
    # 注意：你需要修改 compute_triple_f1 的逻辑，使其返回每个预测三元组的正确性标记
    for pred in predictions:
        conf_score = conf_map.get(pred.get("confidence", "low").lower(), 0.5)
        is_correct = pred.get("_is_correct_flag", False) # 需在匹配逻辑中注入此标记
        data.append((conf_score, is_correct))
    
    if not data: return 0.0
    
    data = np.array(data)
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    total = len(data)
    
    for i in range(n_bins):
        mask = (data[:, 0] > bin_boundaries[i]) & (data[:, 0] <= bin_boundaries[i+1])
        bin_samples = data[mask]
        if len(bin_samples) > 0:
            avg_conf = np.mean(bin_samples[:, 0])
            avg_acc = np.mean(bin_samples[:, 1])
            ece += np.abs(avg_acc - avg_conf) * (len(bin_samples) / total)
    return ece
```

#### 1.2 新增：证据重合度 (Evidence Quality)
**逻辑**：计算抽取出的 `evidence` 字段与原文 `source_text` 的 Rouge-L 分数，判断证据是否由模型臆造。
**实现**：引入 `rouge_score` 库或手写简单的 LCS (Longest Common Subsequence) 算法。

---

### 模块二：Prompt 与 Schema 注入优化 (Extraction Logic)

**目标**：解决模型抽取“通用知识”的问题，并降低中英混合 Schema 对模型的干扰。

#### 2.1 修改 Prompt：区分实例与通用知识
**文件**：`kg/prompts.py`
**修改点**：在 `P5_COT_EXTRACTION_PROMPT` 中显式增加约束，禁止抽取教科书式的定义。

```python
# 在 Prompt 的【核心约束】部分增加：
"""
【⚠️ 核心原则：区分“通用知识”与“具体事件”】
1. **仅抽取具体实例**：
   - ❌ 拒绝通用描述：不要抽取 "洪水通常由暴雨引起" 这样的规律性描述。
   - ✅ 仅抽取事实：只抽取 "1998年长江洪水由持续暴雨引起" 这样的具体记录。
   - 如果文中是在讨论理论、规律或定义，而没有提及具体的时间/地点/事件实例，请返回空列表。

2. **实体必须是实例**：
   - Subject 必须是具体的事件实例（如"98年洪水"）或具体的设施/机构。
   - 不要将 "洪水"（泛指概念）作为 Subject。
"""
```

#### 2.2 优化 Schema 注入格式
**文件**：`kg/cq_pipeline.py`
**修改点**：修改 `format_schema_for_prompt` 函数，将 JSON 转为 Markdown 文本，且**中文名在前**。

```python
def format_schema_for_prompt(schema_json):
    lines = ["【实体类型定义】"]
    for cls in schema_json['classes']:
        # 格式：- **中文名** (ID: EnglishName): 定义
        lines.append(f"- **{cls['cn_name']}** (ID: {cls['name']}): {cls['definition']}")
    
    lines.append("\n【关系类型定义】")
    for rel in schema_json['relations']:
        lines.append(f"- **{rel['cn_name']}** (ID: {rel['name']}): {rel['domain']} -> {rel['range']}")
    
    return "\n".join(lines)
```

---

### 模块三：评测归一化逻辑增强 (Normalization)

**目标**：解决 `NumericValue`（数值）和带括号实体的匹配失败问题。

#### 3.1 增强文本归一化
**文件**：`tools/abox_metrics.py`
**修改点**：`_normalize_text` 函数需处理中文括号。

```python
def _normalize_text(text: str) -> str:
    text = str(text).strip()
    # 去除括号及内容（针对 "长江(Yangtze)" 这种情况）
    text = re.sub(r"（[^）]*）|\([^\)]*\)", "", text)
    # 去除标点和空格
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。、“”‘’：；（）【】《》/\\-]", "", text)
    return text.lower()
```

#### 3.2 新增数值归一化
**文件**：`tools/abox_metrics.py`
**修改点**：新增 `_normalize_value` 函数，并在 `_entities_match_relaxed` 中调用。

```python
def _normalize_value(text: str, entity_type: str = "") -> str:
    """提取纯数字进行比较，解决 '45.2米' vs '45.2m' 的问题"""
    # 如果实体类型包含 Value 或文本包含数字
    if "Value" in str(entity_type) or re.search(r'\d', text):
        # 提取浮点数
        nums = re.findall(r"[-+]?\d*\.\d+|\d+", text)
        if nums:
            return nums[0] # 返回第一个数字字符串
    return _normalize_text(text)

# 在 _entities_match_relaxed 中：
# pred_val = _normalize_value(pred_entity, pred_type)
# gold_val = _normalize_value(gold_entity, gold_type)
# if pred_val == gold_val: return True
```

---

### 模块四：三元组形式确认

**说明**：
- 本项目采用 **Standard Triples (RDF)** + **Event Frames** 混合模式。
- 虽然 Schema 定义了 `attributes`（如 `peak_water_level`），但目前抽取结果主要使用 `has_value` 连接 `NumericValue`。
- **要求**：保持当前三元组结构不变，但必须通过上述 **模块三** 中的数值归一化来确保 `has_value` 关系的评测准确性。

---

### 模块五：用统一的Prompt重新抽取Gold和Pred

原因：
┌─────────────────────────────────────────────────────────────────────────┐
│                     Gold vs Pred 流程差异对比                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  差异维度            Gold                    Pred           ⚠️问题级别   │
│  ───────────────────────────────────────────────────────────────────── │
│  TBox 格式           表格形式                JSON格式         🟡中       │
│  幻觉过滤阈值        0.7 (宽松)              0.85 (严格)      🔴高       │
│  strict_mode         False                  True            🔴高       │
│  模型能力            GPT-4o (强)            Qwen3-8B (弱)   🟡中       │
│  System Prompt       专用 COT Prompt        通用 Prompt      🟡中       │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
### 5.1 统一 Prompt（最关键）
使用一个统一的 Prompt 文件，Gold 和 Pred 都使用：

### 5.2 统一后处理流程

```python
# kg/extraction_pipeline.py

class UnifiedExtractionPipeline:
    """统一的抽取后处理流程"""
    
    def __init__(
        self,
        tbox: dict,
        fuzzy_threshold: float = 0.8,  # 统一阈值
        strict_mode: bool = False,      # 统一严格模式
    ):
        self.tbox = tbox
        self.halluc_filter = HallucinationFilter(
            strict_mode=strict_mode,
            fuzzy_threshold=fuzzy_threshold,
        )
        self.direction_fixer = DirectionNormalizer(tbox)
        self.entity_normalizer = SimpleEntityNormalizer()
    
    def process(self, raw_result: dict, source_text: str) -> dict:
        """统一后处理流程"""
        
        # Step 1: 解析 CoT 响应
        if isinstance(raw_result, str):
            raw_result = parse_cot_response(raw_result)
        
        # Step 2: 幻觉过滤
        verified = self.halluc_filter.verify(raw_result, source_text)
        
        # Step 3: 方向修正
        fixed_triples = self.direction_fixer.fix_directions(verified.valid_triples)
        
        # Step 4: 实体归一化
        normalized_triples = self.entity_normalizer.normalize_triples(fixed_triples)
        
        # Step 5: TBox 约束验证
        valid_triples = self._validate_tbox(normalized_triples)
        
        return {
            "events": verified.valid_events,
            "triples": valid_triples,
            "entities": raw_result.get("entities", []),
            "filtered_triples": verified.filtered_triples,
            "stats": {
                "original": len(raw_result.get("triples", [])),
                "after_halluc_filter": len(verified.valid_triples),
                "after_direction_fix": len(fixed_triples),
                "final": len(valid_triples),
            }
        }
```

2.2 示例数据中的具体问题
看你给的示例：

Pred 输出（10个三元组）:

JSON

{"subject": "洪水", "predicate": "has_hazard_factor", "object": "暖湿的气候"}
{"subject": "洪水", "predicate": "influenced_by_climate", "object": "暖湿的气候"}
{"subject": "洪水频发期", "predicate": "affects_region", "object": "长江三角洲地区"}
...
Gold 输出（3个有效三元组）:

JSON

{"subject": "长江三角洲地区", "predicate": "affects_region", "object": "长江流域"}  ← ⚠️ 方向错误！
{"subject": "气候变化", "predicate": "influenced_by_climate", "object": "洪水"}     ← ⚠️ 方向错误！
{"subject": "人为因素", "predicate": "has_hazard_factor", "object": "洪水"}         ← ⚠️ 方向错误！
关键问题发现：

问题1：Gold 本身的方向就是错的！
查看你的 Schema 定义：

JSON

{
  "name": "has_hazard_factor",
  "domain": "DisasterEvent",    // 主语应该是灾害事件
  "range": "HazardFactor"       // 宾语应该是致灾因子
}
Gold 标注：(人为因素, has_hazard_factor, 洪水)

主语 人为因素 → 应该是 HazardFactor
宾语 洪水 → 应该是 DisasterEvent
这是完全反的！ 正确应该是：(洪水, has_hazard_factor, 人为因素)

问题2：事件抽取差异巨大
Pred: 2个事件
Gold: 0个事件
这说明 Gold 和 Pred 对"什么是事件"的理解完全不一致。

问题3：幻觉过滤阈值不一致导致三元组数量差异
Pred (阈值0.85 更严格): 10个三元组
Gold (阈值0.7 更宽松): 5个三元组 (3有效+2被过滤)
但结果反了？ 这说明模型本身的差异才是主导因素。

### 高优先级（立即修复）

1. **统一 Prompt**：Gold 和 Pred 使用完全相同的 Prompt 模板
2. **统一后处理阈值**：`fuzzy_threshold=0.8`, `strict_mode=False`
3. **增加方向说明**：在 Prompt 中明确关系方向和示例



请根据以上文档，对项目代码进行相应的修改和补充。

