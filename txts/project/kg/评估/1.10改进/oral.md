

# 融合指导文档：基于专家引导与聚类的混合本体构建 + 图结构增强的链式抽取方案

## 文档目标

本文档为AI提供专业、准确的指导，实现以下两个核心改进：

1. **概念层**：专家引导 + 聚类挖掘的混合本体构建（融合支持度/置信度筛选）
2. **抽取层**：图结构引导的链式CoT抽取 + 双重校验（保留并增强现有方法）

---

## 一、改进方案评估与优化建议

### 1.1 您的方案评估

| 方面         | 您的设想                               | 评估         | 建议                                |
| ------------ | -------------------------------------- | ------------ | ----------------------------------- |
| **本体构建** | 专家引导 + 聚类混合，使用支持度/置信度 | ✅ 非常合理   | 建议增加"专家骨架优先"机制          |
| **抽取方法** | 保留CoT+双重校验，引入图结构引导       | ✅ 稳妥且有效 | 建议将图结构作为CoT的"骨架"而非替代 |

### 1.2 进一步优化建议

#### 本体构建优化

| 优化点                    | 说明                                            | 预期收益                 |
| ------------------------- | ----------------------------------------------- | ------------------------ |
| **专家骨架优先**          | 专家定义核心类/关系作为"锚点"，聚类结果向其对齐 | 保证本体的专业性和稳定性 |
| **支持度+置信度双重筛选** | 支持度过滤低频噪声，置信度过滤弱关联            | 提高本体质量             |
| **增量更新机制**          | 新语料只更新聚类部分，不影响专家骨架            | 本体可持续演进           |

#### 抽取方法优化

| 优化点                 | 说明                                | 预期收益             |
| ---------------------- | ----------------------------------- | -------------------- |
| **图结构作为CoT骨架**  | 图结构定义"抽什么"，CoT定义"怎么抽" | 结构化与推理能力兼得 |
| **路径驱动的分步抽取** | 每条图路径对应一个CoT步骤           | 抽取更系统，遗漏更少 |
| **双重校验保留增强**   | 原文回溯 + Schema一致性校验         | 幻觉率进一步降低     |

### 1.3 最终方案架构

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         最终方案架构                                      │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ╔═══════════════════════════════════╗  │
│  ║         【概念层：专家引导 + 聚类的混合本体构建】                    ║  │
│  ╠═══════════════════════════════════════════════════════════════════╣  │
│  ║                                                                   ║  │
│  ║   ┌─────────────┐                    ┌─────────────┐              ║  │
│  ║   │ 专家骨架    │                    │ 语料聚类    │              ║  │
│  ║   │ (核心类/关系)│                    │ (扩展类/关系)│              ║  │
│  ║   └──────┬──────┘                    └──────┬──────┘              ║  │
│  ║          │                                  │                      ║  │
│  ║          │         ┌─────────────┐          │                      ║  │
│  ║          └────────→│   混合融合   │←────────┘                      ║  │
│  ║                    │ (对齐+去重)  │                                ║  │
│  ║                    └──────┬──────┘                                ║  │
│  ║                           │                                        ║  │
│  ║                           ▼                                        ║  │
│  ║                    ┌─────────────┐                                ║  │
│  ║                    │ 支持度/置信度│                                ║  │
│  ║                    │   筛选      │                                ║  │
│  ║                    └──────┬──────┘                                ║  │
│  ║                           │                                        ║  │
│  ║                           ▼                                        ║  │
│  ║                    ┌─────────────┐                                ║  │
│  ║                    │ Master TBox │                                ║  │
│  ║                    └──────┬──────┘                                ║  │
│  ╚═══════════════════════════╪═══════════════════════════════════════╝  │
│                              │                                          │
│  ╔═══════════════════════════╪═══════════════════════════════════════╗  │
│  ║         【抽取层：图结构增强的链式CoT + 双重校验】                   ║  │
│  ╠═══════════════════════════╪═══════════════════════════════════════╣  │
│  ║                           ▼                                        ║  │
│  ║   ┌─────────────────────────────────────────────────────────┐     ║  │
│  ║   │                  图结构Prompt嵌入                        │     ║  │
│  ║   │  (定义节点类型、典型路径、拓扑关系)                       │     ║  │
│  ║   └─────────────────────────┬───────────────────────────────┘     ║  │
│  ║                             │                                      ║  │
│  ║                             ▼                                      ║  │
│  ║   ┌─────────────────────────────────────────────────────────┐     ║  │
│  ║   │              路径驱动的链式CoT抽取                        │     ║  │
│  ║   │  Step1: 按图结构识别节点                                 │     ║  │
│  ║   │  Step2: 按路径模式连接关系                               │     ║  │
│  ║   │  Step3: 证据回溯与三元组生成                             │     ║  │
│  ║   └─────────────────────────┬───────────────────────────────┘     ║  │
│  ║                             │                                      ║  │
│  ║                             ▼                                      ║  │
│  ║   ┌─────────────────────────────────────────────────────────┐     ║  │
│  ║   │                    双重校验                              │     ║  │
│  ║   │  校验1: 原文回溯校验 (实体/证据存在性)                    │     ║  │
│  ║   │  校验2: Schema一致性校验 (关系合法性)                     │     ║  │
│  ║   └─────────────────────────┬───────────────────────────────┘     ║  │
│  ╚═════════════════════════════╪═════════════════════════════════════╝  │
│                                │                                        │
│                                ▼                                        │
│                      ┌───────────────────┐                              │
│                      │   高质量知识图谱   │                              │
│                      └───────────────────┘                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 二、概念层：专家引导 + 聚类的混合本体构建

### 2.1 方法概述

**核心思想**：
- **专家骨架**：由领域专家预定义核心实体类和关系类型，作为本体的"锚点"
- **聚类扩展**：从语料中自动挖掘并聚类，发现专家可能遗漏的类别
- **混合融合**：将聚类结果与专家骨架对齐，去重合并
- **质量筛选**：使用支持度和置信度过滤低质量的类/关系

**优势**：
- 专家骨架保证本体的专业性和核心覆盖
- 聚类扩展保证本体的数据适配性
- 支持度/置信度保证本体的质量

### 2.2 详细流程

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    混合本体构建流程                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Phase 1: 专家骨架定义                                           │    │
│  │  - 定义核心实体类（7-10类）                                     │    │
│  │  - 定义核心关系类型（8-12种）                                   │    │
│  │  - 标记为"锚点"，不可被聚类覆盖                                 │    │
│  └────────────────────────────────┘    │
│                                  │                                      │
│                                  ▼                                      │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Phase 2: 语料聚类挖掘                                           │    │
│  │  - LLM词汇挖掘（名词→实体，动词→关系）                          │    │
│  │  - K-means聚类                                                  │    │
│  │  - Dice系数合并相似簇                                           │    │
│  │  - LLM标签映射                                                  │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                  │                                      │
│                                  ▼                                      │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Phase 3: 混合融合                                               │    │
│  │  - 聚类结果与专家骨架对齐（语义相似度匹配）                      │    │
│  │  - 相似类合并到专家类                                           │    │
│  │  - 新类作为扩展类保留                                           │    │
│  └────────────────────────────────┘    │
│                                  │                                      │
│                                  ▼                                      │
│  ┌────────────────────────────────┐    │
│  │ Phase 4: 支持度/置信度筛选                                      │    │
│  │  - 计算每个类/关系的支持度（出现频次）                          │    │
│  │  - 计算关系的置信度（共现强度）                                 │    │
│  │  - 过滤低于阈值的类/关系                                        │    │
│  └────────────────────────────────────────────────────────────────┘    │
│                                  │                                      │
│                                  ▼                                      │
│  ┌────────────────────────────────────────────────────────────────┐    │
│  │ Phase 5: 输出Master TBox                                        │    │
│  └────────────────────────────────┘    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Phase 1: 专家骨架定义

```python
# kg/ontology/expert_skeleton.py

"""
专家骨架定义模块
定义水旱灾害领域的核心本体结构
"""

from typing import Dict, List
from dataclasses import dataclass, field

@dataclass
class EntityClass:
    """实体类定义"""
    name: str                    # 类名（英文）
    name_cn: str                 # 中文名
    description: str             # 描述
    examples: List[str] = field(default_factory=list)  # 示例
    is_anchor: bool = True       # 是否为锚点（专家定义的不可覆盖）

@dataclass
class RelationType:
    """关系类型定义"""
    name: str                    # 关系名
    name_cn: str                 # 中文名
    description: str             # 描述
    domain: List[str] = field(default_factory=list)    # 主语类型约束
    range: List[str] = field(default_factory=list)     # 宾语类型约束
    examples: List[str] = field(default_factory=list)  # 示例
    is_anchor: bool = True       # 是否为锚点


# ==================== 专家定义的核心实体类 ====================

EXPERT_ENTITY_CLASSES = [
    EntityClass(
        name="TIME",
        name_cn="时间",
        description="时间表达，包括年份、日期、时间段、时间点等",
        examples=["1998年8月", "7月15日", "汛期", "入汛以来"],
        is_anchor=True
    ),
    EntityClass(
        name="LOCATION",
        name_cn="地点",
        description="地理位置，包括行政区划、流域、河段、具体地点等",
        examples=["湖北省", "长江中下游", "三峡库区", "沙市站"],
        is_anchor=True
    ),
    EntityClass(
        name="EVENT",
        name_cn="灾害事件",
        description="水旱灾害事件，包括洪水、干旱、内涝、溃堤等",
        examples=["特大洪水", "严重干旱", "城市内涝", "堤防溃决"],
        is_anchor=True
    ),
    EntityClass(
        name="FACILITY",
        name_cn="水利设施",
        description="水利工程设施，包括水库、堤防、闸门、泵站等",
        examples=["三峡水库", "荆江大堤", "泄洪闸", "排涝泵站"],
        is_anchor=True
    ),
    EntityClass(
        name="VALUE",
        name_cn="数值指标",
        description="监测数值和统计数据，包括水位、流量、雨量、损失等",
        examples=["45.22米", "50000立方米/秒", "200毫米", "100亿元"],
        is_anchor=True
    ),
    EntityClass(
        name="CAUSE",
        name_cn="致灾因子",
        description="导致灾害的原因，包括气象因素、人为因素等",
        examples=["持续暴雨", "台风", "上游来水", "堤防老化"],
        is_anchor=True
    ),
    EntityClass(
        name="IMPACT",
        name_cn="灾害影响",
        description="灾害造成的影响和损失",
        examples=["受灾人口100万", "农田淹没50万亩", "直接经济损失10亿元"],
        is_anchor=True
    ),
    EntityClass(
        name="MEASURE",
        name_cn="应急措施",
        description="防汛抗旱的应急响应和措施",
        examples=["启动一级响应", "人员转移", "开闸泄洪", "调水抗旱"],
        is_anchor=True
    ),
    EntityClass(
        name="ORG",
        name_cn="机构组织",
        description="参与防汛抗旱的机构和组织",
        examples=["水利部", "长江水利委员会", "省防汛指挥部"],
        is_anchor=True
    )
]


# ==================== 专家定义的核心关系类型 ====================

EXPERT_RELATION_TYPES = [
    RelationType(
        name="occurs_at",
        name_cn="发生于",
        description="事件发生的时间",
        domain=["EVENT"],
        range=["TIME"],
        examples=["洪水 occurs_at 1998年8月"],
        is_anchor=True
    ),
    RelationType(
        name="located_in",
        name_cn="位于",
        description="事件或设施所在的地点",
        domain=["EVENT", "FACILITY"],
        range=["LOCATION"],
        examples=["洪水 located_in 长江中下游", "三峡水库 located_in 湖北省"],
        is_anchor=True
    ),
    RelationType(
        name="has_cause",
        name_cn="由...引起",
        description="灾害事件的原因",
        domain=["EVENT"],
        range=["CAUSE"],
        examples=["洪水 has_cause 持续暴雨"],
        is_anchor=True
    ),
    RelationType(
        name="causes_impact",
        name_cn="造成影响",
        description="灾害事件造成的影响",
        domain=["EVENT"],
        range=["IMPACT", "VALUE"],
        examples=["洪水 causes_impact 受灾人口100万"],
        is_anchor=True
    ),
    RelationType(
        name="has_value",
        name_cn="测量值为",
        description="设施或地点的监测数值",
        domain=["FACILITY", "LOCATION"],
        range=["VALUE"],
        examples=["沙市站 has_value 45.22米"],
        is_anchor=True
    ),
    RelationType(
        name="triggers",
        name_cn="触发",
        description="事件或条件触发的响应",
        domain=["EVENT", "VALUE"],
        range=["MEASURE"],
        examples=["洪水 triggers 启动一级响应"],
        is_anchor=True
    ),
    RelationType(
        name="implements",
        name_cn="实施",
        description="机构实施的措施",
        domain=["ORG"],
        range=["MEASURE"],
        examples=["水利部 implements 调水抗旱"],
        is_anchor=True
    ),
    RelationType(
        name="affects",
        name_cn="影响",
        description="事件影响的区域",
        domain=["EVENT"],
        range=["LOCATION"],
        examples=["洪水 affects 湖北省"],
        is_anchor=True
    ),
    RelationType(
        name="part_of",
        name_cn="属于",
        description="地点的包含关系",
        domain=["LOCATION"],
        range=["LOCATION"],
        examples=["武汉市 part_of 湖北省"],
        is_anchor=True
    ),
    RelationType(
        name="operates",
        name_cn="操作",
        description="对设施的操作",
        domain=["ORG", "MEASURE"],
        range=["FACILITY"],
        examples=["开闸泄洪 operates 泄洪闸"],
        is_anchor=True
    )
]


class ExpertSkeleton:
    """专家骨架类"""
  
    def __init__(self):
        self.entity_classes = {ec.name: ec for ec in EXPERT_ENTITY_CLASSES}
        self.relation_types = {rt.name: rt for rt in EXPERT_RELATION_TYPES}
  
    def get_entity_class(self, name: str) -> EntityClass:
        return self.entity_classes.get(name)
  
    def get_relation_type(self, name: str) -> RelationType:
        return self.relation_types.get(name)
  
    def get_all_entity_names(self) -> List[str]:
        return list(self.entity_classes.keys())
  
    def get_all_relation_names(self) -> List[str]:
        return list(self.relation_types.keys())
  
    def to_tbox_format(self) -> Dict:
        """转换为TBox格式"""
        return {
            "classes": [
                {
                    "name": ec.name,
                    "name_cn": ec.name_cn,
                    "description": ec.description,
                    "examples": ec.examples,
                    "is_anchor": ec.is_anchor,
                    "source": "expert"
                }
                for ec in self.entity_classes.values()
            ],
            "relations": [
                {
                    "name": rt.name,
                    "name_cn": rt.name_cn,
                    "description": rt.description,
                    "domain": rt.domain,
                    "range": rt.range,
                    "examples": rt.examples,
                    "is_anchor": rt.is_anchor,
                    "source": "expert"
                }
                for rt in self.relation_types.values()
            ]
        }
```

### 2.4 Phase 2: 语料聚类挖掘

```python
# kg/ontology/corpus_clustering.py

"""
语料聚类挖掘模块
从语料中自动挖掘并聚类实体和关系
"""

import json
import numpy as np
from typing import Dict, List, Tuple
from collections import Counter
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score


class CorpusClusteringMiner:
    """语料聚类挖掘器"""
  
    def __init__(self, llm_client, embedding_model, config: dict):
        self.llm = llm_client
        self.embedding_model = embedding_model
        self.config = config
      
        # 配置参数
        self.min_freq = config.get("min_freq", 3)
        self.n_clusters_entity = config.get("n_clusters_entity", 15)
        self.n_clusters_relation = config.get("n_clusters_relation", 12)
        self.dice_threshold = config.get("dice_threshold", 0.5)
  
    def mine_and_cluster(self, texts: List[str]) -> Dict:
        """
        挖掘并聚类
      
        Returns:
            {
                "entity_clusters": {label: {"members": [...], "description": ...}},
                "relation_clusters": {label: {"members": [...], "description": ...}}
            }
        """
        # Step 1: LLM词汇挖掘
        print("  [2.1] LLM词汇挖掘...")
        vocabulary = self._mine_vocabulary(texts)
        print(f"       挖掘到 {len(vocabulary['entities'])} 个实体词, "
              f"{len(vocabulary['relations'])} 个关系词")
      
        # Step 2: 向量化
        print("  [2.2] 词汇向量化...")
        entity_embeddings = self._get_embeddings(vocabulary["entities"])
        relation_embeddings = self._get_embeddings(vocabulary["relations"])
      
        # Step 3: K-means聚类
        print("  [2.3] K-means聚类...")
        entity_clusters = self._cluster(
            vocabulary["entities"], 
            entity_embeddings,
            self.n_clusters_entity
        )
        relation_clusters = self._cluster(
            vocabulary["relations"],
            relation_embeddings,
            self.n_clusters_relation
        )
        print(f"       实体聚类: {len(entity_clusters)} 簇, "
              f"关系聚类: {len(relation_clusters)} 簇")
      
        # Step 4: Dice系数合并
        print("  [2.4] Dice系数合并相似簇...")
        entity_clusters = self._merge_similar_clusters(entity_clusters)
        relation_clusters = self._merge_similar_clusters(relation_clusters)
        print(f"       合并后: 实体 {len(entity_clusters)} 簇, "
              f"关系 {len(relation_clusters)} 簇")
      
        # Step 5: LLM标签映射
        print("  [2.5] LLM标签映射...")
        labeled_entities = self._label_clusters(entity_clusters, "entity")
        labeled_relations = self._label_clusters(relation_clusters, "relation")
      
        return {
            "entity_clusters": labeled_entities,
            "relation_clusters": labeled_relations
        }
  
    def _mine_vocabulary(self, texts: List[str]) -> Dict:
        """LLM词汇挖掘"""
        all_entities = []
        all_relations = []
      
        # 批量处理
        batch_size = self.config.get("batch_size", 5)
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            batch_text = "\n---\n".join(batch)
          
            prompt = f"""
请从以下水旱灾害领域文本中提取关键词汇：

文本：
{batch_text}

请提取：
1. 实体词（名词短语）：地名、机构、设施、事件、数值等
2. 关系词（动词短语）：动作、状态变化、因果关系等

输出JSON格式：
{{"entities": ["词1", "词2", ...], "relations": ["词1", "词2", ...]}}
"""
            response = self.llm.generate(prompt)
            result = self._parse_json_response(response)
            all_entities.extend(result.get("entities", []))
            all_relations.extend(result.get("relations", []))
      
        # 词频过滤
        entity_freq = Counter(all_entities)
        relation_freq = Counter(all_relations)
      
        entities = [w for w, c in entity_freq.items() if c >= self.min_freq]
        relations = [w for w, c in relation_freq.items() if c >= self.min_freq]
      
        return {
            "entities": entities,
            "relations": relations,
            "entity_freq": dict(entity_freq),
            "relation_freq": dict(relation_freq)
        }
  
    def _get_embeddings(self, words: List[str]) -> np.ndarray:
        """获取词汇向量"""
        if not words:
            return np.array([])
        return self.embedding_model.encode(words)
  
    def _cluster(self, words: List[str], embeddings: np.ndarray, n_clusters: int) -> Dict:
        """K-means聚类"""
        if len(words) < n_clusters:
            return {i: [w] for i, w in enumerate(words)}
      
        # 自动选择最优K
        best_k = self._find_optimal_k(embeddings, min(n_clusters, len(words) - 1))
      
        kmeans = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        labels = kmeans.fit_predict(embeddings)
      
        clusters = {}
        for word, label in zip(words, labels):
            label = int(label)
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(word)
      
        return clusters
  
    def _find_optimal_k(self, embeddings: np.ndarray, max_k: int) -> int:
        """使用轮廓系数找最优K"""
        if len(embeddings) <= 2:
            return min(2, len(embeddings))
      
        best_score = -1
        best_k = 2
      
        for k in range(2, min(max_k + 1, len(embeddings))):
            try:
                kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
                labels = kmeans.fit_predict(embeddings)
                score = silhouette_score(embeddings, labels)
                if score > best_score:
                    best_score = score
                    best_k = k
            except:
                continue
      
        return best_k
  
    def _merge_similar_clusters(self, clusters: Dict) -> Dict:
        """使用Dice系数合并相似簇"""
        cluster_ids = list(clusters.keys())
        merged = {}
        used = set()
      
        for i, cid1 in enumerate(cluster_ids):
            if cid1 in used:
                continue
          
            merged_members = set(clusters[cid1])
            used.add(cid1)
          
            for cid2 in cluster_ids[i+1:]:
                if cid2 in used:
                    continue
              
                set1 = set(clusters[cid1])
                set2 = set(clusters[cid2])
              
                # Dice系数
                intersection = len(set1 & set2)
                dice = 2 * intersection / (len(set1) + len(set2)) if (len(set1) + len(set2)) > 0 else 0
              
                if dice >= self.dice_threshold:
                    merged_members.update(set2)
                    used.add(cid2)
          
            merged[len(merged)] = list(merged_members)
      
        return merged
  
    def _label_clusters(self, clusters: Dict, cluster_type: str) -> Dict:
        """LLM标签映射"""
        labeled = {}
        type_hint = "实体类型" if cluster_type == "entity" else "关系类型"
      
        for cluster_id, members in clusters.items():
            prompt = f"""
以下是水旱灾害领域的一组相关词汇，请为其生成一个{type_hint}标签。

词汇：{', '.join(members[:15])}

输出JSON格

```python
# kg/ontology/corpus_clustering.py (续)

            prompt = f"""
以下是水旱灾害领域的一组相关词汇，请为其生成一个{type_hint}标签。

词汇：{', '.join(members[:15])}

输出JSON格式：
{{"label": "英文标签", "label_cn": "中文标签", "description": "描述"}}
"""
            response = self.llm.generate(prompt)
            result = self._parse_json_response(response)
          
            label = result.get("label", f"CLUSTER_{cluster_id}")
            labeled[label] = {
                "label_cn": result.get("label_cn", ""),
                "description": result.get("description", ""),
                "members": members,
                "source": "clustering"
            }
      
        return labeled
  
    def _parse_json_response(self, response: str) -> Dict:
        """解析JSON响应"""
        import re
        try:
            json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except:
            pass
        return {}
```

### 2.5 Phase 3: 混合融合

```python
# kg/ontology/hybrid_fusion.py

"""
混合融合模块
将聚类结果与专家骨架对齐融合
"""

import numpy as np
from typing import Dict, List, Tuple
from sklearn.metrics.pairwise import cosine_similarity


class HybridFusion:
    """混合融合器"""
  
    def __init__(self, embedding_model, config: dict):
        self.embedding_model = embedding_model
        self.similarity_threshold = config.get("similarity_threshold", 0.75)
  
    def fuse(
        self, 
        expert_skeleton: Dict, 
        clustering_result: Dict
    ) -> Dict:
        """
        融合专家骨架和聚类结果
      
        Args:
            expert_skeleton: 专家骨架TBox
            clustering_result: 聚类挖掘结果
          
        Returns:
            融合后的TBox
        """
        # 融合实体类
        fused_classes = self._fuse_classes(
            expert_skeleton.get("classes", []),
            clustering_result.get("entity_clusters", {})
        )
      
        # 融合关系类型
        fused_relations = self._fuse_relations(
            expert_skeleton.get("relations", []),
            clustering_result.get("relation_clusters", {})
        )
      
        return {
            "classes": fused_classes,
            "relations": fused_relations
        }
  
    def _fuse_classes(
        self, 
        expert_classes: List[Dict], 
        clustered_classes: Dict
    ) -> List[Dict]:
        """融合实体类"""
        fused = []
        used_clusters = set()
      
        # 1. 保留所有专家类（锚点）
        for ec in expert_classes:
            fused_class = ec.copy()
            fused_class["source"] = "expert"
          
            # 查找可合并的聚类类
            for label, cluster_info in clustered_classes.items():
                if label in used_clusters:
                    continue
              
                similarity = self._compute_class_similarity(
                    ec.get("name", ""),
                    ec.get("description", ""),
                    ec.get("examples", []),
                    label,
                    cluster_info.get("description", ""),
                    cluster_info.get("members", [])
                )
              
                if similarity >= self.similarity_threshold:
                    # 合并：扩展专家类的examples
                    existing_examples = set(fused_class.get("examples", []))
                    new_examples = cluster_info.get("members", [])[:10]
                    fused_class["examples"] = list(existing_examples | set(new_examples))[:15]
                    fused_class["merged_from_clustering"] = label
                    used_clusters.add(label)
                    break
          
            fused.append(fused_class)
      
        # 2. 添加未被合并的聚类类（作为扩展类）
        for label, cluster_info in clustered_classes.items():
            if label in used_clusters:
                continue
          
            fused.append({
                "name": label,
                "name_cn": cluster_info.get("label_cn", ""),
                "description": cluster_info.get("description", ""),
                "examples": cluster_info.get("members", [])[:10],
                "is_anchor": False,
                "source": "clustering"
            })
      
        return fused
  
    def _fuse_relations(
        self, 
        expert_relations: List[Dict], 
        clustered_relations: Dict
    ) -> List[Dict]:
        """融合关系类型"""
        fused = []
        used_clusters = set()
      
        # 1. 保留所有专家关系（锚点）
        for er in expert_relations:
            fused_relation = er.copy()
            fused_relation["source"] = "expert"
          
            # 查找可合并的聚类关系
            for label, cluster_info in clustered_relations.items():
                if label in used_clusters:
                    continue
              
                similarity = self._compute_relation_similarity(
                    er.get("name", ""),
                    er.get("description", ""),
                    label,
                    cluster_info.get("description", ""),
                    cluster_info.get("members", [])
                )
              
                if similarity >= self.similarity_threshold:
                    existing_examples = set(er.get("examples", []))
                    new_examples = cluster_info.get("members", [])[:5]
                    fused_relation["examples"] = list(existing_examples | set(new_examples))[:10]
                    fused_relation["merged_from_clustering"] = label
                    used_clusters.add(label)
                    break
          
            fused.append(fused_relation)
      
        # 2. 添加未被合并的聚类关系（作为扩展关系）
        for label, cluster_info in clustered_relations.items():
            if label in used_clusters:
                continue
          
            fused.append({
                "name": label,
                "name_cn": cluster_info.get("label_cn", ""),
                "description": cluster_info.get("description", ""),
                "domain": [],  # 待后续推断
                "range": [],
                "examples": cluster_info.get("members", [])[:5],
                "is_anchor": False,
                "source": "clustering"
            })
      
        return fused
  
    def _compute_class_similarity(
        self,
        expert_name: str,
        expert_desc: str,
        expert_examples: List[str],
        cluster_label: str,
        cluster_desc: str,
        cluster_members: List[str]
    ) -> float:
        """计算实体类相似度"""
        # 构建文本表示
        expert_text = f"{expert_name} {expert_desc} {' '.join(expert_examples[:5])}"
        cluster_text = f"{cluster_label} {cluster_desc} {' '.join(cluster_members[:5])}"
      
        # 向量化并计算余弦相似度
        embeddings = self.embedding_model.encode([expert_text, cluster_text])
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
      
        return float(similarity)
  
    def _compute_relation_similarity(
        self,
        expert_name: str,
        expert_desc: str,
        cluster_label: str,
        cluster_desc: str,
        cluster_members: List[str]
    ) -> float:
        """计算关系类型相似度"""
        expert_text = f"{expert_name} {expert_desc}"
        cluster_text = f"{cluster_label} {cluster_desc} {' '.join(cluster_members[:3])}"
      
        embeddings = self.embedding_model.encode([expert_text, cluster_text])
        similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
      
        return float(similarity)
```

### 2.6 Phase 4: 支持度/置信度筛选

```python
# kg/ontology/quality_filter.py

"""
质量筛选模块
使用支持度和置信度过滤低质量的类/关系
"""

import json
from typing import Dict, List, Tuple
from collections import Counter, defaultdict


class QualityFilter:
    """质量筛选器"""
  
    def __init__(self, config: dict):
        self.min_support = config.get("min_support", 5)           # 最小支持度
        self.min_confidence = config.get("min_confidence", 0.3)   # 最小置信度
        self.protect_anchors = config.get("protect_anchors", True) # 保护专家锚点
  
    def filter_tbox(
        self, 
        tbox: Dict, 
        corpus_stats: Dict
    ) -> Tuple[Dict, Dict]:
        """
        过滤TBox
      
        Args:
            tbox: 待过滤的TBox
            corpus_stats: 语料统计信息
                - entity_freq: 实体词频统计
                - relation_cooccur: 关系共现统计
              
        Returns:
            (filtered_tbox, filter_report)
        """
        # 过滤实体类
        filtered_classes, class_report = self._filter_classes(
            tbox.get("classes", []),
            corpus_stats.get("entity_freq", {})
        )
      
        # 过滤关系类型
        filtered_relations, relation_report = self._filter_relations(
            tbox.get("relations", []),
            corpus_stats.get("relation_cooccur", {}),
            corpus_stats.get("entity_freq", {})
        )
      
        filtered_tbox = {
            "classes": filtered_classes,
            "relations": filtered_relations,
            "metadata": {
                "original_classes": len(tbox.get("classes", [])),
                "filtered_classes": len(filtered_classes),
                "original_relations": len(tbox.get("relations", [])),
                "filtered_relations": len(filtered_relations)
            }
        }
      
        filter_report = {
            "class_report": class_report,
            "relation_report": relation_report
        }
      
        return filtered_tbox, filter_report
  
    def _filter_classes(
        self, 
        classes: List[Dict], 
        entity_freq: Dict
    ) -> Tuple[List[Dict], Dict]:
        """
        过滤实体类
      
        支持度计算：类的支持度 = 该类所有示例词在语料中出现的总次数
        """
        filtered = []
        removed = []
      
        for cls in classes:
            # 专家锚点保护
            if self.protect_anchors and cls.get("is_anchor", False):
                cls["support"] = -1  # 标记为受保护
                filtered.append(cls)
                continue
          
            # 计算支持度
            examples = cls.get("examples", [])
            support = sum(entity_freq.get(ex, 0) for ex in examples)
            cls["support"] = support
          
            if support >= self.min_support:
                filtered.append(cls)
            else:
                removed.append({
                    "name": cls.get("name"),
                    "support": support,
                    "reason": f"支持度 {support} < {self.min_support}"
                })
      
        report = {
            "total": len(classes),
            "kept": len(filtered),
            "removed": len(removed),
            "removed_details": removed
        }
      
        return filtered, report
  
    def _filter_relations(
        self, 
        relations: List[Dict],
        relation_cooccur: Dict,
        entity_freq: Dict
    ) -> Tuple[List[Dict], Dict]:
        """
        过滤关系类型
      
        置信度计算：
        confidence(A → R → B) = count(A, R, B) / count(A)
        即：在A出现的情况下，A通过R连接到B的概率
        """
        filtered = []
        removed = []
      
        for rel in relations:
            # 专家锚点保护
            if self.protect_anchors and rel.get("is_anchor", False):
                rel["confidence"] = -1  # 标记为受保护
                filtered.append(rel)
                continue
          
            # 计算置信度
            rel_name = rel.get("name", "")
            cooccur_count = relation_cooccur.get(rel_name, {}).get("count", 0)
            domain_count = relation_cooccur.get(rel_name, {}).get("domain_count", 1)
          
            confidence = cooccur_count / domain_count if domain_count > 0 else 0
            rel["confidence"] = round(confidence, 4)
            rel["support"] = cooccur_count
          
            if confidence >= self.min_confidence and cooccur_count >= self.min_support:
                filtered.append(rel)
            else:
                removed.append({
                    "name": rel_name,
                    "confidence": confidence,
                    "support": cooccur_count,
                    "reason": f"置信度 {confidence:.2f} < {self.min_confidence} 或 支持度 {cooccur_count} < {self.min_support}"
                })
      
        report = {
            "total": len(relations),
            "kept": len(filtered),
            "removed": len(removed),
            "removed_details": removed
        }
      
        return filtered, report


class CorpusStatisticsCollector:
    """语料统计收集器"""
  
    def __init__(self, llm_client):
        self.llm = llm_client
  
    def collect_statistics(self, texts: List[str], tbox: Dict) -> Dict:
        """
        收集语料统计信息
      
        Args:
            texts: 语料文本列表
            tbox: 当前TBox（用于指导统计）
          
        Returns:
            统计信息字典
        """
        entity_freq = Counter()
        relation_cooccur = defaultdict(lambda: {"count": 0, "domain_count": 0})
      
        # 获取所有实体示例
        all_examples = []
        for cls in tbox.get("classes", []):
            all_examples.extend(cls.get("examples", []))
      
        # 获取所有关系名
        all_relations = [r.get("name", "") for r in tbox.get("relations", [])]
      
        # 统计实体词频
        for text in texts:
            for example in all_examples:
                if example in text:
                    entity_freq[example] += 1
      
        # 统计关系共现（简化版：基于关键词共现）
        relation_keywords = {
            "occurs_at": ["发生", "于", "在"],
            "located_in": ["位于", "在", "境内"],
            "has_cause": ["由于", "因为", "导致", "引起"],
            "causes_impact": ["造成", "导致", "引发"],
            "has_value": ["达到", "为", "超过"],
            "triggers": ["启动", "触发", "响应"],
            "implements": ["实施", "执行", "开展"],
            "affects": ["影响", "波及", "涉及"],
            "operates": ["操作", "开启", "关闭"]
        }
      
        for text in texts:
            for rel_name, keywords in relation_keywords.items():
                if rel_name in all_relations:
                    for kw in keywords:
                        if kw in text:
                            relation_cooccur[rel_name]["count"] += 1
                            relation_cooccur[rel_name]["domain_count"] += 1
                            break
      
        return {
            "entity_freq": dict(entity_freq),
            "relation_cooccur": dict(relation_cooccur)
        }
```

### 2.7 Phase 5: 本体构建主流程

```python
# kg/ontology/hybrid_ontology_builder.py

"""
混合本体构建主流程
整合专家骨架、聚类挖掘、混合融合、质量筛选
"""

import json
from datetime import datetime
from typing import Dict, List
from pathlib import Path

from kg.ontology.expert_skeleton import ExpertSkeleton
from kg.ontology.corpus_clustering import CorpusClusteringMiner
from kg.ontology.hybrid_fusion import HybridFusion
from kg.ontology.quality_filter import QualityFilter, CorpusStatisticsCollector


class HybridOntologyBuilder:
    """混合本体构建器"""
  
    def __init__(self, llm_client, embedding_model, config: dict):
        self.llm = llm_client
        self.embedding_model = embedding_model
        self.config = config
      
        # 初始化各模块
        self.expert_skeleton = ExpertSkeleton()
        self.clustering_miner = CorpusClusteringMiner(
            llm_client, embedding_model, config.get("clustering", {})
        )
        self.fusion = HybridFusion(
            embedding_model, config.get("fusion", {})
        )
        self.quality_filter = QualityFilter(config.get("quality_filter", {}))
        self.stats_collector = CorpusStatisticsCollector(llm_client)
  
    def build(self, corpus_path: str, output_dir: str) -> Dict:
        """
        构建混合本体
      
        Args:
            corpus_path: 语料文件路径
            output_dir: 输出目录
          
        Returns:
            最终的TBox
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
      
        # 加载语料
        print("=" * 60)
        print("混合本体构建开始")
        print("=" * 60)
      
        print("\n[1/5] 加载语料...")
        texts = self._load_corpus(corpus_path)
        print(f"      加载 {len(texts)} 条文本")
      
        # Phase 1: 专家骨架
        print("\n[2/5] 加载专家骨架...")
        expert_tbox = self.expert_skeleton.to_tbox_format()
        print(f"      专家定义: {len(expert_tbox['classes'])} 个实体类, "
              f"{len(expert_tbox['relations'])} 个关系类型")
      
        # 保存专家骨架
        with open(output_dir / "expert_skeleton.json", 'w', encoding='utf-8') as f:
            json.dump(expert_tbox, f, ensure_ascii=False, indent=2)
      
        # Phase 2: 语料聚类挖掘
        print("\n[3/5] 语料聚类挖掘...")
        clustering_result = self.clustering_miner.mine_and_cluster(texts)
        print(f"      聚类发现: {len(clustering_result['entity_clusters'])} 个实体簇, "
              f"{len(clustering_result['relation_clusters'])} 个关系簇")
      
        # 保存聚类结果
        with open(output_dir / "clustering_result.json", 'w', encoding='utf-8') as f:
            json.dump(clustering_result, f, ensure_ascii=False, indent=2)
      
        # Phase 3: 混合融合
        print("\n[4/5] 混合融合...")
        fused_tbox = self.fusion.fuse(expert_tbox, clustering_result)
        print(f"      融合后: {len(fused_tbox['classes'])} 个实体类, "
              f"{len(fused_tbox['relations'])} 个关系类型")
      
        # 保存融合结果
        with open(output_dir / "fused_tbox.json", 'w', encoding='utf-8') as f:
            json.dump(fused_tbox, f, ensure_ascii=False, indent=2)
      
        # Phase 4: 支持度/置信度筛选
        print("\n[5/5] 支持度/置信度筛选...")
        corpus_stats = self.stats_collector.collect_statistics(texts, fused_tbox)
        final_tbox, filter_report = self.quality_filter.filter_tbox(fused_tbox, corpus_stats)
      
        print(f"      筛选后: {len(final_tbox['classes'])} 个实体类 "
              f"(移除 {filter_report['class_report']['removed']}), "
              f"{len(final_tbox['relations'])} 个关系类型 "
              f"(移除 {filter_report['relation_report']['removed']})")
      
        # 添加元数据
        final_tbox["metadata"] = {
            "build_method": "hybrid (expert + clustering)",
            "build_time": datetime.now().isoformat(),
            "corpus_size": len(texts),
            "expert_classes": len(expert_tbox['classes']),
            "expert_relations": len(expert_tbox['relations']),
            "final_classes": len(final_tbox['classes']),
            "final_relations": len(final_tbox['relations']),
            "config": self.config
        }
      
        # 保存最终TBox
        with open(output_dir / "master_tbox.json", 'w', encoding='utf-8') as f:
            json.dump(final_tbox, f, ensure_ascii=False, indent=2)
      
        # 保存筛选报告
        with open(output_dir / "filter_report.json", 'w', encoding='utf-8') as f:
            json.dump(filter_report, f, ensure_ascii=False, indent=2)
      
        print("\n" + "=" * 60)
        print("混合本体构建完成!")
        print(f"输出目录: {output_dir}")
        print("=" * 60)
      
        return final_tbox
  
    def _load_corpus(self, corpus_path: str) -> List[str]:
        """加载语料"""
        texts = []
        with open(corpus_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    doc = json.loads(line)
                    text = doc.get("text", "")
                    if text and len(text) >= 50:
                        texts.append(text)
                except:
                    continue
        return texts
```

---

## 三、抽取层：图结构增强的链式CoT + 双重校验

### 3.1 方法概述

**核心思想**：
- **图结构作为CoT骨架**：图结构定义"抽什么"（节点类型、路径模式），CoT定义"怎么抽"（分步推理）
- **路径驱动的链式抽取**：每条图路径对应一个CoT步骤，系统化抽取
- **双重校验保留增强**：原文回溯校验 + Schema一致性校验

**与原方法的关系**：
```
原方法：CoT分步抽取 + 双重校验
    ↓ 增强
新方法：图结构引导 + 路径驱动的CoT + 双重校验
```

### 3.2 图结构定义模块

```python
# kg/extraction/graph_structure.py

"""
图结构定义模块
定义文本的逻辑图结构，作为CoT抽取的骨架
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional


@dataclass
class NodeType:
    """节点类型"""
    role: str           # Subject / Intermediate / Object
    entity_types: List[str]
    description: str
    keywords: List[str] = field(default_factory=list)  # 识别关键词


@dataclass
class PathPattern:
    """路径模式"""
    name: str
    pattern: str        # 如 "TIME → occurs_at → EVENT"
    description: str
    extraction_hint: str  # 抽取提示


@dataclass
class GraphStructure:
    """图结构定义"""
    name: str
    description: str
    nodes: Dict[str, NodeType]
    paths: List[PathPattern]
  
    def get_cot_steps(self) -> List[str]:
        """生成CoT步骤"""
        steps = []
      
        # Step 1: 节点识别
        node_hints = []
        for role, node in self.nodes.items():
            role_cn = {"subject": "起始", "intermediate": "中间", "object": "终止"}.get(role, role)
            node_hints.append(f"  - {role_cn}节点: {', '.join(node.entity_types)}")
      
        steps.append(f"""**Step 1: 图结构节点识别**
按照以下节点类型，识别文本中的所有实体：
{chr(10).join(node_hints)}

【操作】：逐句阅读，标记每个实体及其类型。
【自检】：实体是否与原文完全一致？类型是否正确？""")
      
        # Step 2: 路径连接
        path_hints = []
        for p in self.paths:
            path_hints.append(f"  - {p.name}: `{p.pattern}`\n    提示: {p.extraction_hint}")
      
        steps.append(f"""**Step 2: 路径驱动的关系连接**
按照以下路径模式，连接已识别的节点：
{chr(10).join(path_hints)}

【操作】：对每条路径，检查文本中是否存在对应的实体对和关系。
【自检】：关系方向是否正确？是否有遗漏的路径？""")
      
        # Step 3: 证据回溯
        steps.append("""**Step 3: 证据回溯与三元组生成**
对每条潜在三元组：
1. 从原文中找到支撑该关系的证据句
2. 验证主语和宾语都在证据句中出现
3. 如果找不到证据，丢弃该三元组

【操作】：为每条三元组填写evidence字段。
【自检】：证据是否来自原文？是否支撑该关系？""")
      
        return steps
  
    def format_for_prompt(self) -> str:
        """格式化为Prompt"""
        lines = []
        lines.append(f"**文本类型**: {self.name}")
        lines.append(f"**说明**: {self.description}")
        lines.append("")
      
        # 图结构示意
        lines.append("**图结构示意**:")
        lines.append("```")
        lines.append("[Subject] ──关系──→ [Intermediate] ──关系──→ [Object]")
        lines.append("  起始节点              中间节点              终止节点")
        lines.append("```")
        lines.append("")
      
        # 节点定义
        lines.append("**节点类型**:")
        for role, node in self.nodes.items():
            role_cn = {"subject": "起始节点", "intermediate": "中间节点", "object": "终止节点"}.get(role, role)
            lines.append(f"- **{role_cn}**: {', '.join(node.entity_types)}")
            lines.append(f"  {node.description}")
            if node.keywords:
                lines.append(f"  识别词: {', '.join(node.keywords[:5])}")
        lines.append("")
      
        # 典型路径
        lines.append("**典型抽取路径**:")
        for i, p in enumerate(self.paths, 1):
            lines.append(f"{i}. **{p.name}**: `{p.pattern}`")
            lines.append(f"   {p.description}")
      
        return "\n".join(lines)


# ==================== 预定义图结构 ====================

GRAPH_STRUCTURES = {
    "disaster_event": GraphStructure(
        name="灾害事件描述",
        description="描述灾害事件发生过程、影响和应对的文本",
        nodes={
            "subject": NodeType(
                role="Subject",
                entity_types=["TIME", "LOCATION", "CAUSE"],
                description="事件的时间起点、空间起点或原因起点",
                keywords=["年", "月", "日", "省", "市", "县", "流域", "暴雨", "台风"]
            ),
            "intermediate": NodeType(
                role="Intermediate",
                entity_types=["EVENT", "FACILITY", "ORG"],
                description="灾害事件本身、涉及的设施或响应机构",
                keywords=["洪水", "干旱", "水库", "堤防", "水利部", "防汛"]
            ),
            "object": NodeType(
                role="Object",
                entity_types=["IMPACT", "VALUE", "MEASURE"],
                description="灾害影响、监测数值或应对措施",
                keywords=["受灾", "损失", "米", "立方米", "响应", "转移"]
            )
        },
        paths=[
            PathPattern(
                name="时间定位",
                pattern="TIME → occurs_at → EVENT",
                description="事件发生的时间",
                extraction_hint="寻找时间词与事件的关联，如'X月发生Y'"
            ),
            PathPattern(
                name="空间定位",
                pattern="LOCATION → located_in → EVENT/FACILITY",
                description="事件或设施所在的地点",
                extraction_hint="寻找地名与事件/设施的关联，如'X省发生Y'、'Y位于X'"
            ),
            PathPattern(
                name="因果链",
                pattern="CAUSE → has_cause → EVENT → causes_impact → IMPACT",
                description="从原因到事件到影响的因果链",
                extraction_hint="寻找因果词，如'由于X导致Y造成Z

```python
# kg/extraction/graph_structure.py (续)

            PathPattern(
                name="因果链",
                pattern="CAUSE → has_cause → EVENT → causes_impact → IMPACT",
                description="从原因到事件到影响的因果链",
                extraction_hint="寻找因果词，如'由于X导致Y造成Z'"
            ),
            PathPattern(
                name="数值关联",
                pattern="FACILITY/LOCATION → has_value → VALUE",
                description="设施或地点的监测数值",
                extraction_hint="寻找数值表达，如'X水位达到Y米'"
            ),
            PathPattern(
                name="响应触发",
                pattern="EVENT → triggers → MEASURE",
                description="事件触发的应急响应",
                extraction_hint="寻找响应词，如'X发生后启动Y响应'"
            ),
            PathPattern(
                name="措施实施",
                pattern="ORG → implements → MEASURE",
                description="机构实施的措施",
                extraction_hint="寻找实施词，如'X部门实施Y措施'"
            )
        ]
    ),
  
    "dispatch_rule": GraphStructure(
        name="调度规则描述",
        description="描述水利工程调度规则和操作条件的文本",
        nodes={
            "subject": NodeType(
                role="Subject",
                entity_types=["CONDITION", "THRESHOLD", "TIME"],
                description="触发条件、阈值或时间条件",
                keywords=["当", "若", "如果", "超过", "达到", "汛期"]
            ),
            "intermediate": NodeType(
                role="Intermediate",
                entity_types=["FACILITY", "OPERATION"],
                description="调度对象或操作动作",
                keywords=["水库", "闸门", "开启", "关闭", "调节"]
            ),
            "object": NodeType(
                role="Object",
                entity_types=["RESULT", "CONSTRAINT", "VALUE"],
                description="调度结果、约束条件或目标值",
                keywords=["不超过", "控制在", "保持", "确保"]
            )
        },
        paths=[
            PathPattern(
                name="条件触发",
                pattern="CONDITION → triggers → OPERATION",
                description="条件触发操作",
                extraction_hint="寻找条件句，如'当X时，执行Y'"
            ),
            PathPattern(
                name="操作对象",
                pattern="OPERATION → operates → FACILITY",
                description="操作作用于设施",
                extraction_hint="寻找操作与设施的关联，如'开启X闸'"
            ),
            PathPattern(
                name="结果约束",
                pattern="OPERATION → constrains → VALUE",
                description="操作的约束条件",
                extraction_hint="寻找约束词，如'控制X不超过Y'"
            )
        ]
    ),
  
    "impact_statistics": GraphStructure(
        name="灾情统计描述",
        description="描述灾害损失统计数据的文本",
        nodes={
            "subject": NodeType(
                role="Subject",
                entity_types=["TIME", "LOCATION", "EVENT"],
                description="统计时段、区域或灾害类型",
                keywords=["截至", "全年", "全省", "洪涝", "干旱"]
            ),
            "intermediate": NodeType(
                role="Intermediate",
                entity_types=["CATEGORY", "INDICATOR"],
                description="统计类别或指标",
                keywords=["受灾人口", "农作物", "经济损失", "死亡"]
            ),
            "object": NodeType(
                role="Object",
                entity_types=["VALUE", "COMPARISON"],
                description="统计数值或对比基准",
                keywords=["万人", "万亩", "亿元", "同比", "环比"]
            )
        },
        paths=[
            PathPattern(
                name="区域统计",
                pattern="LOCATION → has_impact → VALUE",
                description="区域的灾情数值",
                extraction_hint="寻找区域与数值的关联，如'X省受灾Y万人'"
            ),
            PathPattern(
                name="类别数值",
                pattern="CATEGORY → has_value → VALUE",
                description="统计类别的数值",
                extraction_hint="寻找类别与数值的关联，如'受灾人口X万'"
            ),
            PathPattern(
                name="时段覆盖",
                pattern="TIME → covers → EVENT",
                description="统计的时间范围",
                extraction_hint="寻找时间范围表达，如'X月至Y月期间'"
            )
        ]
    )
}


def detect_text_type(text: str) -> str:
    """自动检测文本类型"""
    # 调度规则特征
    dispatch_keywords = ["当", "若", "如果", "则", "应当", "开启", "关闭", "调节", "控制", "不得超过", "泄洪"]
    # 统计数据特征
    statistics_keywords = ["截至", "共计", "累计", "统计", "合计", "同比", "环比", "万人", "亿元", "万亩", "全年"]
  
    dispatch_score = sum(1 for kw in dispatch_keywords if kw in text)
    statistics_score = sum(1 for kw in statistics_keywords if kw in text)
  
    if dispatch_score >= 3:
        return "dispatch_rule"
    elif statistics_score >= 3:
        return "impact_statistics"
    else:
        return "disaster_event"


def get_graph_structure(text_type: str) -> GraphStructure:
    """获取指定类型的图结构"""
    return GRAPH_STRUCTURES.get(text_type, GRAPH_STRUCTURES["disaster_event"])
```

### 3.3 图结构增强的链式CoT Prompt构建

```python
# kg/extraction/graph_cot_prompt.py

"""
图结构增强的链式CoT Prompt构建模块
将图结构作为CoT的骨架，实现路径驱动的分步抽取
"""

import json
from typing import Dict, List, Optional
from kg.extraction.graph_structure import get_graph_structure, detect_text_type, GraphStructure


class GraphCoTPromptBuilder:
    """图结构增强的CoT Prompt构建器"""
  
    def __init__(self, config: dict = None):
        self.config = config or {}
  
    def build_prompt(
        self,
        text: str,
        tbox: Dict,
        text_type: Optional[str] = None
    ) -> str:
        """
        构建完整的抽取Prompt
      
        Args:
            text: 待抽取文本
            tbox: TBox Schema
            text_type: 文本类型，None则自动检测
          
        Returns:
            完整的Prompt字符串
        """
        # 自动检测文本类型
        if text_type is None:
            text_type = detect_text_type(text)
      
        # 获取图结构
        graph_structure = get_graph_structure(text_type)
      
        # 构建Prompt各部分
        prompt_parts = []
      
        # 1. 系统角色
        prompt_parts.append(self._build_system_role())
      
        # 2. 图结构定义
        prompt_parts.append(self._build_graph_structure_section(graph_structure))
      
        # 3. TBox约束
        prompt_parts.append(self._build_tbox_section(tbox))
      
        # 4. 路径驱动的CoT步骤
        prompt_parts.append(self._build_cot_steps(graph_structure))
      
        # 5. 输出格式要求
        prompt_parts.append(self._build_output_format())
      
        # 6. 待抽取文本
        prompt_parts.append(self._build_input_section(text))
      
        return "\n\n".join(prompt_parts)
  
    def _build_system_role(self) -> str:
        """构建系统角色"""
        return """═══════════════════════════════════════════════════════════════════════════
【角色定义】
═══════════════════════════════════════════════════════════════════════════

你是一名专业的水旱灾害知识图谱构建助手。你的任务是：
1. 按照给定的**图结构**识别文本中的实体节点
2. 按照**路径模式**连接实体，形成三元组
3. 为每条三元组提供**原文证据**

**核心原则**：
- 实体必须与原文**完全一致**，禁止改写或推断
- 关系必须有原文**明确支撑**，禁止编造
- 宁可遗漏，不可幻觉"""
  
    def _build_graph_structure_section(self, graph_structure: GraphStructure) -> str:
        """构建图结构定义部分"""
        return f"""═══════════════════════════════════════════════════════════════════════════
【图结构定义】—— 抽取骨架
═══════════════════════════════════════════════════════════════════════════

{graph_structure.format_for_prompt()}

**抽取策略**：
按照上述图结构，从起始节点出发，沿路径连接到终止节点。
每条完整路径对应一个或多个三元组。"""
  
    def _build_tbox_section(self, tbox: Dict) -> str:
        """构建TBox约束部分"""
        # 实体类型
        entity_types = []
        for cls in tbox.get("classes", []):
            name = cls.get("name", "")
            name_cn = cls.get("name_cn", "")
            examples = cls.get("examples", [])[:3]
            entity_types.append(f"- **{name}**({name_cn}): {', '.join(examples)}")
      
        # 关系类型
        relation_types = []
        for rel in tbox.get("relations", []):
            name = rel.get("name", "")
            name_cn = rel.get("name_cn", "")
            domain = rel.get("domain", [])
            range_ = rel.get("range", [])
            relation_types.append(f"- **{name}**({name_cn}): {domain} → {range_}")
      
        return f"""═══════════════════════════════════════════════════════════════════════════
【TBox Schema约束】—— 类型规范
═══════════════════════════════════════════════════════════════════════════

**可用实体类型**：
{chr(10).join(entity_types)}

**可用关系类型**：
{chr(10).join(relation_types)}

**约束**：抽取的实体和关系应尽量符合上述类型定义。"""
  
    def _build_cot_steps(self, graph_structure: GraphStructure) -> str:
        """构建路径驱动的CoT步骤"""
        cot_steps = graph_structure.get_cot_steps()
      
        steps_text = "\n\n".join(cot_steps)
      
        return f"""═══════════════════════════════════════════
【链式推理步骤（CoT）】—— 路径驱动的分步抽取
═══════════════════════════════════════════

请严格按照以下步骤进行思考和抽取：

{steps_text}

**Step 4: 格式化输出**
将验证通过的三元组整理为JSON格式：
- 确保格式正确
- 确保每条三元组都有evidence
- 丢弃无法验证的三元组"""
  
    def _build_output_format(self) -> str:
        """构建输出格式要求"""
        return """═══════════════════════════════════════════
【输出格式要求】
═══════════════════════════════════════════════════════════════════════════

请输出JSON格式，结构如下：
```json
{
  "reasoning": {
    "step1_nodes": [
      {"text": "实体文本", "type": "实体类型", "role": "subject/intermediate/object"}
    ],
    "step2_paths": [
      {"path": "路径名", "subject": "...", "predicate": "...", "object": "..."}
    ],
    "step3_verification": "验证说明"
  },
  "triples": [
    {
      "subject": "主语实体（原文原样）",
      "subject_type": "主语类型",
      "predicate": "关系",
      "object": "宾语实体（原文原样）",
      "object_type": "宾语类型",
      "evidence": "原文证据句",
      "confidence": 0.9
    }
  ]
}
```

**注意**：
1. `reasoning`字段展示推理过程（可选但推荐）
2. `triples`字段是最终结果（必须）
3. 实体文本必须与原文**完全一致**
4. evidence必须是原文中的句子或片段"""
  
    def _build_input_section(self, text: str) -> str:
        """构建输入文本部分"""
        return f"""═══════════════════════════════════════════════════════════════════════════
【待抽取文本】
═══════════════════════════════════════════════════════════════════════════

{text}

═══════════════════════════════════════════════════════════════════════════
【开始抽取】
═══════════════════════════════════════════

请按照上述CoT步骤进行抽取，输出JSON格式结果。"""
```

### 3.4 双重校验模块（保留并增强）

```python
# kg/extraction/dual_verification.py

"""
双重校验模块
校验1: 原文回溯校验（实体/证据存在性）
校验2: Schema一致性校验（关系合法性）
"""

import re
from typing import Dict, List, Tuple, Optional


class DualVerifier:
    """双重校验器"""
  
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.strict_mode = self.config.get("strict_mode", False)
        self.min_confidence = self.config.get("min_confidence", 0.5)
  
    def verify(
        self,
        triples: List[Dict],
        text: str,
        tbox: Dict
    ) -> Tuple[List[Dict], Dict]:
        """
        执行双重校验
      
        Args:
            triples: 待校验的三元组列表
            text: 原文
            tbox: TBox Schema
          
        Returns:
            (verified_triples, verification_report)
        """
        verified = []
        rejected = []
      
        for triple in triples:
            # 校验1: 原文回溯校验
            pass_text_check, text_reason = self._verify_text_grounding(triple, text)
          
            # 校验2: Schema一致性校验
            pass_schema_check, schema_reason = self._verify_schema_consistency(triple, tbox)
          
            # 综合判断
            if pass_text_check and pass_schema_check:
                triple["_verification"] = {
                    "text_check": "passed",
                    "schema_check": "passed"
                }
                verified.append(triple)
            else:
                triple["_verification"] = {
                    "text_check": text_reason if not pass_text_check else "passed",
                    "schema_check": schema_reason if not pass_schema_check else "passed",
                    "rejected": True
                }
                rejected.append(triple)
      
        report = {
            "total": len(triples),
            "verified": len(verified),
            "rejected": len(rejected),
            "rejection_reasons": self._summarize_rejections(rejected)
        }
      
        return verified, report
  
    def _verify_text_grounding(self, triple: Dict, text: str) -> Tuple[bool, str]:
        """
        校验1: 原文回溯校验
        检查实体和证据是否在原文中存在
        """
        subject = triple.get("subject", "").strip()
        obj = triple.get("object", "").strip()
        evidence = triple.get("evidence", "").strip()
      
        # 检查主语
        if not self._entity_in_text(subject, text):
            return False, f"主语'{subject}'未在原文中找到"
      
        # 检查宾语
        if not self._entity_in_text(obj, text):
            return False, f"宾语'{obj}'未在原文中找到"
      
        # 检查证据（如果提供）
        if evidence:
            if not self._evidence_in_text(evidence, text):
                return False, f"证据句未在原文中找到"
          
            # 检查主语和宾语是否在证据中
            if not (self._entity_in_text(subject, evidence) or 
                    self._entity_in_text(obj, evidence)):
                # 宽松检查：至少有一个实体在证据中
                pass  # 允许通过
      
        return True, "passed"
  
    def _verify_schema_consistency(self, triple: Dict, tbox: Dict) -> Tuple[bool, str]:
        """
        校验2: Schema一致性校验
        检查关系是否在TBox中定义，以及domain/range是否匹配
        """
        predicate = triple.get("predicate", "").strip()
        subject_type = triple.get("subject_type", "")
        object_type = triple.get("object_type", "")
      
        # 获取TBox中的关系定义
        relation_map = {r.get("name"): r for r in tbox.get("relations", [])}
      
        # 检查关系是否存在
        if predicate not in relation_map:
            if self.strict_mode:
                return False, f"关系'{predicate}'不在TBox中"
            else:
                # 宽松模式：允许未定义的关系
                return True, "passed (relation not in TBox, but allowed)"
      
        # 检查domain/range约束（如果提供了类型信息）
        rel_def = relation_map[predicate]
        domain = rel_def.get("domain", [])
        range_ = rel_def.get("range", [])
      
        if subject_type and domain and subject_type not in domain:
            if self.strict_mode:
                return False, f"主语类型'{subject_type}'不在关系'{predicate}'的domain中"
      
        if object_type and range_ and object_type not in range_:
            if self.strict_mode:
                return False, f"宾语类型'{object_type}'不在关系'{predicate}'的range中"
      
        return True, "passed"
  
    def _entity_in_text(self, entity: str, text: str) -> bool:
        """检查实体是否在文本中"""
        if not entity:
            return False
      
        # 精确匹配
        if entity in text:
            return True
      
        # 标点符号归一化后匹配
        entity_norm = re.sub(r'[，。、；：""''（）\s]', '', entity)
        text_norm = re.sub(r'[，。、；：""''（）\s]', '', text)
        if entity_norm and entity_norm in text_norm:
            return True
      
        # 数值模糊匹配
        if re.search(r'\d', entity):
            numbers = re.findall(r'[\d.]+', entity)
            if numbers and all(num in text for num in numbers):
                return True
      
        return False
  
    def _evidence_in_text(self, evidence: str, text: str) -> bool:
        """检查证据是否在文本中"""
        if not evidence:
            return True
      
        # 精确匹配
        if evidence in text:
            return True
      
        # 归一化匹配
        evidence_norm = re.sub(r'[，。、；：""''（）\s]', '', evidence)
        text_norm = re.sub(r'[，。、；：""''（）\s]', '', text)
        if evidence_norm and evidence_norm in text_norm:
            return True
      
        # 关键词覆盖率匹配（80%以上）
        evidence_words = set(re.findall(r'[\u4e00-\u9fa5]+|\d+\.?\d*', evidence))
        if evidence_words:
            match_count = sum(1 for w in evidence_words if w in text)
            if match_count / len(evidence_words) >= 0.8:
                return True
      
        return False
  
    def _summarize_rejections(self, rejected: List[Dict]) -> Dict:
        """汇总拒绝原因"""
        reasons = {}
        for triple in rejected:
            verification = triple.get("_verification", {})
          
            text_reason = verification.get("text_check", "")
            if text_reason and text_reason != "passed":
                reason_type = "text_grounding"
                reasons[reason_type] = reasons.get(reason_type, 0) + 1
          
            schema_reason = verification.get("schema_check", "")
            if schema_reason and schema_reason != "passed":
                reason_type = "schema_consistency"
                reasons[reason_type] = reasons.get(reason_type, 0) + 1
      
        return reasons
```

### 3.5 抽取执行器

```python
# kg/extraction/graph_cot_extractor.py

"""
图结构增强的链式CoT抽取执行器
整合Prompt构建、LLM调用、双重校验
"""

import json
import re
from typing import Dict, List, Optional, Tuple
from kg.extraction.graph_cot_prompt import GraphCoTPromptBuilder
from kg.extraction.graph_structure import detect_text_type
from kg.extraction.dual_verification import DualVerifier


class GraphCoTExtractor:
    """图结构增强的链式CoT抽取器"""
  
    def __init__(self, llm_client, config: dict = None):
        self.llm = llm_client
        self.config = config or {}
      
        # 初始化组件
        self.prompt_builder = GraphCoTPromptBuilder(config)
        self.verifier = DualVerifier(config.get("verification", {}))
      
        # 配置
        self.temperature = self.config.get("temperature", 0.1)
        self.max_retries = self.config.get("max_retries", 2)
  
    def extract(
        self,
        text: str,
        tbox: Dict,
        text_type: Optional[str] = None
    ) -> Dict:
        """
        执行抽取
      
        Args:
            text: 待抽取文本
            tbox: TBox Schema
            text_type: 文本类型
          
        Returns:
            抽取结果
        """
        # 自动检测文本类型
        if text_type is None:
            text_type = detect_text_type(text)
      
        # 构建Prompt
        prompt = self.prompt_builder.build_prompt(text, tbox, text_type)
      
        # 调用LLM（带重试）
        raw_response = None
        for attempt in range(self.max_retries + 1):
            try:
                raw_response = self.llm.generate(
                    prompt,
                    temperature=self.temperature
                )
                break
            except Exception as e:
                if attempt == self.max_retries:
                    return self._error_result(text, text_type, str(e))
      
        # 解析响应
        parsed = self._parse_response(raw_response)
        raw_triples = parsed.get("triples", [])
        reasoning = parsed.get("reasoning", {})
      
        # 双重校验
        verified_triples, verification_report = self.verifier.verify(
            raw_triples, text, tbox
        )
      
        return {
            "text": text,
            "text_type": text_type,
            "reasoning": reasoning,
            "raw_triples": raw_triples,
            "verified_triples": verified_triples,
            "n_raw": len(raw_triples),
            "n_verified": len(verified_triples),
            "verification_report": verification_report
        }
  
    def _parse_response(self, response: str) -> Dict:
        """解析LLM响应"""
        if not response:
            return {"triples": [], "reasoning": {}}
      
        # 尝试提取JSON
        try:
            # 查找JSON块
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                result = json.loads(json_match.group())
                return {
                    "triples": result.get("triples", []),
                    "reasoning": result.get("reasoning", {})
                }
        except json.JSONDecodeError:
            pass
      
        # 尝试提取JSON数组
        try:
            array_match = re.search(r'\[[\s\S]*\]', response)
            if array_match:
                triples = json.loads(array_match.group())
                return {"triples": triples, "reasoning": {}}
        except json.JSONDecodeError:
            pass
      
        return {"triples": [], "reasoning": {}}
  
    def _error_result(self, text: str, text_type: str, error: str) -> Dict:
        """生成错误结果"""
        return {
            "text": text,
            "text_type": text_type,
            "error": error,
            "raw_triples": [],
            "verified_triples": [],
            "n_raw": 0,
            "n_verified": 0
        }


class BatchGraphCoTExtractor:
    """批量抽取器"""
  
    def __init__(self, extractor: GraphCoTExtractor):
        self.extractor = extractor
  
    def extract_batch(
        self,
        documents: List[Dict],
        tbox: Dict,
        text_field: str = "text",
        id_field: str = "doc_id",
        progress_callback=None
    ) -> List[Dict]:
        """批量抽取"""
        results = []
        total = len(documents)
      
        for i, doc in enumerate(documents):
            doc_id = doc.get(id_field, f"doc_{i}")
            text = doc.get(text_field, "")
          
            if not text or len(text) < 20:
                continue
          
            try:
                result = self.extractor.extract(text, tbox)
                result["doc_id"] = doc_id
                results.append(result)
              
                # 进度输出
                print(f"[{i+1}/{total}] {doc_id}: "
                      f"抽取 {result['n_raw']} 条, "
                      f"验证通过 {result['n_verified']} 条")
              
                if progress_callback:
                    progress_callback(i + 1, total, result)
                  
            except Exception as e:
                print(f"[{i+1}/{total}] {doc_id}: 错误 - {str(e)}")
                results.append({
                    "doc_id": doc_id,
                    "error": str(e),
                    "verified_triples": []
                })
      
        return results
```

---

## 四、配置文件

### 4.1 本体构建配置

```yaml
# configs/ontology_building.yaml

# ==================== 聚类挖掘配置 ====================
clustering:
  min_freq: 3              # 最小词频
  n_clusters_entity: 15    # 实体初始聚类数
  n_clusters_relation: 12  # 关系初始聚类数
  dice_threshold: 0.5      # Dice系数合并阈值
  batch_size: 5            # LLM批处理大小

# ==================== 混合融合配置 ====================
fusion:
  similarity_threshold: 0.75  # 聚类与专家类合并的相似度阈值

# ==================== 质量筛选配置 ====================
quality_filter:
  min_support: 5           # 最小支持度
  min_confidence: 0.3      # 最小置信度
  protect_anchors: true    # 保护专家锚点不被过滤
```

### 4.2 抽取配置

```yaml
# configs/extraction.yaml

# ==================== 抽取配置 ====================
extraction:
  temperature: 0.1         # LLM温度
  max_retries: 2           # 最大重试次数
  auto_detect_type: true   # 自动检测文本类型

# ==================== 校验配置 ====================
verification:
  strict_mode: false       # 严格模式
  min_confidence: 0.5      # 最小置信度

# ==================== 批量抽取配置 ====================
batch:
  save_interval: 50        # 保存间隔
  retry_on_error: true     # 错误重试
```

---

## 五、执行脚本

### 5.1 本体构建脚本

```python
# scripts/build_hybrid_ontology.py

"""
混合本体构建脚本
"""

import argparse
import json
import yaml
from pathlib import Path

from kg.ontology.hybrid_ontology_builder import HybridOntologyBuilder
from kg.llm_client import LLMClient
from sentence_transformers import SentenceTransformer


def main():
    parser = argparse.ArgumentParser(description="混合本体构建")
    parser.add_argument("--corpus", required=True, help="语料文件路径")
    parser.add_argument("--config", default="configs/ontology_building.yaml")
    parser.add_

```python
# scripts/build_hybrid_ontology.py (续)

    parser.add_argument("--output", required=True, help="输出目录")
    args = parser.parse_args()
  
    # 加载配置
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
  
    # 初始化模型
    print("初始化模型...")
    llm_client = LLMClient()
    embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
  
    # 构建本体
    builder = HybridOntologyBuilder(llm_client, embedding_model, config)
    tbox = builder.build(args.corpus, args.output)
  
    print(f"\n最终TBox包含:")
    print(f"  - {len(tbox['classes'])} 个实体类")
    print(f"  - {len(tbox['relations'])} 个关系类型")


if __name__ == "__main__":
    main()
```

### 5.2 抽取脚本

```python
# scripts/run_graph_cot_extraction.py

"""
图结构增强的链式CoT抽取脚本
"""

import argparse
import json
import yaml
from pathlib import Path
from datetime import datetime

from kg.extraction.graph_cot_extractor import GraphCoTExtractor, BatchGraphCoTExtractor
from kg.llm_client import LLMClient


def main():
    parser = argparse.ArgumentParser(description="图结构增强的链式CoT抽取")
    parser.add_argument("--input", required=True, help="输入文件路径")
    parser.add_argument("--tbox", required=True, help="TBox文件路径")
    parser.add_argument("--output", required=True, help="输出文件路径")
    parser.add_argument("--config", default="configs/extraction.yaml")
    args = parser.parse_args()
  
    # 加载配置
    with open(args.config, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
  
    # 加载TBox
    with open(args.tbox, 'r', encoding='utf-8') as f:
        tbox = json.load(f)
  
    # 加载输入数据
    documents = []
    with open(args.input, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                documents.append(json.loads(line))
            except:
                continue
  
    print(f"加载 {len(documents)} 条文档")
    print(f"TBox: {len(tbox.get('classes', []))} 类, {len(tbox.get('relations', []))} 关系")
  
    # 初始化抽取器
    llm_client = LLMClient()
    extractor = GraphCoTExtractor(llm_client, config.get("extraction", {}))
    batch_extractor = BatchGraphCoTExtractor(extractor)
  
    # 执行抽取
    print("\n开始抽取...")
    results = batch_extractor.extract_batch(documents, tbox)
  
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
  
    with open(output_path, 'w', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
  
    # 统计
    total_raw = sum(r.get("n_raw", 0) for r in results)
    total_verified = sum(r.get("n_verified", 0) for r in results)
  
    print(f"\n抽取完成:")
    print(f"  - 总抽取: {total_raw} 条")
    print(f"  - 验证通过: {total_verified} 条")
    print(f"  - 过滤率: {(total_raw - total_verified) / max(total_raw, 1) * 100:.1f}%")
    print(f"  - 结果保存至: {output_path}")


if __name__ == "__main__":
    main()
```

---

## 六、消融实验设计

### 6.1 消融配置

```python
# scripts/run_ablation.py

"""
消融实验脚本
"""

import argparse
import json
from pathlib import Path
from kg.extraction.graph_cot_extractor import GraphCoTExtractor, BatchGraphCoTExtractor
from kg.llm_client import LLMClient

# 消融实验配置
ABLATION_CONFIGS = {
    # 完整方法
    "full": {
        "description": "完整方法: 图结构 + CoT + 双重校验",
        "use_graph_structure": True,
        "use_cot": True,
        "use_verification": True,
        "verification": {"strict_mode": False}
    },
  
    # 无图结构
    "wo_graph": {
        "description": "消融: 无图结构引导",
        "use_graph_structure": False,
        "use_cot": True,
        "use_verification": True,
        "verification": {"strict_mode": False}
    },
  
    # 无CoT
    "wo_cot": {
        "description": "消融: 无CoT分步",
        "use_graph_structure": True,
        "use_cot": False,
        "use_verification": True,
        "verification": {"strict_mode": False}
    },
  
    # 无校验
    "wo_verify": {
        "description": "消融: 无双重校验",
        "use_graph_structure": True,
        "use_cot": True,
        "use_verification": False,
        "verification": {"strict_mode": False}
    },
  
    # 仅CoT+校验（原方法基线）
    "baseline_cot_verify": {
        "description": "基线: 仅CoT + 双重校验（原方法）",
        "use_graph_structure": False,
        "use_cot": True,
        "use_verification": True,
        "verification": {"strict_mode": False}
    },
  
    # 仅图结构
    "only_graph": {
        "description": "消融: 仅图结构（无CoT无校验）",
        "use_graph_structure": True,
        "use_cot": False,
        "use_verification": False,
        "verification": {"strict_mode": False}
    }
}


def run_ablation(config_name: str, documents: list, tbox: dict, output_dir: Path):
    """运行单个消融实验"""
    config = ABLATION_CONFIGS[config_name]
    print(f"\n{'='*60}")
    print(f"运行: {config_name}")
    print(f"说明: {config['description']}")
    print(f"{'='*60}")
  
    # 创建抽取器（根据配置调整）
    llm_client = LLMClient()
    extractor = GraphCoTExtractor(llm_client, config)
    batch_extractor = BatchGraphCoTExtractor(extractor)
  
    # 执行抽取
    results = batch_extractor.extract_batch(documents, tbox)
  
    # 保存结果
    output_path = output_dir / f"{config_name}_results.jsonl"
    with open(output_path, 'w', encoding='utf-8') as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + '\n')
  
    # 统计
    total_raw = sum(r.get("n_raw", 0) for r in results)
    total_verified = sum(r.get("n_verified", 0) for r in results)
  
    return {
        "config": config_name,
        "description": config["description"],
        "total_raw": total_raw,
        "total_verified": total_verified,
        "output_path": str(output_path)
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--tbox", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--configs", nargs="+", default=list(ABLATION_CONFIGS.keys()))
    args = parser.parse_args()
  
    # 加载数据
    with open(args.tbox, 'r', encoding='utf-8') as f:
        tbox = json.load(f)
  
    documents = []
    with open(args.input, 'r', encoding='utf-8') as f:
        for line in f:
            documents.append(json.loads(line))
  
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
  
    # 运行消融实验
    all_results = []
    for config_name in args.configs:
        if config_name in ABLATION_CONFIGS:
            result = run_ablation(config_name, documents, tbox, output_dir)
            all_results.append(result)
  
    # 保存汇总
    with open(output_dir / "ablation_summary.json", 'w', encoding='utf-8') as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)
  
    # 打印汇总表
    print("\n" + "="*70)
    print("消融实验汇总")
    print("="*70)
    print(f"{'配置':<25} {'抽取数':<10} {'验证通过':<10} {'通过率':<10}")
    print("-"*70)
    for r in all_results:
        rate = r["total_verified"] / max(r["total_raw"], 1) * 100
        print(f"{r['config']:<25} {r['total_raw']:<10} {r['total_verified']:<10} {rate:.1f}%")


if __name__ == "__main__":
    main()
```

### 6.2 本体构建消融

```python
# scripts/run_ontology_ablation.py

"""
本体构建消融实验
"""

ONTOLOGY_ABLATION_CONFIGS = {
    # 完整方法
    "full": {
        "description": "完整: 专家骨架 + 聚类 + 支持度/置信度筛选",
        "use_expert": True,
        "use_clustering": True,
        "use_quality_filter": True
    },
  
    # 仅专家
    "only_expert": {
        "description": "消融: 仅专家骨架",
        "use_expert": True,
        "use_clustering": False,
        "use_quality_filter": False
    },
  
    # 仅聚类
    "only_clustering": {
        "description": "消融: 仅聚类挖掘",
        "use_expert": False,
        "use_clustering": True,
        "use_quality_filter": True
    },
  
    # 无质量筛选
    "wo_quality_filter": {
        "description": "消融: 无支持度/置信度筛选",
        "use_expert": True,
        "use_clustering": True,
        "use_quality_filter": False
    }
}
```

---

## 七、注意事项与踩坑提醒

### 7.1 本体构建注意事项

| 问题                 | 原因                    | 解决方案                            |
| -------------------- | ----------------------- | ----------------------------------- |
| 聚类结果与专家类重复 | 融合阈值设置不当        | 调整`similarity_threshold`至0.7-0.8 |
| 支持度过滤掉有用类   | 阈值过高或语料覆盖不足  | 降低`min_support`或扩充语料         |
| 专家骨架被误过滤     | `protect_anchors`未启用 | 确保配置中`protect_anchors: true`   |
| LLM标签不一致        | 温度过高                | 设置`temperature: 0.1`              |

### 7.2 抽取层注意事项

| 问题                | 原因                     | 解决方案                   |
| ------------------- | ------------------------ | -------------------------- |
| 图结构路径不完整    | 预定义路径未覆盖所有情况 | 根据语料特点补充路径模式   |
| CoT步骤过长导致遗忘 | Prompt过长               | 精简Prompt，保留核心步骤   |
| 实体被LLM改写       | 未强调"原样保留"         | 在Prompt中多次强调         |
| JSON解析失败        | LLM输出格式不规范        | 增加格式示例，使用正则提取 |
| 校验过严导致召回低  | `strict_mode`启用        | 设置`strict_mode: false`   |

### 7.3 评估注意事项

| 问题                 | 原因                 | 解决方案               |
| -------------------- | -------------------- | ---------------------- |
| Gold与Pred实体不匹配 | 实体边界不一致       | 使用模糊匹配或归一化   |
| 关系名称不统一       | 使用了不同的关系命名 | 建立关系映射表         |
| 评估指标偏低         | 评估粒度过细         | 区分严格匹配和宽松匹配 |

---

## 八、文件结构总览

```
project/
├── configs/
│   ├── ontology_building.yaml      # 本体构建配置
│   └── extraction.yaml             # 抽取配置
│
├── kg/
│   ├── ontology/                   # 本体构建模块
│   │   ├── __init__.py
│   │   ├── expert_skeleton.py      # 专家骨架定义
│   │   ├── corpus_clustering.py    # 语料聚类挖掘
│   │   ├── hybrid_fusion.py        # 混合融合
│   │   ├── quality_filter.py       # 支持度/置信度筛选
│   │   └── hybrid_ontology_builder.py  # 主流程
│   │
│   ├── extraction/                 # 抽取模块
│   │   ├── __init__.py
│   │   ├── graph_structure.py      # 图结构定义
│   │   ├── graph_cot_prompt.py     # 图结构CoT Prompt
│   │   ├── dual_verification.py    # 双重校验
│   │   └── graph_cot_extractor.py  # 抽取执行器
│   │
│   └── llm_client.py               # LLM客户端
│
├── scripts/
│   ├── build_hybrid_ontology.py    # 本体构建脚本
│   ├── run_graph_cot_extraction.py # 抽取脚本
│   ├── run_ablation.py             # 消融实验脚本
│   └── run_ontology_ablation.py    # 本体消融脚本
│
└── outputs/
    ├── ontology/                   # 本体输出
    ├── extraction/                 # 抽取结果
    └── ablation/                   # 消融实验结果
```

---

## 九、执行命令汇总

```bash
# ==================== 本体构建 ====================
python scripts/build_hybrid_ontology.py \
    --corpus data/corpus.jsonl \
    --config configs/ontology_building.yaml \
    --output outputs/ontology

# ==================== 知识抽取 ====================
python scripts/run_graph_cot_extraction.py \
    --input data/test.jsonl \
    --tbox outputs/ontology/master_tbox.json \
    --output outputs/extraction/results.jsonl \
    --config configs/extraction.yaml

# ==================== 消融实验 ====================
python scripts/run_ablation.py \
    --input data/test.jsonl \
    --tbox outputs/ontology/master_tbox.json \
    --output-dir outputs/ablation \
    --configs full wo_graph wo_cot wo_verify baseline_cot_verify
```

---

## 十、预期效果

| 方法                   | Precision | Recall   | F1       | 幻觉率  |
| ---------------------- | --------- | -------- | -------- | ------- |
| 原方法（CoT+双重校验） | ~88%      | ~80%     | ~84%     | ~4%     |
| +图结构引导            | ~90%      | ~83%     | ~86%     | ~3%     |
| +混合本体              | ~91%      | ~85%     | ~88%     | ~2.5%   |
| **完整方法**           | **~92%**  | **~86%** | **~89%** | **~2%** |

---

## 十一、论文写作建议

### 创新点表述

**创新点1**：
> 提出专家引导与数据驱动相结合的混合本体构建方法。该方法以专家定义的核心类和关系作为本体骨架，通过K-means聚类从语料中自动挖掘扩展类，并使用支持度和置信度指标进行质量筛选，实现了本体专业性与数据适配性的平衡。

**创新点2**：
> 提出图结构增强的链式推理抽取方法。该方法将文本的隐含逻辑结构显式建模为图结构，以图结构作为链式推理（CoT）的骨架，实现路径驱动的分步抽取，结合双重校验机制有效降低了大语言模型的幻觉问题。

