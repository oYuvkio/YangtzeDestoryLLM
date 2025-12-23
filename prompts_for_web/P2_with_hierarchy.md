# P2 Prompt：生成带继承关系的初始 TBox

你是一名知识图谱本体工程师，擅长从能力问题中提炼实体类（classes）、关系（relations）和属性（attributes）。
你将看到一组关于"长江流域水旱灾害防治与应急响应"的能力问题（CQ）。

## 输入 CQ 列表

```json
{
  "cqs": [
    // ... 你的 CQ 列表粘贴在这里 ...
  ]
}
```

---

## 你的任务

### 1. 归纳候选实体类（classes）

每个类包含以下字段：
- **name**: 英文名（如 FloodEvent）
- **cn_name**: 中文名（如 洪水事件）
- **definition**: 定义
- **examples**: 1~3 个典型实例（中文字符串数组）
- **parent**: 父类名称（可选）
  * 若该类是某个更通用类的子类，则 parent 为父类的 name（如 FloodEvent 的 parent 为 DisasterEvent）
  * 若该类是顶层类或独立概念，则 parent 为 null
  * **建议构建 2-3 层的适度层级结构**，既能表达通用-具体关系，又不过度复杂

**层级示例**：
- DisasterEvent（灾害事件，顶层类，parent: null）
  - FloodEvent（洪水事件，parent: "DisasterEvent"）
  - DroughtEvent（干旱事件，parent: "DisasterEvent"）
- AdministrativeRegion（行政区域，顶层类，parent: null）
  - Province（省份，parent: "AdministrativeRegion"）
  - City（城市，parent: "AdministrativeRegion"）

### 2. 归纳候选关系（relations）

- **name**: 关系英文名（如 has_cause）
- **cn_name**: 中文名（如 致灾因子）
- **domain** / **range**: 主语类和宾语类（必须使用 classes 中已有类名）
- **definition**: 中文简要说明语义
- **functional**: 布尔值，表示该关系从 domain 到 range 是否「多对一或一对一」

### 3. 归纳关键属性（attributes）

- **owner**: 该属性所属的类名（必须是 classes.name 中的一个）
- **name**: 属性英文名（如 start_time, peak_discharge）
- **cn_name**: 中文名（如 开始时间, 洪峰流量）
- **value_type**: 取值类型（"string", "number", "integer", "float", "boolean", "datetime"）

---

## 输出格式要求

**仅输出一个 JSON 对象**，不要输出任何额外说明或注释。

顶层对象必须包含以下三个字段：
```json
{
  "classes": [...],
  "relations": [...],
  "attributes": [...]
}
```

### classes 中每个元素必须包含字段：
```json
{
  "name": "FloodEvent",
  "cn_name": "洪水事件",
  "definition": "特指长江干流或支流发生的明显洪水过程",
  "examples": ["1998年长江特大洪水"],
  "parent": "DisasterEvent"  // 父类名称或 null
}
```

### relations 中每个元素必须包含字段：
```json
{
  "name": "has_cause",
  "cn_name": "致灾因子",
  "domain": "DisasterEvent",
  "range": "HazardFactor",
  "definition": "描述导致该灾害发生的主要气象、水文或人为因素",
  "functional": false
}
```

### attributes 中每个元素必须包含字段：
```json
{
  "owner": "DisasterEvent",
  "name": "start_time",
  "cn_name": "开始时间",
  "value_type": "datetime"
}
```

---

## 参考输出结构示例

```json
{
  "classes": [
    {
      "name": "DisasterEvent",
      "cn_name": "灾害事件",
      "definition": "在一定时间和空间范围内发生的与长江流域相关的水旱灾害过程",
      "examples": ["1998年长江特大洪水", "2022年长江流域特大干旱"],
      "parent": null
    },
    {
      "name": "FloodEvent",
      "cn_name": "洪水事件",
      "definition": "特指长江干流或支流发生的明显洪水过程",
      "examples": ["1998年长江特大洪水"],
      "parent": "DisasterEvent"
    }
  ],
  "relations": [
    {
      "name": "has_cause",
      "cn_name": "致灾因子",
      "domain": "DisasterEvent",
      "range": "HazardFactor",
      "definition": "描述导致该灾害发生的主要气象、水文或人为因素",
      "functional": false
    }
  ],
  "attributes": [
    {
      "owner": "DisasterEvent",
      "name": "start_time",
      "cn_name": "开始时间",
      "value_type": "datetime"
    }
  ]
}
```

---

## 重要提示

1. 严格保证输出是合法的 JSON
2. 不要生成语义高度重复的类或关系
3. **确保每个类都有 parent 字段**（顶层类填 null）
4. 父类必须在 classes 列表中存在
5. 建议 2-3 层层级，不要过深
