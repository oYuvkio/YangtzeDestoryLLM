
# 问题一

提取出来了：
{"entities": [{"name": "无为", "type": "GeographicRegion"}, {"name": "水灾", "type": "DisasterEvent"}, {"name": "旱灾", "type": "DroughtEvent"}, {"name": "水旱灾害", "type": "DisasterEvent"}, {"name": "江坝", "type": "Levee"}, {"name": "五里碑大堤", "type": "Levee"}, {"name": "临江", "type": "GeographicRegion"}, {"name": "三坝", "type": "Levee"}, {"name": "乾隆五十年(1785年)奇旱", "type": "DroughtEvent"}, {"name": "宣统三年(1911年)五六月间大雨", "type": "DisasterEvent"}, {"name": "乾隆二十九年(1764年)", "type": "DisasterEvent"}, {"name": "江洪", "type": "HazardFactor"}, {"name": "江潮", "type": "HazardFactor"}, {"name": "大饥", "type": "DisasterImpact"}, {"name": "疫", "type": "DisasterImpact"}, {"name": "溺死", "type": "CasualtyImpact"}, {"name": "漂荡庐舍", "type": "InfrastructureDamage"}, {"name": "圩田", "type": "GeographicRegion"}, {"name": "山田", "type": "AgriculturalImpact"}, {"name": "坝堤", "type": "Levee"}], "triples": [{"subject": "水灾", "predicate": "affects_region", "object": "无为", "evidence": "清代无为有水、旱、震、疫、风、雪、雹、虫等自然灾害共158次。其中水灾达60次", "confidence": "high"}, {"subject": "旱灾", "predicate": "affects_region", "object": "无为", "evidence": "清代无为有水、旱、震、疫、风、雪、雹、虫等自然灾害共158次...旱灾33次", "confidence": "high"}, {"subject": "水旱灾害", "predicate": "affects_region", "object": "无为", "evidence": "清代无为水旱灾害为患之巨、发生之频繁", "confidence": "high"}, {"subject": "江坝", "predicate": "protects_region", "object": "无为", "evidence": "从清代开始才有了无为江坝口决堤的记载", "confidence": "high"}, {"subject": "五里碑大堤", "predicate": "protects_region", "object": "无为", "evidence": "江潮暴涨,冲溃五里碑大堤,无为州境上下九连各圩一片汪洋", "confidence": "high"}, {"subject": "乾隆五十年(1785年)奇旱", "predicate": "affects_region", "object": "无为", "evidence": "乾隆五十年(1785年)奇旱,自去冬至是年终岁无雨", "confidence": "high"}, {"subject": "乾隆五十年(1785年)奇旱", "predicate": "causes_impact", "object": "山田", "evidence": "山田籽粒无收,圩之滨河者收三十之一", "confidence": "high"}, {"subject": "乾隆五十年(1785年)奇旱", "predicate": "causes_impact", "object": "大饥", "evidence": "五十一年(1786年)春仍旱,大饥而疫死者弥望", "confidence": "high"}, {"subject": "乾隆五十年(1785年)奇旱", "predicate": "causes_impact", "object": "疫", "evidence": "五十一年(1786年)春仍旱,大饥而疫死者弥望", "confidence": "high"}, {"subject": "宣统三年(1911年)五六月间大雨", "predicate": "has_hazard_factor", "object": "江潮", "evidence": "宣统三年(1911年)五六月间大雨时行,江潮暴涨", "confidence": "high"}, {"subject": "宣统三年(1911年)五六月间大雨", "predicate": "causes_impact", "object": "漂荡庐舍", "evidence": "无为州境上下九连各圩一片汪洋,高及树巅,村落庐舍全归巨浸", "confidence": "high"}, {"subject": "乾隆二十九年(1764年)", "predicate": "affects_region", "object": "临江", "evidence": "乾隆二十九年(1764年),临江及三坝相继破", "confidence": "high"}, {"subject": "乾隆二十九年(1764年)", "predicate": "has_hazard_factor", "object": "江洪", "evidence": "江坝被江洪冲溃的年份就有14个", "confidence": "medium"}, {"subject": "乾隆二十九年(1764年)", "predicate": "causes_impact", "object": "漂荡庐舍", "evidence": "江水横入圩田,堤岸尽沉,漂荡庐舍无算", "confidence": "high"}, {"subject": "乾隆二十九年(1764年)", "predicate": "causes_impact", "object": "溺死", "evidence": "有溺死者,四乡邨民挈眷奔冈", "confidence": "high"}, {"subject": "三坝", "predicate": "protects_region", "object": "圩田", "evidence": "临江及三坝相继破,江水横入圩田", "confidence": "high"}, {"subject": "坝堤", "predicate": "protects_region", "object": "无为", "evidence": "在清代无为农业水利建设达到高峰的乾隆盛世,以修建坝堤为例...达到了25处", "confidence": "high"}], "events": [{"name": "乾隆五十年(1785年)奇旱", "event_type": "DroughtEvent", "time": {"start_time": "1785年", "end_time": "1785年"}, "location": ["无为"]}, {"name": "宣统三年(1911年)五六月间大雨", "event_type": "DisasterEvent", "time": {"start_time": "1911年5月", "end_time": "1911年6月"}, "location": ["无为"]}, {"name": "乾隆二十九年(1764年)洪水", "event_type": "DisasterEvent", "time": {"start_time": "1764年", "end_time": "1764年"}, "location": ["无为", "临江"]}], "parse_error": false, "_thinking": "文本主要描述清代无为地区的水旱灾害情况。核心实体包括：地理区域\"无为\"、灾害类型（水灾、旱灾）、具体灾害事件（乾隆五十年旱灾、宣统三年洪水等）、受灾影响（人员死亡、农田受损、基础设施损毁）、防洪工程（江坝、堤防）。关键关系包括灾害影响区域、造成各类损失、防洪工程保护区域等。需注意实体必须是原文精确子串，所有关系必须有明确文本支撑。", "_verification_stats": {"original": 17, "valid": 17, "filtered": 0, "hallucination_rate": 0.0}, "doc_id": "7e1939ba8c53", "source_text": "通过上文的论述,我们可以看到清代无为因地制宜地建设了数量众多、分布广泛的农业水利工程水利兴筑、维护的各项制度与规定也逐渐成熟。这些丰富的农业水利建设也取得了成效。以人口为例,无为在顺治五年(1648年)仅55,424丁,到乾隆元年(1741年)增为454,120丁,1796年)更是达到了727,594丁。人口的快速增长是水旱灾害得到有效治理、农业取得发展的重要体现。\n\n然而,我们又可以看到这样的现实,清代无为有水、旱、震、疫、风、雪、雹、虫等自然灾害共158次。其中水灾达60次,占比近38%,旱灾33次,占比近21%;水旱灾害合计93次,占总自然灾害次数的比率达58%以上,远超过其他任何灾害及其总和。清代268年间,平均4.5年发生一次水灾,平均8.1年发生一次旱灾,总计每2.9年就发生一次水旱灾害。另外,从清代开始才有了无为江坝口决堤的记载,江坝被江洪冲溃的年份就有14个。可见清代无为水旱灾害为患之巨、发生之频繁。\n\n同时,关于水旱灾情的描述也屡屡见诸史籍。如:乾隆五十年(1785年)奇旱,“自去冬至是年终岁无雨,江潮闭,山田籽粒无收,圩之滨河者收三十之一”;五十一年(1786年)春..."}



# Gold 标注质量问题分析与修复

## 一、问题诊断

你发现的问题很典型，主要有以下几类：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        标注质量问题汇总                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ❌ 问题1：时间被误标为事件                                              │
│     "乾隆二十九年(1764年)" → DisasterEvent  ← 应该是 TemporalEntity      │
│                                                                         │
│  ❌ 问题2：实体类型混淆                                                  │
│     "山田" → AgriculturalImpact  ← 应该是 GeographicRegion 或不抽取      │
│     "大饥" → DisasterImpact  ← 可以接受但不够精确                        │
│                                                                         │
│  ❌ 问题3：时间作为事件主语                                              │
│     ("乾隆二十九年(1764年)", affects_region, "临江")  ← 逻辑错误          │
│                                                                         │
│  ⚠️ 问题4：古文表述不规范                                               │
│     "漂荡庐舍" 作为 InfrastructureDamage  ← 可接受但不够规范              │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、根本原因

| 原因 | 说明 | 解决方案 |
|------|------|----------|
| **Prompt 不够明确** | 没有强调时间和事件的区别 | 优化 Prompt |
| **TBox 类型使用不当** | 模型不清楚何时用 TemporalEntity | 在 Prompt 中加示例 |
| **历史文本特殊性** | 古文格式与现代文本不同 | 添加专门处理规则 |
| **缺少后处理** | 没有过滤明显错误的标注 | 添加规则校验 |

---

## 三、Prompt 优化方案

### 3.1 优化后的 Prompt

```python
GOLD_USER_PROMPT_COT_V2 = """请从以下文本中抽取实体和关系三元组。

{tbox_schema}

---

【待标注文本】
```
{text}
```

---

【重要规则 - 必须严格遵守】

**规则1：区分时间和事件**
- ❌ 错误："乾隆二十九年(1764年)" → DisasterEvent
- ✅ 正确："乾隆二十九年(1764年)" → TemporalEntity
- ✅ 正确："1764年洪水" 或 "乾隆二十九年洪水" → DisasterEvent
- 判断标准：如果只有年份/日期，是时间；如果有"洪水/旱灾/大水"等灾害词，才是事件

**规则2：事件命名规范**
- 事件名应包含：时间 + 地点/范围 + 灾害类型
- ✅ 正确："1998年长江特大洪水"、"乾隆五十年无为大旱"
- ❌ 错误："宣统三年(1911年)五六月间大雨" → 这是天气现象描述，不是事件名

**规则3：事件作为三元组主语时**
- 主语应是完整的灾害事件，不能是纯时间
- ❌ ("乾隆二十九年", affects_region, "无为")
- ✅ ("乾隆二十九年洪水", affects_region, "无为")

**规则4：古文实体处理**
- "大饥" → DisasterImpact（饥荒影响）✓
- "漂荡庐舍" → 不抽取（过于笼统）或标注为 InfrastructureDamage
- "山田/圩田" → GeographicRegion（农业区域），不是 AgriculturalImpact

**规则5：数值和影响的区分**
- "死亡X人" → CasualtyImpact + has_value 关系
- "经济损失X亿" → EconomicLoss + has_value 关系
- 不要把具体数字作为独立实体

---

【抽取步骤】请严格按以下步骤思考：

**Step 1: 识别时间表达式**
先标出所有时间（年份、日期、时期），类型为 TemporalEntity。
不要把纯时间误标为 DisasterEvent！

**Step 2: 识别灾害事件**
事件必须包含灾害性质（洪水、干旱、溃堤等），可以组合时间+地点+灾害类型形成事件名。

**Step 3: 识别其他实体**
地理区域、工程设施、组织机构、影响类型等。

**Step 4: 构建三元组**
确保主语不是纯时间。使用 occurs_at 关系连接事件和时间。

**Step 5: 自检**
- [ ] 是否有纯时间被标为 DisasterEvent？→ 修正
- [ ] 三元组主语是否有意义（不是纯时间/纯数字）？
- [ ] 所有实体是否在原文中原样出现？

---

请按以下 JSON 格式输出（只输出 JSON）：

{{
  "thinking": "分析过程（特别说明时间和事件的区分）",
  "entities": [
    {{"name": "实体名", "type": "类型"}}
  ],
  "triples": [
    {{
      "subject": "主语",
      "predicate": "关系",
      "object": "宾语",
      "evidence": "原文依据",
      "confidence": "high/medium/low"
    }}
  ],
  "events": [
    {{
      "name": "事件名（时间+地点+灾害类型）",
      "event_type": "DisasterEvent/DroughtEvent",
      "time": {{"start_time": "YYYY", "end_time": "YYYY"}},
      "location": ["地点"]
    }}
  ]
}}

请直接输出JSON："""
```

---

## 四、后处理校验脚本

```python
#!/usr/bin/env python3
"""
scripts/postprocess_gold.py

Gold 标注后处理：修复常见错误
"""
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Tuple


# ============================================================
# 时间模式匹配
# ============================================================

# 纯时间模式（不应作为 DisasterEvent）
PURE_TIME_PATTERNS = [
    r'^(公元前?)?\d{1,4}年$',                           # 1998年
    r'^\d{1,4}年\d{1,2}月$',                            # 1998年8月
    r'^\d{1,4}年\d{1,2}月\d{1,2}日$',                   # 1998年8月1日
    r'^(康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统).+年$',  # 乾隆五十年
    r'^(康熙|雍正|乾隆|嘉庆|道光|咸丰|同治|光绪|宣统).+年\(.+\)$',  # 乾隆五十年(1785年)
    r'^\d+世纪$',                                       # 20世纪
    r'^民国\d+年$',                                     # 民国38年
]

# 灾害关键词（如果包含这些，可能是事件而非纯时间）
DISASTER_KEYWORDS = [
    '洪水', '大水', '洪涝', '水灾', '涝灾',
    '干旱', '大旱', '旱灾', '枯水',
    '溃堤', '决口', '溃坝',
    '台风', '暴雨', '暴风雨',
    '灾', '难', '祸'
]


def is_pure_time(text: str) -> bool:
    """判断是否是纯时间表达式"""
    text = text.strip()
    
    # 检查是否匹配纯时间模式
    for pattern in PURE_TIME_PATTERNS:
        if re.match(pattern, text):
            # 再检查是否包含灾害关键词
            has_disaster_word = any(kw in text for kw in DISASTER_KEYWORDS)
            if not has_disaster_word:
                return True
    
    return False


def fix_entity_type(entity: Dict) -> Tuple[Dict, bool]:
    """修复实体类型"""
    name = entity.get("name", "")
    etype = entity.get("type", "")
    fixed = False
    
    # 修复1：纯时间被标为 DisasterEvent
    if etype == "DisasterEvent" and is_pure_time(name):
        entity["type"] = "TemporalEntity"
        entity["_fixed"] = f"DisasterEvent → TemporalEntity (纯时间)"
        fixed = True
    
    # 修复2：山田/圩田 不应是 AgriculturalImpact
    if etype == "AgriculturalImpact" and any(kw in name for kw in ["田", "地", "圩", "坝"]):
        entity["type"] = "GeographicRegion"
        entity["_fixed"] = f"AgriculturalImpact → GeographicRegion (农业区域)"
        fixed = True
    
    return entity, fixed


def fix_triple(triple: Dict, entities: List[Dict]) -> Tuple[Dict, bool, str]:
    """修复三元组"""
    subject = triple.get("subject", "")
    predicate = triple.get("predicate", "")
    obj = triple.get("object", "")
    
    # 修复1：纯时间作为主语
    if is_pure_time(subject):
        # 如果谓语是 affects_region, causes_impact 等，需要修复
        if predicate in ["affects_region", "causes_impact", "has_hazard_factor"]:
            return triple, False, f"主语 '{subject}' 是纯时间，不应作为灾害事件主语"
    
    # 修复2：检查主语/宾语是否过短（可能是噪音）
    if len(subject) < 2 or len(obj) < 2:
        return triple, False, f"主语或宾语过短"
    
    return triple, True, ""


def postprocess_gold(input_path: Path, output_path: Path) -> Dict[str, Any]:
    """后处理 Gold 标注"""
    
    stats = {
        "total_samples": 0,
        "total_entities": 0,
        "fixed_entities": 0,
        "total_triples": 0,
        "removed_triples": 0,
        "removal_reasons": {}
    }
    
    results = []
    
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            
            sample = json.loads(line)
            stats["total_samples"] += 1
            
            # 修复实体
            fixed_entities = []
            for entity in sample.get("entities", []):
                stats["total_entities"] += 1
                fixed_entity, was_fixed = fix_entity_type(entity)
                if was_fixed:
                    stats["fixed_entities"] += 1
                fixed_entities.append(fixed_entity)
            sample["entities"] = fixed_entities
            
            # 修复三元组
            valid_triples = []
            for triple in sample.get("triples", []):
                stats["total_triples"] += 1
                fixed_triple, is_valid, reason = fix_triple(triple, fixed_entities)
                
                if is_valid:
                    valid_triples.append(fixed_triple)
                else:
                    stats["removed_triples"] += 1
                    stats["removal_reasons"][reason] = stats["removal_reasons"].get(reason, 0) + 1
            
            sample["triples"] = valid_triples
            sample["_postprocess"] = {
                "original_triples": len(sample.get("triples", [])) + stats["removed_triples"],
                "valid_triples": len(valid_triples)
            }
            
            results.append(sample)
    
    # 保存
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in results:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    return stats


def main():
    import argparse
    parser = argparse.ArgumentParser(description="后处理 Gold 标注")
    parser.add_argument("--input", required=True, help="输入文件")
    parser.add_argument("--output", required=True, help="输出文件")
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("Gold 标注后处理")
    print("=" * 60)
    
    stats = postprocess_gold(Path(args.input), Path(args.output))
    
    print(f"\n处理统计:")
    print(f"  样本数: {stats['total_samples']}")
    print(f"  实体数: {stats['total_entities']}")
    print(f"  修复实体: {stats['fixed_entities']}")
    print(f"  三元组数: {stats['total_triples']}")
    print(f"  移除三元组: {stats['removed_triples']}")
    
    if stats['removal_reasons']:
        print(f"\n移除原因:")
        for reason, count in sorted(stats['removal_reasons'].items(), key=lambda x: -x[1]):
            print(f"    {reason}: {count}")
    
    print(f"\n输出: {args.output}")


if __name__ == "__main__":
    main()
```

---

## 五、推荐的执行流程

```bash
# ============================================================
# Step 1: 使用优化后的 Prompt 重新生成（或继续生成）
# ============================================================

# 更新 Prompt 后重新运行
bash scripts/p5/run_gold_annotation.sh \
    --tbox-version s3 \
    --input data/p5_eval_pool/final/test_final.jsonl \
    --text-source data/p5_eval_pool/pool_v3.jsonl \
    --output data/p5_eval_pool/gold_s3_tbox_v2.jsonl \
    --model "[官转]claude-4.5-sonnet" \
    --use-cot \
    --use-verification \
    --verification-threshold 0.7 \
    # 不加 --resume，重新开始

# ============================================================
# Step 2: 后处理已生成的标注
# ============================================================

# 如果已经生成了部分，可以先后处理
python scripts/postprocess_gold.py \
    --input data/p5_eval_pool/gold_s3_tbox_full.jsonl \
    --output data/p5_eval_pool/gold_s3_tbox_cleaned.jsonl

# ============================================================
# Step 3: 质量检查
# ============================================================

# 检查修复后的分布
python -c "
import json
from collections import Counter

entity_types = Counter()
relation_types = Counter()
time_as_event = 0
time_patterns = [
    '年$', '年\)', '月$', '日$', '世纪$'
]

with open('data/p5_eval_pool/gold_s3_tbox_cleaned.jsonl') as f:
    for line in f:
        data = json.loads(line)
        for e in data.get('entities', []):
            entity_types[e['type']] += 1
            # 检查是否有时间被标为事件
            import re
            if e['type'] == 'DisasterEvent':
                for p in time_patterns:
                    if re.search(p, e['name']):
                        time_as_event += 1
                        break
        for t in data.get('triples', []):
            relation_types[t['predicate']] += 1

print('实体类型分布:')
for t, c in entity_types.most_common(15):
    print(f'  {t}: {c}')

print()
print('关系类型分布:')
for t, c in relation_types.most_common(15):
    print(f'  {t}: {c}')

print()
print(f'疑似时间误标为事件: {time_as_event}')
"
```

---

## 六、修复后的预期效果

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 时间误标为事件 | ~15% | <1% |
| 无效三元组 | ~10% | <3% |
| 主语为纯时间 | 存在 | 已过滤 |

---

## 七、Prompt 更新快速操作

如果你不想重新生成全部，可以只更新 Prompt 文件：

```python
# 在 scripts/generate_gold_with_tbox.py 中找到 GOLD_USER_PROMPT_COT
# 替换为上面的 GOLD_USER_PROMPT_COT_V2

# 关键添加的规则：
"""
【重要规则 - 必须严格遵守】

**规则1：区分时间和事件**
- ❌ 错误："乾隆二十九年(1764年)" → DisasterEvent
- ✅ 正确："乾隆二十九年(1764年)" → TemporalEntity
- ✅ 正确："1764年洪水" → DisasterEvent

**规则2：事件作为三元组主语时**
- 主语应是完整的灾害事件，不能是纯时间
- ❌ ("乾隆二十九年", affects_region, "无为")
- ✅ ("乾隆二十九年洪水", affects_region, "无为")
"""
```

---

## 八、决策建议

```
┌─────────────────────────────────────────────────────────────┐
│                     推荐方案                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  选项A：继续当前生成 + 后处理修复                             │
│         ✅ 节省时间                                          │
│         ⚠️ 可能有遗漏                                        │
│                                                             │
│  选项B：更新 Prompt 后重新生成                               │
│         ✅ 质量更高                                          │
│         ⚠️ 需要重新跑                                        │
│                                                             │
│  推荐：选项A + 选项B 结合                                    │
│  1. 对已生成的546条使用后处理脚本修复                         │
│  2. 之后新生成的使用优化后的 Prompt                          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**立即可执行**：

```bash
# 1. 后处理当前结果
python scripts/postprocess_gold.py \
    --input data/p5_eval_pool/gold_s3_tbox_full.jsonl \
    --output data/p5_eval_pool/gold_s3_tbox_cleaned.jsonl

# 2. 检查质量
python scripts/check_gold_quality.py \
    --input data/p5_eval_pool/gold_s3_tbox_cleaned.jsonl
```


# 问题二

好的，那之前说的Prompt抽取的更改，比如规则1：区分时间和事件

❌ 错误："乾隆二十九年(1764年)" → DisasterEvent
✅ 正确："乾隆二十九年(1764年)" → TemporalEntity
✅ 正确："1764年洪水" → DisasterEvent
规则2：事件作为三元组主语时

主语应是完整的灾害事件，不能是纯时间
❌ ("乾隆二十九年", affects_region, "无为")
✅ ("乾隆二十九年洪水", affects_region, "无为")。 这样的是只应用到gold抽取吗？pred抽取需要应用吗？我理解这个其实就是加了一些few-shot对吧？


# 规则应用范围与 Few-shot 示例选择

## 一、规则应用范围

| 场景 | 是否应用规则 | 理由 |
|------|-------------|------|
| **Gold 生成** | ✅ 必须 | 确保标注质量 |
| **Pred 抽取（主实验）** | ✅ 必须 | 与 Gold 使用相同标准才公平 |
| **Pred 抽取（Baseline）** | ❌ 不用 | 证明规则的价值 |

```
┌─────────────────────────────────────────────────────────────┐
│                    规则应用策略                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Gold 生成：                                                 │
│    ✅ TBox 约束 + 规则 + CoT + 后校验                        │
│                                                             │
│  主实验（Ours）：                                            │
│    ✅ TBox 约束 + 规则 + CoT + 后校验  ← 与Gold一致          │
│                                                             │
│  消融实验（w/o 规则）：                                       │
│    ❌ TBox 约束 + CoT + 后校验（无规则）← 证明规则价值        │
│                                                             │
│  Baseline：                                                  │
│    ❌ 简单 Prompt，无 CoT 无规则       ← 最弱基线            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**是的，这本质上就是 Few-shot 指导**，通过正例/反例帮助模型理解任务。

---

## 二、高质量样例选择

从你提供的样例中，我选出 **3 个最佳 Few-shot 示例**：

### ✅ 推荐示例 1：2022年水文干旱过程（最佳）

**优点**：事件阶段划分清晰、关系类型丰富、时间处理正确

```json
{
  "doc_id": "9d95b917cd45",
  "quality_score": "★★★★★",
  "highlights": [
    "✅ 干旱阶段作为子事件识别",
    "✅ occurs_at 时间关系正确使用",
    "✅ has_hazard_factor 致灾因子关系完整",
    "✅ triggers_response 应急响应触发"
  ]
}
```

### ✅ 推荐示例 2：1995-1999年长江洪水

**优点**：水文站关系准确、数值处理规范

```json
{
  "doc_id": "6203e64b917f",
  "quality_score": "★★★★☆",
  "highlights": [
    "✅ monitors_river 水文站关系正确",
    "✅ part_of 江段层级关系",
    "✅ 事件命名规范（1995年7月鄱阳湖水系洪水）"
  ]
}
```

### ✅ 推荐示例 3：长江上游暴雨过程

**优点**：河流地理关系清晰、流域归属正确

```json
{
  "doc_id": "120fddbc1f74",
  "quality_score": "★★★★☆",
  "highlights": [
    "✅ belongs_to_basin 流域归属关系",
    "✅ located_in 地理位置关系",
    "✅ 事件命名规范（长江上游暴雨过程）"
  ]
}
```

---

## 三、Few-shot Prompt 模板

```python
FEW_SHOT_EXAMPLES = """
【示例1：干旱事件的正确处理】

原文片段：
"第一阶段(干旱露头):2022年7月8日—8月底。7月8日全省集中降雨基本结束,天气转入高温少雨阶段..."

正确抽取：
```json
{
  "entities": [
    {"name": "2022年水文干旱过程", "type": "DroughtEvent"},
    {"name": "干旱露头", "type": "DroughtEvent"},
    {"name": "2022年7月8日", "type": "TemporalEntity"},  // ✅ 时间是TemporalEntity
    {"name": "高温少雨", "type": "ClimateAnomaly"},
    {"name": "抗旱Ⅳ级应急响应", "type": "EmergencyResponse"}
  ],
  "triples": [
    {"subject": "干旱露头", "predicate": "occurs_at", "object": "2022年7月8日"},  // ✅ 使用occurs_at连接
    {"subject": "干旱露头", "predicate": "has_hazard_factor", "object": "高温少雨"},
    {"subject": "2022年水文干旱过程", "predicate": "triggers_response", "object": "抗旱Ⅳ级应急响应"}
  ]
}
```

错误示范：
- ❌ {"name": "2022年7月8日", "type": "DisasterEvent"}  // 纯时间不是事件
- ❌ {"subject": "2022年7月8日", "predicate": "affects_region", ...}  // 时间不能作主语

---

【示例2：水文站与河流关系】

原文片段：
"1998年长江出现流域性洪水,长江松滋口至金水闸492km江段水位超历史,沙市最高水位45.22m..."

正确抽取：
```json
{
  "entities": [
    {"name": "1998年长江出现流域性洪水", "type": "DisasterEvent"},  // ✅ 完整事件名
    {"name": "沙市", "type": "HydrologicalStation"},
    {"name": "45.22m", "type": "NumericValue"},
    {"name": "松滋口至金水闸492km江段", "type": "GeographicRegion"}
  ],
  "triples": [
    {"subject": "沙市", "predicate": "monitors_river", "object": "长江"},
    {"subject": "沙市", "predicate": "has_value", "object": "45.22m"},
    {"subject": "松滋口至金水闸492km江段", "predicate": "part_of", "object": "长江"}
  ]
}
```

---

【示例3：河流流域归属】

原文片段：
"长江上游发生了一次暴雨过程。强降雨主要集中在嘉陵江、岷沱江和干流附近..."

正确抽取：
```json
{
  "entities": [
    {"name": "长江上游暴雨过程", "type": "DisasterEvent"},  // ✅ 事件名包含灾害性质
    {"name": "嘉陵江", "type": "River"},
    {"name": "岷沱江", "type": "River"},
    {"name": "长江上游", "type": "GeographicRegion"},
    {"name": "长江流域", "type": "Basin"}
  ],
  "triples": [
    {"subject": "嘉陵江", "predicate": "belongs_to_basin", "object": "长江流域"},
    {"subject": "嘉陵江", "predicate": "located_in", "object": "长江上游"},
    {"subject": "长江上游暴雨过程", "predicate": "affects_region", "object": "嘉陵江"}
  ]
}
```
"""
```

---

## 四、完整 Prompt 结构

```python
EXTRACTION_PROMPT_WITH_FEWSHOT = """
{system_prompt}

{tbox_schema}

---

【⚠️ 关键规则】

**规则1：区分时间和事件**
- 纯时间表达式 → TemporalEntity（如"1998年"、"乾隆五十年"）
- 包含灾害性质 → DisasterEvent（如"1998年长江洪水"）

**规则2：三元组主语规范**
- ❌ ("1998年", affects_region, "长江流域")
- ✅ ("1998年长江洪水", affects_region, "长江流域")
- ✅ ("1998年长江洪水", occurs_at, "1998年")

**规则3：使用 occurs_at 连接事件和时间**

---

{few_shot_examples}

---

【待抽取文本】
```
{text}
```

请按 JSON 格式输出：
"""
```

---

## 五、执行建议

```bash
# 1. 更新 Prompt（添加规则和 Few-shot）
# 在 scripts/generate_gold_with_tbox.py 中更新

# 2. Gold 生成（使用完整 Prompt）
python scripts/generate_gold_with_tbox.py \
    --input data/p5_eval_pool/final/test_final.jsonl \
    --tbox outputs/cq_pipeline/final/tbox_s3_optimized.json \
    --output data/p5_eval_pool/gold_s3_v2.jsonl \
    --model "[官转]claude-4.5-sonnet" \
    --use-cot \
    --use-fewshot \
    --use-verification

# 3. 主实验 Pred（使用相同 Prompt）
python scripts/run_extraction.py \
    --model Qwen/Qwen3-8B \
    --tbox outputs/cq_pipeline/final/tbox_s3_optimized.json \
    --use-cot \
    --use-fewshot  # 与 Gold 一致

# 4. Baseline（不用规则和 Few-shot）
python scripts/run_extraction.py \
    --model Qwen/Qwen3-8B \
    --tbox outputs/cq_pipeline/final/tbox_s3_optimized.json \
    --no-cot \
    --no-fewshot
```

---

## 六、总结

| 问题 | 答案 |
|------|------|
| 规则只用于 Gold？ | ❌ Gold 和 主实验Pred 都要用，Baseline 不用 |
| 这是 Few-shot？ | ✅ 是的，通过正例/反例指导模型 |
| 选哪些样例？ | 9d95b917cd45、6203e64b917f、120fddbc1f74 |

**核心原则**：Gold 和 Pred（主实验）使用完全相同的 Prompt，才能公平评测。