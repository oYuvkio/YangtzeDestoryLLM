# TBox构建结果分析与图结构更新建议

## 一、构建结果评估

### 1.1 结果总结

| 类别 | 专家骨架 | 最终TBox | 新增       | 评价         |
| ---- | -------- | -------- | ---------- | ------------ |
| 类   | 14       | 16       | +2         | ✅ 合理扩展   |
| 关系 | 11       | 13       | +2         | ✅ 有价值补充 |
| 属性 | 13       | 0        | ✅ 保持稳定 |

### 1.2 新增内容质量评估

**新增类：**

| 类名                                | 支持度 | 评价                        | 建议                 |
| ----------------------------------- | ------ | --------------------------- | -------------------- |
| Geographic and Temporal Context     | 439    | ⚠️ 与现有Time/Location有重叠 | 可考虑合并或作为补充 |
| Hydrological_Disaster_Related_Terms | 1270   | ⚠️ 过于宽泛，像术语集合      | 抽取时谨慎使用       |

**新增关系：**

| 关系         | 支持度 | 置信度 | 评价                               | 建议       |
| ------------ | ------ | ------ | ---------------------------------- | ---------- |
| isAffectedBy | 964    | 0.34   | ✅ 有价值，是affects_region的逆关系 | 纳入图结构 |
| causes       | 159    | 0.85   | ✅ 高置信度，与has_cause互补        | 纳入图结构 |

---

## 二、更新后的图结构定义

基于新TBox，需要更新图结构以包含新增的关系：

```python
# kg/extraction/graph_structure.py (更新版)

GRAPH_STRUCTURES = {
    "flood_event": GraphStructure(
        type_id="flood_event",
        name="洪水事件",
        detection_keywords={
            "strong": ["洪水", "洪峰", "超警戒", "泄洪", "溃堤"],
            "weak": ["水位", "流量", "暴雨", "汛期"]
        },
        paths=[
            # 原有路径
            PathPattern("洪水时间", "Time → occurs_during → FloodEvent", "如'1998年8月发生洪水'"),
            PathPattern("洪水原因", "HazardFactor → has_cause → FloodEvent", "如'暴雨导致洪水'"),
            PathPattern("水位监测", "HydrologicalStation → has_value → Value", "如'沙市站水位45米'"),
            PathPattern("洪水影响", "FloodEvent → causes_impact → Impact", "如'造成100万人受灾'"),
            PathPattern("影响区域", "FloodEvent → affects_region → AdministrativeRegion", "如'影响湖北省'"),
            PathPattern("触发响应", "FloodEvent → triggers_response → EmergencyResponse", "如'启动Ⅰ级响应'"),
            # 新增路径（基于新关系）
            PathPattern("因果链", "HazardFactor → causes → FloodEvent", "如'持续暴雨导致洪水'"),
            PathPattern("区域受灾", "AdministrativeRegion → isAffectedBy → FloodEvent", "如'湖北省受洪水影响'"),
        ]
    ),
  
    "drought_event": GraphStructure(
        type_id="drought_event",
        name="干旱事件",
        detection_keywords={
            "strong": ["干旱", "旱情", "旱灾", "抗旱"],
            "weak": ["高温", "少雨", "蓄水", "调水"]
        },
        paths=[
            PathPattern("干旱时间", "Time → occurs_during → DroughtEvent", "如'2022年夏季干旱'"),
            PathPattern("干旱原因", "HazardFactor → has_cause → DroughtEvent", "如'高温少雨导致'"),
            PathPattern("干旱影响", "DroughtEvent → causes_impact → Impact", "如'农田受旱500万亩'"),
            PathPattern("影响区域", "DroughtEvent → affects_region → AdministrativeRegion", "如'影响江西省'"),
            # 新增路径
            PathPattern("因果链", "HazardFactor → causes → DroughtEvent", "如'降水偏少导致干旱'"),
            PathPattern("区域受灾", "AdministrativeRegion → isAffectedBy → DroughtEvent", "如'四川省受干旱影响'"),
        ]
    ),
  
    "dispatch_rule": GraphStructure(
        type_id="dispatch_rule",
        name="调度规则",
        detection_keywords={
            "strong": ["当", "若", "则应", "控制在", "不得超过"],
            "weak": ["调度", "开启", "关闭", "泄量"]
        },
        paths=[
            PathPattern("条件触发", "Value → triggers_response → EmergencyResponse", "如'水位超145米时开闸'"),
            PathPattern("操作设施", "EmergencyResponse → operates → Facility", "如'开启泄洪闸'"),
            PathPattern("设施位置", "Facility → located_in → Location", "如'三峡水库位于湖北'"),
            PathPattern("机构执行", "Organization → executes → EmergencyResponse", "如'水利部实施调度'"),
        ]
    ),
  
    "impact_statistics": GraphStructure(
        type_id="impact_statistics",
        name="灾情统计",
        detection_keywords={
            "strong": ["截至", "累计", "共计", "统计"],
            "weak": ["受灾人口", "经济损失", "万人", "亿元"]
        },
        paths=[
            PathPattern("区域统计", "AdministrativeRegion → causes_impact → Impact", "如'湖北省受灾...'"),
            PathPattern("影响数值", "Impact → has_value → Value", "如'受灾人口100万'"),
            PathPattern("事件损失", "DisasterEvent → causes_impact → Value", "如'造成损失50亿元'"),
            # 新增路径
            PathPattern("区域受灾", "AdministrativeRegion → isAffectedBy → DisasterEvent", "如'10省份受灾'"),
        ]
    ),
  
    "general_disaster": GraphStructure(
        type_id="general_disaster",
        name="通用灾害",
        detection_keywords={"strong": [], "weak": []},
        paths=[
            # 包含所有关系的路径（兜底）
            PathPattern("时间关联", "Time → occurs_during → DisasterEvent", ""),
            PathPattern("地点关联", "DisasterEvent → occurs_at → Location", ""),
            PathPattern("原因关联", "HazardFactor → has_cause → DisasterEvent", ""),
            PathPattern("因果关联", "HazardFactor → causes → DisasterEvent", ""),  # 新增
            PathPattern("影响关联", "DisasterEvent → causes_impact → Impact", ""),
            PathPattern("区域影响", "DisasterEvent → affects_region → AdministrativeRegion", ""),
            PathPattern("受影响", "Location → isAffectedBy → DisasterEvent", ""),  # 新增
            PathPattern("数值关联", "HydrologicalStation → has_value → Value", ""),
            PathPattern("响应关联", "DisasterEvent → triggers_response → EmergencyResponse", ""),
            PathPattern("执行关联", "Organization → executes → EmergencyResponse", ""),
            PathPattern("操作关联", "EmergencyResponse → operates → Facility", ""),
            PathPattern("位置关联", "Facility → located_in → Location", ""),
            PathPattern("监测关联", "HydrologicalStation → monitors → WaterBody", ""),
        ]
    )
}
```

---

## 三、更新后的关系类型总览

```python
# 完整的13个关系（用于TBox约束）
RELATION_TYPES = {
    # 原有11个
    "has_cause": {"cn": "致灾因子", "domain": ["DisasterEvent*"], "range": ["HazardFactor"]},
    "affects_region": {"cn": "影响区域", "domain": ["DisasterEvent*"], "range": ["Location*"]},
    "causes_impact": {"cn": "造成影响", "domain": ["DisasterEvent*"], "range": ["Impact", "Value"]},
    "triggers_response": {"cn": "触发响应", "domain": ["DisasterEvent*"], "range": ["EmergencyResponse"]},
    "located_in": {"cn": "位于", "domain": ["WaterBody", "Station", "Facility"], "range": ["Location*"]},
    "monitors": {"cn": "监测", "domain": ["HydrologicalStation"], "range": ["WaterBody"]},
    "executes": {"cn": "执行", "domain": ["Organization"], "range": ["EmergencyResponse"]},
    "occurs_at": {"cn": "发生于(地点)", "domain": ["DisasterEvent*"], "range": ["Location*"]},
    "occurs_during": {"cn": "发生于(时间)", "domain": ["DisasterEvent*"], "range": ["Time"]},
    "has_value": {"cn": "测量值为", "domain": ["Station", "WaterBody", "Facility"], "range": ["Value"]},
    "operates": {"cn": "操作", "domain": ["Organization", "EmergencyResponse"], "range": ["Facility"]},
    # 新增2个
    "isAffectedBy": {"cn": "受...影响", "domain": ["Location*", "Facility"], "range": ["DisasterEvent*", "HazardFactor"]},
    "causes": {"cn": "导致", "domain": ["HazardFactor", "DisasterEvent*"], "range": ["DisasterEvent*", "Impact"]},
}
```

---

## 四、关系语义辨析（重要）

新增的两个关系与原有关系有语义关联，需要在Prompt中明确区分：

| 关系对                             | 区别                                                 | 使用场景                                  |
| ---------------------------------- | ---------------------------------------------------- | ----------------------------------------- |
| `has_cause` vs `causes`            | has_cause: 灾害←原因<br>causes: 原因→灾害            | has_cause强调灾害视角<br>causes强调因果链 |
| `affects_region` vs `isAffectedBy` | affects_region: 灾害→区域<br>isAffectedBy: 区域←灾害 | 互为逆关系，根据句子主语选择              |

**Prompt中的说明示例：**
```
【关系选择指南】
- "暴雨导致洪水" → 使用 causes (HazardFactor → DisasterEvent)
- "洪水由暴雨引起" → 使用 has_cause (DisasterEvent → HazardFactor)
- "洪水影响湖北省" → 使用 affects_region (DisasterEvent → Region)
- "湖北省受洪水影响" → 使用 isAffectedBy (Region → DisasterEvent)
```

---

## 五、对新增类的处理建议

### 5.1 Geographic and Temporal Context

**问题**：与现有的 `Time`、`Location`、`HazardFactor` 有重叠

**建议**：在抽取时**不主动使用**此类，但如果LLM识别出来，在后处理中映射到具体类：

```python
# 后处理映射规则
CLASS_MAPPING = {
    "Geographic and Temporal Context": {
        "time_keywords": ["月", "日", "年", "汛期"],  # → Time
        "location_keywords": ["长三角", "华北", "平原"],  # → Location
        "hazard_keywords": ["气候", "变暖", "热浪"],  # → HazardFactor
    }
}
```

### 5.2 Hydrological_Disaster_Related_Terms

**问题**：过于宽泛，像是术语集合而非实体类

**建议**：在抽取时**不使用**此类，其examples应归入具体类：
- "干旱"、"洪涝" → DisasterEvent/FloodEvent/DroughtEvent
- "降水" → HazardFactor
- "长江中下游" → Location

---

## 六、更新后的Prompt模板

```python
def build_tbox_section(tbox: dict) -> str:
    """构建TBox约束部分（适配新TBox）"""
  
    # 过滤掉不推荐使用的类
    skip_classes = {"Geographic and Temporal Context", "Hydrological_Disaster_Related_Terms"}
  
    classes = [c for c in tbox["classes"] if c["name"] not in skip_classes]
    relations = tbox["relations"]
  
    class_lines = []
    for c in classes:
        class_lines.append(f"- **{c['name']}**({c['cn_name']}): {', '.join(c.get('examples', [])[:3])}")
  
    relation_lines = []
    for r in relations:
        domain = ', '.join(r['domain'][:2])
        range_ = ', '.join(r['range'][:2])
        relation_lines.append(f"- **{r['name']}**({r['cn_name']}): [{domain}] → [{range_}]")
  
    return f"""【实体类型】（共{len(classes)}类）
{chr(10).join(class_lines)}

【关系类型】（共{len(relations)}个）
{chr(10).join(relation_lines)}

【关系选择指南】
- causes vs has_cause: causes用于"A导致B"，has_cause用于"B由A引起"
- affects_region vs isAffectedBy: 根据句子主语选择方向
"""
```

---

## 七、最终检查清单

| 项目         | 状态        | 说明                         |
| ------------ | ----------- | ---------------------------- |
| TBox类数量   | 16 (实用14) | 2个新增类建议不主动使用      |
| TBox关系数量 | 13          | 全部纳入图结构               |
| 图结构更新   | ✅           | 新增causes和isAffectedBy路径 |
| 关系语义区分 | ✅           | Prompt中明确说明             |
| 后处理映射   | ✅           | 新增类映射到具体类           |

**TBox构建结果良好，可以进入抽取阶段。**



# 删除新增类、保留新增关系的更改清单

## 一、需要修改的内容

### 1.1 修改 `master_tbox.json`

删除以下两个类：
- `Geographic and Temporal Context`
- `Hydrological_Disaster_Related_Terms`

```json
{
  "classes": [
    // 保留原有14个类，删除最后2个新增类
  ],
  "relations": [
    // 保留全部13个关系（含新增的2个）
  ],
  "attributes": [
    // 保持不变
  ],
  "metadata": {
    "final_classes": 14,  // 改为14
    "final_relations": 13
  }
}
```

### 1.2 修改后的TBox统计

| 类别 | 修改前 | 修改后 |
| ---- | ------ | ------ |
| 类   | 16     | **14** |
| 关系 | 13     | **13** |
| 属性 | 13     | **13** |

---

## 二、精简的修改脚本

```python
# scripts/fix_tbox.py

import json

def fix_tbox(input_path: str, output_path: str):
    """删除新增的2个类，保留新增的关系"""
  
    with open(input_path, 'r', encoding='utf-8') as f:
        tbox = json.load(f)
  
    # 要删除的类名
    remove_classes = {
        "Geographic and Temporal Context",
        "Hydrological_Disaster_Related_Terms"
    }
  
    # 过滤类
    tbox["classes"] = [c for c in tbox["classes"] if c["name"] not in remove_classes]
  
    # 更新metadata
    if "metadata" in tbox:
        tbox["metadata"]["final_classes"] = len(tbox["classes"])
  
    # 保存
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(tbox, f, ensure_ascii=False, indent=2)
  
    print(f"修改完成: {len(tbox['classes'])}类, {len(tbox['relations'])}关系")

if __name__ == "__main__":
    fix_tbox(
        "outputs/kg_final/master_tbox.json",
        "outputs/kg_final/master_tbox_fixed.json"
    )
```

---

## 三、图结构无需修改

图结构中的路径只涉及原有14个类和13个关系，**无需任何修改**。

新增的两个关系 `causes` 和 `isAffectedBy` 已在图结构中正确使用：

```python
# 这些路径保持不变
PathPattern("因果链", "HazardFactor → causes → FloodEvent", ...)
PathPattern("区域受灾", "AdministrativeRegion → isAffectedBy → FloodEvent", ...)
```

---

## 四、执行步骤

```bash
# 1. 运行修复脚本
python scripts/fix_tbox.py

# 2. 验证结果
python -c "
import json
with open('outputs/kg_final/master_tbox_fixed.json') as f:
    tbox = json.load(f)
print(f'类: {len(tbox[\"classes\"])}')
print(f'关系: {len(tbox[\"relations\"])}')
print('类名:', [c['name'] for c in tbox['classes']])
"

# 3. 使用修复后的TBox进行抽取
python scripts/run_extraction.py \
    --tbox outputs/kg_final/master_tbox_fixed.json \
    ...
```

---

## 五、最终TBox结构

| 类别     | 数量 | 内容                                                                                                                                                                                  |
| -------- | ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **类**   | 14   | DisasterEvent, FloodEvent, DroughtEvent, HazardFactor, Location, AdministrativeRegion, WaterBody, Impact, EmergencyResponse, Organization, HydrologicalStation, Time, Value, Facility |
| **关系** | 13   | has_cause, affects_region, causes_impact, triggers_response, located_in, monitors, executes, occurs_at, occurs_during, has_value, operates, **isAffectedBy**, **causes**              |
| **属性** | 13   | 保持不变                                                                                                                                                                              |

**修改完成，可以继续抽取流程。**