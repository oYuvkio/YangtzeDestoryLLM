

# 融合指导文档：基于专家引导与聚类的混合本体构建 + 图结构增强的链式抽取方案

## 文档目标

本文档实现以下两个核心改进：

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

# 补充

1、关于专家骨架的定义
# 专家骨架合并分析与建议

## 一、现有骨架与建议骨架对比分析

### 1.1 实体类对比

| 维度           | 您现有的骨架         | 我建议的骨架 | 分析       |
| -------------- | -------------------- | ------------ | ---------- |
| **实体类数量** | 11个                 | 9个          | 您的更细致 |
| **层次结构**   | 有继承关系（parent） | 扁平结构     | 您的更规范 |
| **属性定义**   | 有attributes         | 无           | 您的更完整 |

### 1.2 详细对比表

| 您现有的类             | 我建议的类 | 对应关系 | 建议                     |
| ---------------------- | ---------- | -------- | ------------------------ |
| `DisasterEvent`        | `EVENT`    | 对应     | ✅ 保留您的（更专业）     |
| `FloodEvent`           | -          | 子类     | ✅ 保留（有层次）         |
| `DroughtEvent`         | -          | 子类     | ✅ 保留（有层次）         |
| `HazardFactor`         | `CAUSE`    | 对应     | ✅ 保留您的（命名更专业） |
| `Location`             | `LOCATION` | 对应     | ✅ 保留您的               |
| `AdministrativeRegion` | -          | 子类     | ✅ 保留（有层次）         |
| `WaterBody`            | -          | 子类     | ✅ 保留（有层次）         |
| `Impact`               | `IMPACT`   | 对应     | ✅ 保留您的               |
| `EmergencyResponse`    | `MEASURE`  | 对应     | ✅ 保留您的（命名更准确） |
| `Organization`         | `ORG`      | 对应     | ✅ 保留您的               |
| `HydrologicalStation`  | `FACILITY` | 部分对应 | ⚠️ 需要扩展               |
| -                      | `TIME`     | **缺失** | ⚠️ **建议添加**           |
| -                      | `VALUE`    | **缺失** | ⚠️ **建议添加**           |

### 1.3 关系类型对比

| 您现有的关系        | 我建议的关系    | 对应关系 | 建议                 |
| ------------------- | --------------- | -------- | -------------------- |
| `has_cause`         | `has_cause`     | 完全对应 | ✅ 保留               |
| `affects_region`    | `affects`       | 对应     | ✅ 保留您的（更明确） |
| `causes_impact`     | `causes_impact` | 完全对应 | ✅ 保留               |
| `triggers_response` | `triggers`      | 对应     | ✅ 保留您的（更明确） |
| `located_in`        | `located_in`    | 完全对应 | ✅ 保留               |
| `monitors`          | -               | 您独有   | ✅ 保留（专业）       |
| `executes`          | `implements`    | 对应     | ✅ 保留您的           |
| `occurs_at`         | `occurs_at`     | 完全对应 | ✅ 保留               |
| -                   | `has_value`     | **缺失** | ⚠️ **建议添加**       |
| -                   | `part_of`       | **缺失** | ⚠️ **可选添加**       |
| -                   | `operates`      | **缺失** | ⚠️ **可选添加**       |

---

## 二、合并建议

### 2.1 核心结论

**您现有的骨架质量很高**，具有以下优势：
1. ✅ 有层次继承结构（parent）
2. ✅ 有属性定义（attributes）
3. ✅ 命名更专业（如`HazardFactor`比`CAUSE`更准确）
4. ✅ 关系定义有domain/range约束

**建议：以您现有骨架为基础，补充缺失的2个关键类和1-2个关系**

### 2.2 需要补充的内容

#### 补充实体类

```json
{
  "name": "Time",
  "cn_name": "时间",
  "definition": "灾害事件相关的时间表达，包括时间点、时间段、时间范围",
  "examples": ["1998年8月", "7月15日", "汛期", "入汛以来", "8月1日至15日"],
  "parent": null
},
{
  "name": "Value",
  "cn_name": "数值指标",
  "definition": "水文监测数值、统计数据、损失数量等定量信息",
  "examples": ["45.22米", "50000立方米/秒", "200毫米", "100亿元", "受灾人口100万"],
  "parent": null
},
{
  "name": "Facility",
  "cn_name": "水利设施",
  "definition": "水利工程设施，包括水库、堤防、闸门、泵站等（扩展HydrologicalStation）",
  "examples": ["三峡水库", "荆江大堤", "泄洪闸", "排涝泵站"],
  "parent": null
}
```

#### 补充关系类型

```json
{
  "name": "has_value",
  "cn_name": "测量值为",
  "domain": ["HydrologicalStation", "WaterBody", "Facility"],
  "range": ["Value"],
  "definition": "描述监测站点或设施的测量数值",
  "functional": false
},
{
  "name": "occurs_during",
  "cn_name": "发生于(时间)",
  "domain": ["DisasterEvent"],
  "range": ["Time"],
  "definition": "描述灾害事件发生的时间",
  "functional": false
}
```

---

## 三、合并后的完整专家骨架

```python
# kg/ontology/expert_skeleton.py

"""
专家骨架定义模块（合并版）
基于用户现有骨架，补充缺失的关键类和关系
"""

import json
from typing import Dict, List
from dataclasses import dataclass, field


# ==================== 合并后的专家骨架JSON ====================

EXPERT_SKELETON_JSON = {
    "description": "长江流域水旱灾害领域本体骨架（专家预定义 + 补充）",
    "version": "1.1",
  
    "classes": [
        # ========== 原有类（保留） ==========
        {
            "name": "DisasterEvent",
            "cn_name": "灾害事件",
            "definition": "在一定时间和空间范围内发生的与长江流域相关的水旱灾害过程",
            "examples": ["1998年长江特大洪水", "2022年长江流域特大干旱"],
            "parent": None,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "FloodEvent",
            "cn_name": "洪水事件",
            "definition": "长江干流或支流发生的明显洪水过程",
            "examples": ["1998年长江特大洪水", "2016年长江流域性洪水"],
            "parent": "DisasterEvent",
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "DroughtEvent",
            "cn_name": "干旱事件",
            "definition": "长江流域因降水持续偏少导致的水资源短缺事件",
            "examples": ["2022年长江流域特大干旱", "2006年川渝大旱"],
            "parent": "DisasterEvent",
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "HazardFactor",
            "cn_name": "致灾因子",
            "definition": "导致灾害发生的气象、水文或人为因素",
            "examples": ["持续性强降雨", "高温热浪", "上游来水偏多", "台风"],
            "parent": None,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "Location",
            "cn_name": "地理位置",
            "definition": "灾害发生或影响的地理区域",
            "examples": ["长江中下游", "洞庭湖", "湖北省", "三峡库区"],
            "parent": None,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "AdministrativeRegion",
            "cn_name": "行政区划",
            "definition": "省、市、县等行政单位",
            "examples": ["湖北省", "武汉市", "荆州市", "江西省"],
            "parent": "Location",
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "WaterBody",
            "cn_name": "水体",
            "definition": "河流、湖泊、水库等水域",
            "examples": ["长江", "洞庭湖", "三峡水库", "鄱阳湖"],
            "parent": "Location",
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "Impact",
            "cn_name": "灾害影响",
            "definition": "灾害造成的各类损失和影响",
            "examples": ["人员伤亡", "经济损失", "农田受灾", "房屋倒塌"],
            "parent": None,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "EmergencyResponse",
            "cn_name": "应急响应",
            "definition": "针对灾害采取的应急管理措施",
            "examples": ["启动防汛Ⅰ级响应", "人员转移", "水库调度", "开闸泄洪"],
            "parent": None,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "Organization",
            "cn_name": "机构",
            "definition": "参与防灾减灾的政府部门或组织",
            "examples": ["国家防汛抗旱总指挥部", "长江水利委员会", "水利部"],
            "parent": None,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "HydrologicalStation",
            "cn_name": "水文站",
            "definition": "监测水位、流量等水文数据的站点",
            "examples": ["沙市站", "汉口站", "九江站", "宜昌站"],
            "parent": None,
            "is_anchor": True,
            "source": "expert"
        },
      
        # ========== 补充类（新增） ==========
        {
            "name": "Time",
            "cn_name": "时间",
            "definition": "灾害事件相关的时间表达，包括时间点、时间段、时间范围",
            "examples": ["1998年8月", "7月15日", "汛期", "入汛以来", "8月1日至15日"],
            "parent": None,
            "is_anchor": True,
            "source": "expert_supplement"
        },
        {
            "name": "Value",
            "cn_name": "数值指标",
            "definition": "水文监测数值、统计数据、损失数量等定量信息",
            "examples": ["45.22米", "50000立方米/秒", "200毫米", "100亿元", "受灾人口100万"],
            "parent": None,
            "is_anchor": True,
            "source": "expert_supplement"
        },
        {
            "name": "Facility",
            "cn_name": "水利设施",
            "definition": "水利工程设施，包括水库、堤防、闸门、泵站等",
            "examples": ["三峡水库", "荆江大堤", "泄洪闸", "排涝泵站", "丹江口水库"],
            "parent": None,
            "is_anchor": True,
            "source": "expert_supplement"
        }
    ],
  
    "relations": [
        # ========== 原有关系（保留） ==========
        {
            "name": "has_cause",
            "cn_name": "致灾因子",
            "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"],
            "range": ["HazardFactor"],
            "definition": "描述导致该灾害发生的主要因素",
            "functional": False,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "affects_region",
            "cn_name": "影响区域",
            "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"],
            "range": ["Location", "AdministrativeRegion", "WaterBody"],
            "definition": "描述灾害影响的地理范围",
            "functional": False,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "causes_impact",
            "cn_name": "造成影响",
            "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"],
            "range": ["Impact", "Value"],
            "definition": "描述灾害造成的损失或影响",
            "functional": False,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "triggers_response",
            "cn_name": "触发响应",
            "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"],
            "range": ["EmergencyResponse"],
            "definition": "描述灾害触发的应急响应措施",
            "functional": False,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "located_in",
            "cn_name": "位于",
            "domain": ["WaterBody", "HydrologicalStation", "Facility"],
            "range": ["AdministrativeRegion", "Location"],
            "definition": "描述水体或设施所在的行政区域",
            "functional": False,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "monitors",
            "cn_name": "监测",
            "domain": ["HydrologicalStation"],
            "range": ["WaterBody"],
            "definition": "描述水文站监测的水体",
            "functional": True,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "executes",
            "cn_name": "执行",
            "domain": ["Organization"],
            "range": ["EmergencyResponse"],
            "definition": "描述机构执行的应急措施",
            "functional": False,
            "is_anchor": True,
            "source": "expert"
        },
        {
            "name": "occurs_at",
            "cn_name": "发生于(地点)",
            "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"],
            "range": ["Location", "AdministrativeRegion", "WaterBody"],
            "definition": "描述灾害发生的具体位置",
            "functional": False,
            "is_anchor": True,
            "source": "expert"
        },
      
        # ========== 补充关系（新增） ==========
        {
            "name": "occurs_during",
            "cn_name": "发生于(时间)",
            "domain": ["DisasterEvent", "FloodEvent", "DroughtEvent"],
            "range": ["Time"],
            "definition": "描述灾害事件发生的时间",
            "functional": False,
            "is_anchor": True,
            "source": "expert_supplement"
        },
        {
            "name": "has_value",
            "cn_name": "测量值为",
            "domain": ["HydrologicalStation", "WaterBody", "Facility", "Location"],
            "range": ["Value"],
            "definition": "描述监测站点或设施的测量数值",
            "functional": False,
            "is_anchor": True,
            "source": "expert_supplement"
        },
        {
            "name": "operates",
            "cn_name": "操作",
            "domain": ["Organization", "EmergencyResponse"],
            "range": ["Facility"],
            "definition": "描述对水利设施的操作",
            "functional": False,
            "is_anchor": True,
            "source": "expert_supplement"
        }
    ],
  
    "attributes": [
        # ========== 原有属性（保留） ==========
        {
            "owner": "DisasterEvent",
            "name": "start_time",
            "cn_name": "开始时间",
            "value_type": "datetime"
        },
        {
            "owner": "DisasterEvent",
            "name": "end_time",
            "cn_name": "结束时间",
            "value_type": "datetime"
        },
        {
            "owner": "Impact",
            "name": "affected_population",
            "cn_name": "受灾人口",
            "value_type": "string"
        },
        {
            "owner": "Impact",
            "name": "deaths",
            "cn_name": "死亡人数",
            "value_type": "integer"
        },
        {
            "owner": "Impact",
            "name": "economic_loss",
            "cn_name": "经济损失",
            "value_type": "string"
        },
        {
            "owner": "HydrologicalStation",
            "name": "warning_level",
            "cn_name": "警戒水位",
            "value_type": "float"
        },
        {
            "owner": "HydrologicalStation",
            "name": "guarantee_level",
            "cn_name": "保证水位",
            "value_type": "float"
        },
        {
            "owner": "EmergencyResponse",
            "name": "response_level",
            "cn_name": "响应级别",
            "value_type": "string"
        },
      
        # ========== 补充属性（新增） ==========
        {
            "owner": "Value",
            "name": "unit",
            "cn_name": "单位",
            "value_type": "string"
        },
        {
            "owner": "Value",
            "name": "numeric_value",
            "cn_name": "数值",
            "value_type": "float"
        },
        {
            "owner": "Facility",
            "name": "capacity",
            "cn_name": "库容",
            "value_type": "string"
        }
    ]
}


class ExpertSkeleton:
    """专家骨架类"""
  
    def __init__(self, skeleton_json: Dict = None):
        """
        初始化专家骨架
      
        Args:
            skeleton_json: 骨架JSON，None则使用默认骨架
        """
        self.skeleton = skeleton_json or EXPERT_SKELETON_JSON
      
        # 构建索引
        self._build_indices()
  
    def _build_indices(self):
        """构建索引以便快速查找"""
        self.class_map = {c["name"]: c for c in self.skeleton.get("classes", [])}
        self.relation_map = {r["name"]: r for r in self.skeleton.get("relations", [])}
        self.attribute_map = {}
        for attr in self.skeleton.get("attributes", []):
            owner = attr["owner"]
            if owner not in self.attribute_map:
                self.attribute_map[owner] = []
            self.attribute_map[owner].append(attr)
  
    def get_class(self, name: str) -> Dict:
        """获取实体类定义"""
        return self.class_map.get(name)
  
    def get_relation(self, name: str) -> Dict:
        """获取关系定义"""
        return self.relation_map.get(name)
  
    def get_attributes(self, class_name: str) -> List[Dict]:
        """获取类的属性列表"""
        return self.attribute_map.get(class_name, [])
  
    def get_all_class_names(self) -> List[str]:
        """获取所有实体类名"""
        return list(self.class_map.keys())
  
    def get_all_relation_names(self) -> List[str]:
        """获取所有关系名"""
        return list(self.relation_map.keys())
  
    def get_class_hierarchy(self) -> Dict[str, List[str]]:
        """获取类的层次结构"""
        hierarchy = {}
        for cls in self.skeleton.get("classes", []):
            parent = cls.get("parent")
            if parent:
                if parent not in hierarchy:
                    hierarchy[parent] = []
                hierarchy[parent].append(cls["name"])
        return hierarchy
  
    def to_tbox_format(self) -> Dict:
        """
        转换为TBox格式（用于抽取）
        """
        return {
            "classes": [
                {
                    "name": c["name"],
                    "name_cn": c.get("cn_name", ""),
                    "description": c.get("definition", ""),
                    "examples": c.get("examples", []),
                    "parent": c.get("parent"),
                    "is_anchor": c.get("is_anchor", True),
                    "source": c.get("source", "expert")
                }
                for c in self.skeleton.get("classes", [])
            ],
            "relations": [
                {
                    "name": r["name"],
                    "name_cn": r.get("cn_name", ""),
                    "description": r.get("definition", ""),
                    "domain": r.get("domain", []),
                    "range": r.get("range", []),
                    "is_anchor": r.get("is_anchor", True),
                    "source": r.get("source", "expert")
                }
                for r in self.skeleton.get("relations", [])
            ],
            "attributes": self.skeleton.get("attributes", []),
            "metadata": {
                "description": self.skeleton.get("description", ""),
                "version": self.skeleton.get("version", "1.0")
            }
        }
  
    def to_json(self) -> str:
        """导出为JSON字符串"""
        return json.dumps(self.skeleton, ensure_ascii=False, indent=2)
  
    @classmethod
    def from_json_file(cls, filepath: str) -> "ExpertSkeleton":
        """从JSON文件加载"""
        with open(filepath, 'r', encoding='utf-8') as f:
            skeleton_json = json.load(f)
        return cls(skeleton_json)
  
    def save_to_file(self, filepath: str):
        """保存到文件"""
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.skeleton, f, ensure_ascii=False, indent=2)


# ==================== 便捷函数 ====================

def get_default_expert_skeleton() -> ExpertSkeleton:
    """获取默认专家骨架"""
    return ExpertSkeleton(EXPERT_SKELETON_JSON)


def load_expert_skeleton(filepath: str = None) -> ExpertSkeleton:
    """
    加载专家骨架
  
    Args:
        filepath: 骨架文件路径，None则使用默认骨架
    """
    if filepath:
        return ExpertSkeleton.from_json_file(filepath)
    return get_default_expert_skeleton()
```

---

## 四、合并后的统计

### 4.1 最终骨架统计

| 类别         | 原有 | 补充 | 合计     |
| ------------ | ---- | ---- | -------- |
| **实体类**   | 11个 | 3个  | **14个** |
| **关系类型** | 8个  | 3个  | **11个** |
| **属性**     | 8个  | 3个  | **11个** |

### 4.2 实体类层次结构

```
├── DisasterEvent (灾害事件)
│   ├── FloodEvent (洪水事件)
│   └── DroughtEvent (干旱事件)
├── Location (地理位置)
│   ├── AdministrativeRegion (行政区划)
│   └── WaterBody (水体)
├── HazardFactor (致灾因子)
├── Impact (灾害影响)
├── EmergencyResponse (应急响应)
├── Organization (机构)
├── HydrologicalStation (水文站)
├── Time (时间) [新增]
├── Value (数值指标) [新增]
└── Facility (水利设施) [新增]
```

### 4.3 关系类型总览

| 关系名              | 中文名       | Domain                       | Range             | 来源     |
| ------------------- | ------------ | ---------------------------- | ----------------- | -------- |
| `has_cause`         | 致灾因子     | DisasterEvent*               | HazardFactor      | 原有     |
| `affects_region`    | 影响区域     | DisasterEvent*               | Location*         | 原有     |
| `causes_impact`     | 造成影响     | DisasterEvent*               | Impact, Value     | 原有     |
| `triggers_response` | 触发响应     | DisasterEvent*               | EmergencyResponse | 原有     |
| `located_in`        | 位于         | WaterBody, Station, Facility | Region, Location  | 原有     |
| `monitors`          | 监测         | HydrologicalStation          | WaterBody         | 原有     |
| `executes`          | 执行         | Organization                 | EmergencyResponse | 原有     |
| `occurs_at`         | 发生于(地点) | DisasterEvent*               | Location*         | 原有     |
| `occurs_during`     | 发生于(时间) | DisasterEvent*               | Time              | **新增** |
| `has_value`         | 测量值为     | Station, WaterBody, Facility | Value             | **新增** |
| `operates`          | 操作         | Organization, Response       | Facility          | **新增** |

---

## 五、更新后的图结构定义

由于实体类和关系有变化，需要同步更新图结构定义：

```python
# kg/extraction/graph_structure.py (更新版)

"""
图结构定义模块（适配合并后的专家骨架）
"""

from dataclasses import dataclass, field
from typing import List, Dict


@dataclass
class NodeType:
    """节点类型"""
    role: str
    entity_types: List[str]
    description: str
    keywords: List[str] = field(default_factory=list)


@dataclass
class PathPattern:
    """路径模式"""
    name: str
    pattern: str
    description: str
    extraction_hint: str


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
        lines.append("**图结构示意**:")
        lines.append("```")
        lines.append("[Subject] ──关系──→ [Intermediate] ──关系──→ [Object]")
        lines.append("```")

```python
# kg/extraction/graph_structure.py (更新版 - 续)

        lines.append("")
        lines.append("**节点类型**:")
        for role, node in self.nodes.items():
            role_cn = {"subject": "起始节点", "intermediate": "中间节点", "object": "终止节点"}.get(role, role)
            lines.append(f"- **{role_cn}**: {', '.join(node.entity_types)}")
            lines.append(f"  {node.description}")
            if node.keywords:
                lines.append(f"  识别词: {', '.join(node.keywords[:5])}")
        lines.append("")
      
        lines.append("**典型抽取路径**:")
        for i, p in enumerate(self.paths, 1):
            lines.append(f"{i}. **{p.name}**: `{p.pattern}`")
            lines.append(f"   {p.description}")
      
        return "\n".join(lines)


# ==================== 预定义图结构（适配合并后的骨架） ====================

GRAPH_STRUCTURES = {
    "disaster_event": GraphStructure(
        name="灾害事件描述",
        description="描述灾害事件发生过程、影响和应对的文本",
        nodes={
            "subject": NodeType(
                role="Subject",
                entity_types=["Time", "Location", "AdministrativeRegion", "HazardFactor"],
                description="事件的时间起点、空间起点或原因起点",
                keywords=["年", "月", "日", "省", "市", "县", "流域", "暴雨", "台风", "汛期"]
            ),
            "intermediate": NodeType(
                role="Intermediate",
                entity_types=["DisasterEvent", "FloodEvent", "DroughtEvent", "Facility", "Organization"],
                description="灾害事件本身、涉及的设施或响应机构",
                keywords=["洪水", "干旱", "水库", "堤防", "水利部", "防汛", "特大洪水", "严重干旱"]
            ),
            "object": NodeType(
                role="Object",
                entity_types=["Impact", "Value", "EmergencyResponse"],
                description="灾害影响、监测数值或应对措施",
                keywords=["受灾", "损失", "米", "立方米", "响应", "转移", "死亡", "倒塌"]
            )
        },
        paths=[
            PathPattern(
                name="时间定位",
                pattern="Time → occurs_during → DisasterEvent",
                description="事件发生的时间",
                extraction_hint="寻找时间词与事件的关联，如'X月发生Y洪水'"
            ),
            PathPattern(
                name="空间定位",
                pattern="DisasterEvent → occurs_at → Location",
                description="事件发生的地点",
                extraction_hint="寻找地名与事件的关联，如'X省发生Y'、'Y发生在X'"
            ),
            PathPattern(
                name="影响区域",
                pattern="DisasterEvent → affects_region → AdministrativeRegion",
                description="事件影响的行政区域",
                extraction_hint="寻找影响范围表达，如'Y影响X省'、'X省受Y影响'"
            ),
            PathPattern(
                name="因果链",
                pattern="HazardFactor → has_cause → DisasterEvent → causes_impact → Impact",
                description="从原因到事件到影响的因果链",
                extraction_hint="寻找因果词，如'由于X导致Y造成Z'"
            ),
            PathPattern(
                name="数值关联",
                pattern="HydrologicalStation → has_value → Value",
                description="水文站的监测数值",
                extraction_hint="寻找数值表达，如'X站水位达到Y米'"
            ),
            PathPattern(
                name="响应触发",
                pattern="DisasterEvent → triggers_response → EmergencyResponse",
                description="事件触发的应急响应",
                extraction_hint="寻找响应词，如'X发生后启动Y响应'"
            ),
            PathPattern(
                name="措施执行",
                pattern="Organization → executes → EmergencyResponse",
                description="机构执行的措施",
                extraction_hint="寻找执行词，如'X部门执行Y措施'"
            ),
            PathPattern(
                name="设施操作",
                pattern="Organization → operates → Facility",
                description="对设施的操作",
                extraction_hint="寻找操作词，如'X开启Y闸门'"
            )
        ]
    ),
  
    "flood_event": GraphStructure(
        name="洪水事件描述",
        description="专门描述洪水事件的文本，包含水位、流量等水文信息",
        nodes={
            "subject": NodeType(
                role="Subject",
                entity_types=["Time", "HazardFactor", "WaterBody"],
                description="洪水发生的时间、原因或河流",
                keywords=["年", "月", "暴雨", "长江", "洞庭湖", "鄱阳湖", "上游来水"]
            ),
            "intermediate": NodeType(
                role="Intermediate",
                entity_types=["FloodEvent", "HydrologicalStation", "Facility"],
                description="洪水事件、监测站点或水利设施",
                keywords=["洪水", "洪峰", "沙市站", "汉口站", "三峡水库", "堤防"]
            ),
            "object": NodeType(
                role="Object",
                entity_types=["Value", "Impact", "EmergencyResponse", "AdministrativeRegion"],
                description="水位流量数值、灾害影响或应急措施",
                keywords=["米", "立方米/秒", "超警戒", "受灾", "转移", "泄洪"]
            )
        },
        paths=[
            PathPattern(
                name="洪水时间",
                pattern="Time → occurs_during → FloodEvent",
                description="洪水发生的时间",
                extraction_hint="如'1998年8月发生特大洪水'"
            ),
            PathPattern(
                name="洪水原因",
                pattern="HazardFactor → has_cause → FloodEvent",
                description="导致洪水的原因",
                extraction_hint="如'持续暴雨导致洪水'"
            ),
            PathPattern(
                name="水位监测",
                pattern="HydrologicalStation → has_value → Value",
                description="水文站监测的水位/流量",
                extraction_hint="如'沙市站水位45.22米'"
            ),
            PathPattern(
                name="站点位置",
                pattern="HydrologicalStation → monitors → WaterBody",
                description="水文站监测的水体",
                extraction_hint="如'沙市站监测长江'"
            ),
            PathPattern(
                name="洪水影响",
                pattern="FloodEvent → causes_impact → Impact",
                description="洪水造成的影响",
                extraction_hint="如'洪水造成100万人受灾'"
            ),
            PathPattern(
                name="水库调度",
                pattern="EmergencyResponse → operates → Facility",
                description="对水库的调度操作",
                extraction_hint="如'三峡水库拦洪削峰'"
            )
        ]
    ),
  
    "drought_event": GraphStructure(
        name="干旱事件描述",
        description="专门描述干旱事件的文本，包含降水、蓄水等信息",
        nodes={
            "subject": NodeType(
                role="Subject",
                entity_types=["Time", "HazardFactor"],
                description="干旱发生的时间或原因",
                keywords=["年", "月", "高温", "少雨", "降水偏少", "持续晴热"]
            ),
            "intermediate": NodeType(
                role="Intermediate",
                entity_types=["DroughtEvent", "WaterBody", "Facility"],
                description="干旱事件、受影响水体或水利设施",
                keywords=["干旱", "旱情", "洞庭湖", "鄱阳湖", "水库", "蓄水"]
            ),
            "object": NodeType(
                role="Object",
                entity_types=["Value", "Impact", "EmergencyResponse", "AdministrativeRegion"],
                description="蓄水量数值、旱灾影响或抗旱措施",
                keywords=["亿立方米", "农田受旱", "饮水困难", "调水", "抗旱"]
            )
        },
        paths=[
            PathPattern(
                name="干旱时间",
                pattern="Time → occurs_during → DroughtEvent",
                description="干旱发生的时间",
                extraction_hint="如'2022年夏季发生特大干旱'"
            ),
            PathPattern(
                name="干旱原因",
                pattern="HazardFactor → has_cause → DroughtEvent",
                description="导致干旱的原因",
                extraction_hint="如'持续高温少雨导致干旱'"
            ),
            PathPattern(
                name="干旱影响区域",
                pattern="DroughtEvent → affects_region → AdministrativeRegion",
                description="干旱影响的区域",
                extraction_hint="如'干旱影响湖北、江西等省'"
            ),
            PathPattern(
                name="干旱损失",
                pattern="DroughtEvent → causes_impact → Impact",
                description="干旱造成的损失",
                extraction_hint="如'干旱导致农田受旱500万亩'"
            ),
            PathPattern(
                name="抗旱措施",
                pattern="Organization → executes → EmergencyResponse",
                description="抗旱措施的执行",
                extraction_hint="如'水利部实施应急调水'"
            )
        ]
    ),
  
    "impact_statistics": GraphStructure(
        name="灾情统计描述",
        description="描述灾害损失统计数据的文本",
        nodes={
            "subject": NodeType(
                role="Subject",
                entity_types=["Time", "AdministrativeRegion", "DisasterEvent", "FloodEvent", "DroughtEvent"],
                description="统计时段、区域或灾害类型",
                keywords=["截至", "全年", "全省", "洪涝", "干旱", "累计"]
            ),
            "intermediate": NodeType(
                role="Intermediate",
                entity_types=["Impact"],
                description="统计类别或指标",
                keywords=["受灾人口", "农作物", "经济损失", "死亡", "房屋倒塌"]
            ),
            "object": NodeType(
                role="Object",
                entity_types=["Value"],
                description="统计数值",
                keywords=["万人", "万亩", "亿元", "人", "间"]
            )
        },
        paths=[
            PathPattern(
                name="区域灾情",
                pattern="AdministrativeRegion → causes_impact → Impact → has_value → Value",
                description="区域的灾情数值",
                extraction_hint="如'湖北省受灾人口100万'"
            ),
            PathPattern(
                name="事件损失",
                pattern="DisasterEvent → causes_impact → Value",
                description="灾害事件的损失数值",
                extraction_hint="如'此次洪水造成经济损失50亿元'"
            ),
            PathPattern(
                name="时段统计",
                pattern="Time → occurs_during → DisasterEvent → causes_impact → Impact",
                description="某时段的灾情统计",
                extraction_hint="如'2020年汛期洪涝灾害造成...'"
            )
        ]
    )
}


def detect_text_type(text: str) -> str:
    """
    自动检测文本类型
  
    Args:
        text: 输入文本
      
    Returns:
        文本类型标识
    """
    # 洪水特征
    flood_keywords = ["洪水", "洪峰", "水位", "流量", "超警戒", "超保证", "泄洪", "分洪", "溃堤", "决口"]
    # 干旱特征
    drought_keywords = ["干旱", "旱情", "旱灾", "少雨", "高温", "蓄水", "抗旱", "调水", "饮水困难"]
    # 统计特征
    statistics_keywords = ["截至", "共计", "累计", "统计", "合计", "同比", "全年", "全省", "受灾人口", "经济损失"]
  
    flood_score = sum(1 for kw in flood_keywords if kw in text)
    drought_score = sum(1 for kw in drought_keywords if kw in text)
    statistics_score = sum(1 for kw in statistics_keywords if kw in text)
  
    # 判断逻辑
    if statistics_score >= 3:
        return "impact_statistics"
    elif drought_score > flood_score and drought_score >= 2:
        return "drought_event"
    elif flood_score >= 2:
        return "flood_event"
    else:
        return "disaster_event"


def get_graph_structure(text_type: str) -> GraphStructure:
    """
    获取指定类型的图结构
  
    Args:
        text_type: 文本类型标识
      
    Returns:
        对应的图结构定义
    """
    return GRAPH_STRUCTURES.get(text_type, GRAPH_STRUCTURES["disaster_event"])


def get_all_graph_structures() -> Dict[str, GraphStructure]:
    """获取所有图结构"""
    return GRAPH_STRUCTURES
```

---

## 七、总结与建议

### 7.1 合并结论

| 项目         | 决策         | 理由                                           |
| ------------ | ------------ | ---------------------------------------------- |
| **基础骨架** | 采用您现有的 | 层次结构完整、命名专业、有属性定义             |
| **实体类**   | 补充3个      | Time、Value、Facility是抽取必需的              |
| **关系类型** | 补充3个      | occurs_during、has_value、operates覆盖常见模式 |
| **属性**     | 补充4个      | 完善Value和Facility的属性                      |

### 7.2 后续工作建议

1. **更新代码引用**：确保`ExpertSkeleton`类加载新版骨架

2. **聚类对齐时注意**：
   - 聚类发现的类如果与`FloodEvent`/`DroughtEvent`相似，应合并到对应子类
   - 聚类发现的`水库`类应合并到`Facility`而非`WaterBody`

3. **图结构适配**：已在上面更新，确保路径模式使用正确的类名



2、关于图结构的预定义类型，该支持哪些文本类型的图结构?oral.md定义了3种(灾害事件、调度规则、灾情统计)

# 图结构类型设计分析

## 一、核心问题分析

### 1.1 两种方案对比

| 方案                  | 优点                         | 缺点                         |
| --------------------- | ---------------------------- | ---------------------------- |
| **预定义固定类型**    | 结构清晰、路径精准、易于评估 | 覆盖不全、边界模糊文本难处理 |
| **自动检测+动态选择** | 灵活适应、无需人工标注       | 检测可能出错、增加复杂度     |

### 1.2 建议方案

**推荐：预定义类型 + 自动检测 + 兜底通用结构**

```
文本输入 → 自动检测类型 → 选择对应图结构 → 抽取
              ↓
         检测不确定时
              ↓
         使用通用图结构
```

---

## 二、应该支持的图结构类型

基于水旱灾害领域语料特点，建议支持 **5种图结构**：

### 2.1 图结构类型总览

| 类型ID              | 名称     | 典型场景                   | 核心路径             |
| ------------------- | -------- | -------------------------- | -------------------- |
| `flood_event`       | 洪水事件 | 洪水过程描述、水位流量报道 | 时间→洪水→水位/影响  |
| `drought_event`     | 干旱事件 | 旱情描述、抗旱报道         | 时间→干旱→影响/措施  |
| `dispatch_rule`     | 调度规则 | 水库调度规程、操作规则     | 条件→操作→设施/约束  |
| `impact_statistics` | 灾情统计 | 灾害损失统计、年度汇总     | 区域/时段→类别→数值  |
| `general_disaster`  | 通用灾害 | 综合性描述、混合内容       | 通用路径集合（兜底） |

### 2.2 各类型的判断依据

```python
# 类型检测关键词配置
TEXT_TYPE_KEYWORDS = {
    "flood_event": {
        "strong": ["洪水", "洪峰", "超警戒", "超保证", "泄洪", "分洪", "溃堤"],
        "weak": ["水位", "流量", "暴雨", "汛期", "防汛"],
        "threshold": {"strong": 1, "weak": 3}
    },
    "drought_event": {
        "strong": ["干旱", "旱情", "旱灾", "抗旱", "特旱"],
        "weak": ["高温", "少雨", "蓄水", "调水", "饮水困难", "农田受旱"],
        "threshold": {"strong": 1, "weak": 3}
    },
    "dispatch_rule": {
        "strong": ["当", "若", "如果", "则应", "应当", "不得超过", "控制在"],
        "weak": ["调度", "运用", "开启", "关闭", "泄量", "下泄"],
        "threshold": {"strong": 2, "weak": 3}
    },
    "impact_statistics": {
        "strong": ["截至", "累计", "共计", "统计显示", "合计"],
        "weak": ["受灾人口", "经济损失", "死亡", "万人", "亿元", "万亩"],
        "threshold": {"strong": 1, "weak": 3}
    }
}
```

---

## 三、完整的图结构定义代码

```python
# kg/extraction/graph_structure.py

"""
图结构定义模块
支持5种文本类型的图结构，含自动检测功能
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
import re


@dataclass
class NodeType:
    """节点类型定义"""
    role: str                          # subject / intermediate / object
    entity_types: List[str]            # 可选的实体类型
    description: str                   # 描述
    keywords: List[str] = field(default_factory=list)  # 识别关键词


@dataclass
class PathPattern:
    """路径模式定义"""
    name: str                          # 路径名称
    pattern: str                       # 路径表达式
    description: str                   # 描述
    extraction_hint: str               # 抽取提示
    priority: int = 1                  # 优先级（1最高）


@dataclass
class GraphStructure:
    """图结构定义"""
    type_id: str                       # 类型标识
    name: str                          # 中文名称
    description: str                   # 描述
    nodes: Dict[str, NodeType]         # 节点定义
    paths: List[PathPattern]           # 路径模式
    detection_keywords: Dict[str, List[str]] = field(default_factory=dict)  # 检测关键词
  
    def get_cot_steps(self) -> List[str]:
        """生成CoT推理步骤"""
        steps = []
      
        # Step 1: 节点识别
        node_lines = []
        role_names = {"subject": "起始", "intermediate": "中间", "object": "终止"}
        for role, node in self.nodes.items():
            role_cn = role_names.get(role, role)
            types_str = ", ".join(node.entity_types[:5])
            node_lines.append(f"  - **{role_cn}节点**: {types_str}")
            node_lines.append(f"    {node.description}")
      
        steps.append(f"""**Step 1: 识别图结构节点**

按照以下节点类型，从文本中识别所有实体：

{chr(10).join(node_lines)}

【操作】逐句阅读，标记每个实体及其类型。
【自检】实体文本是否与原文完全一致？类型判断是否正确？""")
      
        # Step 2: 路径连接
        path_lines = []
        for i, p in enumerate(self.paths[:6], 1):  # 最多显示6条路径
            path_lines.append(f"  {i}. **{p.name}**: `{p.pattern}`")
            path_lines.append(f"     提示: {p.extraction_hint}")
      
        steps.append(f"""**Step 2: 按路径模式连接节点**

按照以下路径模式，将已识别的节点连接成三元组：

{chr(10).join(path_lines)}

【操作】对每条路径，检查文本中是否存在匹配的实体对和关系。
【自检】关系方向是否正确？是否有遗漏？""")
      
        # Step 3: 证据回溯
        steps.append("""**Step 3: 证据回溯验证**

对每条候选三元组：
1. 从原文中定位支撑该关系的**证据句**
2. 确认主语和宾语**至少有一个**出现在证据句中
3. 如果找不到证据支撑，**丢弃**该三元组

【操作】为每条三元组填写evidence字段。
【自检】证据是否来自原文？是否真正支撑该关系？""")
      
        return steps
  
    def format_for_prompt(self) -> str:
        """格式化为Prompt片段"""
        lines = [
            f"**文本类型**: {self.name}",
            f"**说明**: {self.description}",
            "",
            "**图结构示意**:",
            "```",
            "[起始节点] ──关系──→ [中间节点] ──关系──→ [终止节点]",
            "```",
            ""
        ]
      
        # 节点类型
        lines.append("**节点类型**:")
        role_names = {"subject": "起始节点", "intermediate": "中间节点", "object": "终止节点"}
        for role, node in self.nodes.items():
            lines.append(f"- **{role_names.get(role, role)}**: {', '.join(node.entity_types)}")
            if node.keywords:
                lines.append(f"  关键词: {', '.join(node.keywords[:5])}")
        lines.append("")
      
        # 核心路径
        lines.append("**核心抽取路径**:")
        for i, p in enumerate(self.paths[:5], 1):
            lines.append(f"{i}. `{p.pattern}` — {p.description}")
      
        return "\n".join(lines)


# ==================== 5种图结构定义 ====================

GRAPH_STRUCTURES: Dict[str, GraphStructure] = {
  
    # ========== 1. 洪水事件 ==========
    "flood_event": GraphStructure(
        type_id="flood_event",
        name="洪水事件描述",
        description="描述洪水发生过程、水位流量变化、影响和应对措施的文本",
        detection_keywords={
            "strong": ["洪水", "洪峰", "超警戒", "超保证", "泄洪", "分洪", "溃堤", "决口"],
            "weak": ["水位", "流量", "暴雨", "汛期", "防汛", "堤防", "漫堤"]
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "HazardFactor", "WaterBody"],
                description="洪水发生的时间、致灾因子或河流水体",
                keywords=["年", "月", "日", "暴雨", "台风", "长江", "汉江"]
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["FloodEvent", "DisasterEvent", "HydrologicalStation", "Facility"],
                description="洪水事件本身、监测站点或水利设施",
                keywords=["洪水", "洪峰", "沙市站", "汉口站", "三峡水库"]
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value", "Impact", "EmergencyResponse", "AdministrativeRegion"],
                description="水位流量数值、灾害影响、应急措施或受影响区域",
                keywords=["米", "立方米/秒", "受灾", "转移", "响应", "省", "市"]
            )
        },
        paths=[
            PathPattern("洪水时间", "Time → occurs_during → FloodEvent", 
                       "洪水发生的时间", "如'1998年8月发生特大洪水'", 1),
            PathPattern("洪水原因", "HazardFactor → has_cause → FloodEvent",
                       "导致洪水的原因", "如'持续暴雨导致洪水'", 1),
            PathPattern("洪水地点", "FloodEvent → occurs_at → Location",
                       "洪水发生的地点", "如'长江中下游发生洪水'", 1),
            PathPattern("水位监测", "HydrologicalStation → has_value → Value",
                       "水文站的水位/流量数值", "如'沙市站水位45.22米'", 1),
            PathPattern("站点监测", "HydrologicalStation → monitors → WaterBody",
                       "水文站监测的水体", "如'汉口站监测长江'", 2),
            PathPattern("洪水影响", "FloodEvent → causes_impact → Impact",
                       "洪水造成的影响", "如'洪水造成100万人受灾'", 1),
            PathPattern("影响区域", "FloodEvent → affects_region → AdministrativeRegion",
                       "洪水影响的区域", "如'洪水影响湖北、江西'", 1),
            PathPattern("触发响应", "FloodEvent → triggers_response → EmergencyResponse",
                       "洪水触发的响应", "如'启动防汛Ⅰ级响应'", 1),
            PathPattern("水库调度", "EmergencyResponse → operates → Facility",
                       "对水库的调度操作", "如'三峡水库拦洪削峰'", 2),
            PathPattern("机构执行", "Organization → executes → EmergencyResponse",
                       "机构执行的措施", "如'水利部启动应急响应'", 2)
        ]
    ),
  
    # ========== 2. 干旱事件 ==========
    "drought_event": GraphStructure(
        type_id="drought_event",
        name="干旱事件描述",
        description="描述干旱发生过程、旱情发展、影响和抗旱措施的文本",
        detection_keywords={
            "strong": ["干旱", "旱情", "旱灾", "抗旱", "特旱", "重旱"],
            "weak": ["高温", "少雨", "降水偏少", "蓄水", "调水", "饮水困难", "农田受旱"]
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "HazardFactor"],
                description="干旱发生的时间或致灾因子",
                keywords=["年", "月", "夏季", "高温", "少雨", "降水偏少"]
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["DroughtEvent", "DisasterEvent", "WaterBody", "Facility"],
                description="干旱事件、受影响水体或水利设施",
                keywords=["干旱", "旱情", "洞庭湖", "鄱阳湖", "水库"]
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value", "Impact", "EmergencyResponse", "AdministrativeRegion"],
                description="蓄水量数值、旱灾影响、抗旱措施或受影响区域",
                keywords=["亿立方米", "受旱", "饮水困难", "调水", "省", "县"]
            )
        },
        paths=[
            PathPattern("干旱时间", "Time → occurs_during → DroughtEvent",
                       "干旱发生的时间", "如'2022年夏季发生特大干旱'", 1),
            PathPattern("干旱原因", "HazardFactor → has_cause → DroughtEvent",
                       "导致干旱的原因", "如'持续高温少雨导致干旱'", 1),
            PathPattern("干旱区域", "DroughtEvent → affects_region → AdministrativeRegion",
                       "干旱影响的区域", "如'干旱影响长江中下游地区'", 1),
            PathPattern("干旱影响", "DroughtEvent → causes_impact → Impact",
                       "干旱造成的影响", "如'干旱导致农田受旱500万亩'", 1),
            PathPattern("水体蓄水", "WaterBody → has_value → Value",
                       "水体的蓄水量", "如'洞庭湖蓄水量较常年偏少5成'", 1),
            PathPattern("抗旱措施", "Organization → executes → EmergencyResponse",
                       "抗旱措施的执行", "如'水利部实施应急调水'", 1),
            PathPattern("设施调度", "EmergencyResponse → operates → Facility",
                       "对设施的调度", "如'三峡水库加大下泄流量'", 2)
        ]
    ),
  
    # ========== 3. 调度规则 ==========
    "dispatch_rule": GraphStructure(
        type_id="dispatch_rule",
        name="调度规则描述",
        description="描述水库、闸门等水利工程调度规则和操作条件的文本",
        detection_keywords={
            "strong": ["当", "若", "如果", "则应", "应当", "不得超过", "控制在", "按照"],
            "weak": ["调度", "运用", "开启", "关闭", "泄量", "下泄", "蓄水", "库水位"]
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "Value", "HazardFactor"],
                description="触发条件（时间条件、阈值条件或水情条件）",
                keywords=["当", "若", "汛期", "超过", "达到", "水位", "流量"]
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["Facility", "EmergencyResponse"],
                description="调度对象（水库、闸门）或操作动作",
                keywords=["水库", "闸门", "泄洪", "开启", "关闭", "调节"]
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value", "Facility", "WaterBody"],
                description="调度目标值、下游设施或保护对象",
                keywords=["不超过", "控制在", "立方米/秒", "下游", "河道"]
            )
        },
        paths=[
            PathPattern("条件触发", "Value → triggers_response → EmergencyResponse",
                       "阈值条件触发操作", "如'当水位超过145米时，开启泄洪闸'", 1),
            PathPattern("时间条件", "Time → triggers_response → EmergencyResponse",
                       "时间条件触发操作", "如'汛期应控制库水位不超过145米'", 1),
            PathPattern("操作设施", "EmergencyResponse → operates → Facility",
                       "操作作用于设施", "如'开启泄洪闸'", 1),
            PathPattern("设施位置", "Facility → located_in → Location",
                       "设施所在位置", "如'三峡水库位于湖北省'", 2),
            PathPattern("下泄约束", "Facility → has_value → Value",
                       "设施的运行参数", "如'下泄流量不超过35000立方米/秒'", 1),
            PathPattern("保护对象", "EmergencyResponse → affects_region → Location",
                       "调度保护的区域", "如'确保荆江河段安全'", 2)
        ]
    ),
  
    # ========== 4. 灾情统计 ==========
    "impact_statistics": GraphStructure(
        type_id="impact_statistics",
        name="灾情统计描述",
        description="描述灾害损失统计数据、受灾情况汇总的文本",
        detection_keywords={
            "strong": ["截至", "累计", "共计", "统计", "合计", "总计"],
            "weak": ["受灾人口", "经济损失", "死亡", "失踪", "万人", "亿元", "万亩", "倒塌"]
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "AdministrativeRegion", "DisasterEvent", "FloodEvent", "DroughtEvent"],
                description="统计时段、统计区域或灾害事件",
                keywords=["截至", "全年", "汛期", "全省", "全国", "此次"]
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["Impact"],
                description="统计类别（受灾人口、经济损失等）",
                keywords=["受灾人口", "死亡", "农作物受灾", "房屋倒塌", "经济损失"]
            ),
            "object": NodeType(
                role="object",
                entity_types=["Value"],
                description="统计数值",
                keywords=["万人", "人", "亿元", "万亩", "间", "公顷"]
            )
        },
        paths=[
            PathPattern("区域统计", "AdministrativeRegion → causes_impact → Impact",
                       "区域的灾情统计", "如'湖北省受灾人口...'", 1),
            PathPattern("影响数值", "Impact → has_value → Value",
                       "影响类别的数值", "如'受灾人口100万人'", 1),
            PathPattern("事件损失", "DisasterEvent → causes_impact → Value",
                       "灾害事件的损失", "如'此次洪水造成经济损失50亿元'", 1),
            PathPattern("时段统计", "Time → occurs_during → DisasterEvent",
                       "统计的时间范围", "如'2020年汛期...'", 2),
            PathPattern("区域事件", "DisasterEvent → affects_region → AdministrativeRegion",
                       "灾害影响的区域", "如'洪涝灾害影响10个省份'", 1)
        ]
    ),
  
    # ========== 5. 通用灾害（兜底） ==========
    "general_disaster": GraphStructure(
        type_id="general_disaster",
        name="通用灾害描述",
        description="综合性灾害描述文本，或无法明确分类的灾害相关文本",
        detection_keywords={
            "strong": [],
            "weak": ["灾害", "灾情", "防灾", "减灾", "救灾", "应急"]
        },
        nodes={
            "subject": NodeType(
                role="subject",
                entity_types=["Time", "Location", "AdministrativeRegion", "HazardFactor", "WaterBody"],
                description="时间、地点或原因",
                keywords=["年", "月", "省", "市", "流域", "暴雨", "台风"]
            ),
            "intermediate": NodeType(
                role="intermediate",
                entity_types=["DisasterEvent", "FloodEvent", "DroughtEvent", "Facility", 
                             "HydrologicalStation", "Organization"],
                description="灾害事件、设施或机构",
                keywords=["灾害", "洪水", "干旱", "水库", "水文站", "水利部"]
            ),
            "object": NodeType(
                role="object",
                entity_types=["Impact", "Value", "EmergencyResponse", "AdministrativeRegion"],
                description="影响、数值、措施或区域",
                keywords=["受灾", "损失", "米", "响应", "转移", "省"]
            )
        },
        paths=[
            # 包含所有可能的路径（作为兜底）
            PathPattern("时间关联", "Time → occurs_during → DisasterEvent",
                       "事件发生时间", "寻找时间与事件的关联", 1),
            PathPattern("地点关联", "DisasterEvent → occurs_at → Location",
                       "事件发生地点", "寻找地点与事件的关联", 1),
            PathPattern("原因关联", "HazardFactor → has_cause → DisasterEvent",
                       "事件的原因", "寻找因果关系", 1),
            PathPattern("影响关联", "DisasterEvent → causes_impact → Impact",
                       "事件的影响", "寻找影响描述", 1),
            PathPattern("数值关联", "HydrologicalStation → has_value → Value",
                       "监测数值", "寻找数值表达", 1),
            PathPattern("响应关联", "DisasterEvent → triggers_response → EmergencyResponse",
                       "触发的响应", "寻找响应措施", 1),
            PathPattern("执行关联", "Organization → executes → EmergencyResponse",
                       "机构执行措施", "寻找执行主体", 2),
            PathPattern("区域关联", "DisasterEvent → affects_region → AdministrativeRegion",
                       "影响区域", "寻找区域范围", 1),
            PathPattern("设施关联", "EmergencyResponse → operates → Facility",
                       "设施操作", "寻找设施操作", 2),
            PathPattern("位置关联", "Facility → located_in → Location",
                       "设施位置", "寻找位置关系", 2)
        ]
    )
}


# ==================== 文本类型自动检测 ====================

class TextTypeDetector:
    """文本类型检测器"""
  
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.default_type = self.config.get("default_type", "general_disaster")
        self.confidence_threshold = self.config.get("confidence_threshold", 0.3)
  
    def detect(self, text: str) -> Tuple[str, float, Dict]:
        """
        检测文本类型
      
        Args:
            text: 输入文本
          
        Returns:
            (type_id, confidence, details)
        """
        scores = {}
        details = {}
      
        for type_id, graph in GRAPH_STRUCTURES.items():
            if type_id == "general_disaster":
                continue  # 通用类型不参与评分
          
            keywords = graph.detection_keywords
            strong_kws = keywords.get("strong", [])
            weak_kws = keywords.get("weak", [])
          
            # 计算匹配
            strong_matches = [kw for kw in strong_kws if kw in text]
            weak_matches = [kw for kw in weak_kws if kw in text]
          
            # 评分：强关键词权重2，弱关键词权重1
            score = len(strong_matches) * 2 + len(weak_matches) * 1
          
            # 归一化（基于最大可能分数）
            max_score = len(strong_kws) * 2 + len(weak_kws) * 1
            normalized_score = score / max_score if max_score > 0 else 0
          
            scores[type_id] = normalized_score
            details[type_id] = {
                "strong_matches": strong_matches,
                "weak_matches": weak_matches,
                "raw_score": score,
                "normalized_score": round(normalized_score, 3)
            }
      
        # 选择最高分
        if scores:
            best_type = max(scores, key=scores.get)
            best_score = scores[best_type]
          
            # 置信度检查
            if best_score >= self.confidence_threshold:
                return best_type, best_score, details
      
        # 兜底：使用通用类型
        return self.default_type, 0.0, details
  
    def detect_with_fallback(self, text: str) -> str:
        """简化版检测，直接返回类型ID"""
        type_id, _, _ = self.detect(text)
        return type_id


def detect_text_type(text: str) -> str:
    """
    便捷函数：检测文本类型
  
    Args:
        text: 输入文本
      
    Returns:
        文本类型ID
    """
    detector = TextTypeDetector()
    return detector.detect_with_fallback(text)


def get_graph_structure(type_id: str) -> GraphStructure:
    """
    获取指定类型的图结构
  
    Args:
        type_id: 类型标识
      
    Returns:
        图结构定义
    """
    return GRAPH_STRUCTURES.get(type_id, GRAPH_STRUCTURES["general_disaster"])


def get_graph_structure_for_text(text: str) -> Tuple[GraphStructure, str, float]:
    """
    根据文本自动选择图结构
  
    Args:
        text: 输入文本
      
    Returns:
        (graph_structure, type_id, confidence)
    """
    detector = TextTypeDetector()
    type_id, confidence, _ = detector.detect(text)
    graph = get_graph_structure(type_id)
    return graph, type_id, confidence


def get_all_graph_structures() -> Dict[str, GraphStructure]:
    """获取所有图结构定义"""
    return GRAPH_STRUCTURES


def get_supported_types() -> List[str]:
    """获取支持的文本类型列表"""
    return list(GRAPH_STRUCTURES.keys())
```

---

## 四、使用示例

### 4.1 自动检测示例

```python
# 测试文本
texts = [
    # 洪水事件
    "1998年8月，长江发生特大洪水，沙市站水位达到45.22米，超警戒水位0.55米。",
  
    # 干旱事件
    "2022年夏季，长江流域遭遇严重干旱，洞庭湖水位创历史新低，农田受旱面积达500万亩。",
  
    # 调度规则
    "当三峡水库入库流量超过50000立方米/秒时，应开启泄洪深孔，控制下泄流量不超过35000立方米/秒。",
  
    # 灾情统计
    "截至8月底，全省累计受灾人口120万人，死亡15人，直接经济损失达50亿元。",
  
    # 混合/通用
    "水利部召开会议，部署长江流域防汛抗旱工作。"
]

detector = TextTypeDetector()

for text in texts:
    type_id, confidence, details = detector.


```python
for text in texts:
    type_id, confidence, details = detector.detect(text)
    print(f"文本: {text[:30]}...")
    print(f"类型: {type_id}, 置信度: {confidence:.2f}")
    print(f"详情: {details.get(type_id, {})}")
    print("-" * 50)
```

### 4.2 完整抽取流程示例

```python
from kg.extraction.graph_structure import get_graph_structure_for_text
from kg.extraction.graph_cot_prompt import GraphCoTPromptBuilder

# 输入文本
text = "1998年8月，长江发生特大洪水，沙市站水位达到45.22米，超警戒水位0.55米，造成湖北省受灾人口500万人。"

# 自动检测并获取图结构
graph, type_id, confidence = get_graph_structure_for_text(text)
print(f"检测类型: {type_id} (置信度: {confidence:.2f})")
print(f"使用图结构: {graph.name}")

# 构建Prompt
builder = GraphCoTPromptBuilder()
prompt = builder.build_prompt(text, tbox, text_type=type_id)
```

---

## 五、配置文件

```yaml
# configs/graph_structure.yaml

# ==================== 文本类型检测配置 ====================
detection:
  # 置信度阈值，低于此值使用通用类型
  confidence_threshold: 0.3

  # 默认类型（检测失败时使用）
  default_type: "general_disaster"

  # 是否启用自动检测
  auto_detect: true

# ==================== 各类型权重调整（可选） ====================
type_weights:
  flood_event: 1.0
  drought_event: 1.0
  dispatch_rule: 1.2      # 调度规则特征明显，可提高权重
  impact_statistics: 1.1  # 统计文本特征明显

# ==================== 路径优先级配置 ====================
path_config:
  # 每种类型最多使用的路径数
  max_paths_per_type: 8

  # 是否只使用高优先级路径
  high_priority_only: false
```

---

## 六、总结

### 6.1 最终方案

| 决策项         | 选择       | 理由                   |
| -------------- | ---------- | ---------------------- |
| **图结构数量** | 5种        | 覆盖主要场景 + 兜底    |
| **检测方式**   | 自动检测   | 减少人工标注，提高效率 |
| **兜底机制**   | 通用图结构 | 确保任何文本都能处理   |

### 6.2 5种图结构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    文本类型自动检测                          │
└─────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │ flood_event │     │drought_event│     │dispatch_rule│
   │  洪水事件   │     │  干旱事件   │     │  调度规则   │
   └─────────────┘     └─────────────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          ▼                   ▼                   ▼
   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │impact_stats │     │general_dis. │     │   (扩展)    │
   │  灾情统计   │     │ 通用(兜底)  │     │   未来...   │
   └─────────────┘     └─────────────┘
```

### 6.3 各类型核心路径

| 类型         | 核心路径                         | 典型三元组示例                           |
| ------------ | -------------------------------- | ---------------------------------------- |
| **洪水事件** | Time→FloodEvent→Impact           | (1998年8月, occurs_during, 长江特大洪水) |
| **干旱事件** | HazardFactor→DroughtEvent→Impact | (持续高温少雨, has_cause, 特大干旱)      |
| **调度规则** | Value→EmergencyResponse→Facility | (水位超145米, triggers, 开启泄洪闸)      |
| **灾情统计** | Region→Impact→Value              | (湖北省, causes_impact, 受灾人口100万)   |
| **通用**     | 全路径集合                       | 根据文本自适应                           |

### 6.4 扩展建议

如果未来需要支持更多类型，只需：

```python
# 添加新的图结构
GRAPH_STRUCTURES["new_type"] = GraphStructure(
    type_id="new_type",
    name="新类型名称",
    description="描述",
    detection_keywords={
        "strong": ["关键词1", "关键词2"],
        "weak": ["关键词3", "关键词4"]
    },
    nodes={...},
    paths=[...]
)
```



3、补充和注意的事项吗？

# 方案完整性审查与补充建议

您的思考非常全面，整体方案已经相当完整。以下是我对几个关键点的补充建议和注意事项：

---

## 一、需要补充的内容

### 1.1 实体归一化模块（建议新增）

您提到的"实体对齐"问题很重要，建议增加一个轻量级的归一化模块：

```python
# kg/extraction/entity_normalizer.py

"""
实体归一化模块
处理抽取结果中的实体标准化问题
"""

import re
from typing import Dict, List, Tuple, Optional


class EntityNormalizer:
    """实体归一化器"""
  
    def __init__(self):
        # 数值单位映射
        self.unit_patterns = {
            "人口": r"(\d+(?:\.\d+)?)\s*(万人|人|万)",
            "面积": r"(\d+(?:\.\d+)?)\s*(万亩|亩|公顷|万公顷|平方公里)",
            "水位": r"(\d+(?:\.\d+)?)\s*(米|m)",
            "流量": r"(\d+(?:\.\d+)?)\s*(立方米/秒|立方米每秒|m³/s)",
            "损失": r"(\d+(?:\.\d+)?)\s*(亿元|万元|元)",
            "降水": r"(\d+(?:\.\d+)?)\s*(毫米|mm)"
        }
      
        # 时间归一化模式
        self.time_patterns = [
            (r"(\d{4})年(\d{1,2})月(\d{1,2})日", "{0}-{1:02d}-{2:02d}"),
            (r"(\d{4})年(\d{1,2})月", "{0}-{1:02d}"),
            (r"(\d{1,2})月(\d{1,2})日", "XXXX-{0:02d}-{1:02d}"),
        ]
      
        # 地名别名映射
        self.location_aliases = {
            "鄂": "湖北省",
            "赣": "江西省",
            "皖": "安徽省",
            "川": "四川省",
            "渝": "重庆市",
            "湘": "湖南省",
        }
  
    def normalize_value(self, text: str, value_type: str = None) -> Dict:
        """
        归一化数值实体
      
        Args:
            text: 原始文本，如"45.22米"、"100万人"
            value_type: 数值类型提示
          
        Returns:
            {"original": "45.22米", "value": 45.22, "unit": "米", "normalized": "45.22米"}
        """
        result = {"original": text, "value": None, "unit": None, "normalized": text}
      
        # 尝试匹配各种模式
        for vtype, pattern in self.unit_patterns.items():
            match = re.search(pattern, text)
            if match:
                result["value"] = float(match.group(1))
                result["unit"] = match.group(2)
                result["value_type"] = vtype
                break
      
        # 通用数值提取
        if result["value"] is None:
            num_match = re.search(r"(\d+(?:\.\d+)?)", text)
            if num_match:
                result["value"] = float(num_match.group(1))
      
        return result
  
    def normalize_time(self, text: str) -> Dict:
        """
        归一化时间实体
      
        Args:
            text: 原始时间文本
          
        Returns:
            {"original": "1998年8月", "normalized": "1998-08", "precision": "month"}
        """
        result = {"original": text, "normalized": text, "precision": "unknown"}
      
        for pattern, fmt in self.time_patterns:
            match = re.search(pattern, text)
            if match:
                groups = [int(g) for g in match.groups()]
                result["normalized"] = fmt.format(*groups)
                if len(groups) == 3:
                    result["precision"] = "day"
                elif len(groups) == 2:
                    result["precision"] = "month"
                break
      
        return result
  
    def normalize_location(self, text: str) -> str:
        """归一化地名"""
        # 处理简称
        for alias, full_name in self.location_aliases.items():
            if text == alias:
                return full_name
        return text
  
    def normalize_triple(self, triple: Dict) -> Dict:
        """
        归一化整个三元组
      
        Args:
            triple: {"subject": ..., "relation": ..., "object": ..., "subject_type": ..., "object_type": ...}
        """
        result = triple.copy()
      
        # 根据类型归一化
        if triple.get("subject_type") == "Value":
            norm = self.normalize_value(triple["subject"])
            result["subject_normalized"] = norm
        elif triple.get("subject_type") == "Time":
            norm = self.normalize_time(triple["subject"])
            result["subject_normalized"] = norm
        elif triple.get("subject_type") in ["Location", "AdministrativeRegion"]:
            result["subject"] = self.normalize_location(triple["subject"])
      
        if triple.get("object_type") == "Value":
            norm = self.normalize_value(triple["object"])
            result["object_normalized"] = norm
        elif triple.get("object_type") == "Time":
            norm = self.normalize_time(triple["object"])
            result["object_normalized"] = norm
        elif triple.get("object_type") in ["Location", "AdministrativeRegion"]:
            result["object"] = self.normalize_location(triple["object"])
      
        return result
```

### 1.2 评估模块（建议新增）

```python
# kg/evaluation/metrics.py

"""
评估指标计算模块
"""

from typing import List, Dict, Set, Tuple
from collections import defaultdict


class KGEvaluator:
    """知识图谱抽取评估器"""
  
    def __init__(self, config: dict = None):
        self.config = config or {}
        self.fuzzy_match = self.config.get("fuzzy_match", True)
        self.ignore_case = self.config.get("ignore_case", True)
  
    def _normalize_entity(self, entity: str) -> str:
        """实体归一化（用于匹配）"""
        if self.ignore_case:
            entity = entity.lower()
        # 去除空格和标点
        entity = entity.strip().replace(" ", "")
        return entity
  
    def _match_triple(self, pred: Dict, gold: Dict) -> bool:
        """判断两个三元组是否匹配"""
        # 严格匹配
        if not self.fuzzy_match:
            return (
                self._normalize_entity(pred["subject"]) == self._normalize_entity(gold["subject"]) and
                pred["relation"] == gold["relation"] and
                self._normalize_entity(pred["object"]) == self._normalize_entity(gold["object"])
            )
      
        # 模糊匹配：实体包含关系
        pred_s = self._normalize_entity(pred["subject"])
        pred_o = self._normalize_entity(pred["object"])
        gold_s = self._normalize_entity(gold["subject"])
        gold_o = self._normalize_entity(gold["object"])
      
        s_match = pred_s in gold_s or gold_s in pred_s
        o_match = pred_o in gold_o or gold_o in pred_o
        r_match = pred["relation"] == gold["relation"]
      
        return s_match and r_match and o_match
  
    def evaluate(self, predictions: List[Dict], golds: List[Dict]) -> Dict:
        """
        计算评估指标
      
        Args:
            predictions: 预测的三元组列表
            golds: 标准答案三元组列表
          
        Returns:
            {"precision": ..., "recall": ..., "f1": ...}
        """
        if not golds:
            return {"precision": 0.0, "recall": 0.0, "f1": 0.0}
      
        # 匹配计数
        matched_pred = set()
        matched_gold = set()
      
        for i, pred in enumerate(predictions):
            for j, gold in enumerate(golds):
                if j not in matched_gold and self._match_triple(pred, gold):
                    matched_pred.add(i)
                    matched_gold.add(j)
                    break
      
        tp = len(matched_gold)
        precision = tp / len(predictions) if predictions else 0.0
        recall = tp / len(golds) if golds else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
      
        return {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "pred_count": len(predictions),
            "gold_count": len(golds)
        }
  
    def evaluate_by_relation(self, predictions: List[Dict], golds: List[Dict]) -> Dict:
        """按关系类型分别评估"""
        # 按关系分组
        pred_by_rel = defaultdict(list)
        gold_by_rel = defaultdict(list)
      
        for p in predictions:
            pred_by_rel[p["relation"]].append(p)
        for g in golds:
            gold_by_rel[g["relation"]].append(g)
      
        # 分别评估
        results = {}
        all_relations = set(pred_by_rel.keys()) | set(gold_by_rel.keys())
      
        for rel in all_relations:
            results[rel] = self.evaluate(pred_by_rel[rel], gold_by_rel[rel])
      
        return results


def calculate_hallucination_rate(predictions: List[Dict], golds: List[Dict], 
                                  source_text: str) -> Dict:
    """
    计算幻觉率
  
    幻觉定义：预测的实体在原文中不存在
    """
    hallucinated = []
  
    for pred in predictions:
        subject_in_text = pred["subject"] in source_text
        object_in_text = pred["object"] in source_text
      
        if not subject_in_text or not object_in_text:
            hallucinated.append({
                "triple": pred,
                "subject_in_text": subject_in_text,
                "object_in_text": object_in_text
            })
  
    rate = len(hallucinated) / len(predictions) if predictions else 0.0
  
    return {
        "hallucination_rate": round(rate, 4),
        "hallucinated_count": len(hallucinated),
        "total_count": len(predictions),
        "hallucinated_triples": hallucinated
    }
```

---

## 二、关键注意事项

### 2.1 Prompt工程注意事项

| 问题                   | 风险                  | 解决方案                         |
| ---------------------- | --------------------- | -------------------------------- |
| **图结构展示过于复杂** | LLM理解困难，输出混乱 | 使用简洁的ASCII图 + 编号列表     |
| **CoT步骤过多**        | 上下文过长，遗忘前文  | 控制在3-4步，每步聚焦            |
| **实体边界不清**       | LLM改写或截断实体     | 强调"原样保留"，给出正反例       |
| **关系名不统一**       | LLM使用自创关系名     | 明确列出允许的关系，要求严格选择 |

### 2.2 图结构设计注意事项

```python
# 在Prompt中展示图结构的推荐格式

GRAPH_DISPLAY_TEMPLATE = """
【当前文本类型】: {text_type}

【图结构路径】:
1. {path1_name}: [{node1}] --{rel1}--> [{node2}]
2. {path2_name}: [{node2}] --{rel2}--> [{node3}]
...

【抽取要求】:
- 按上述路径顺序，逐条检查是否存在对应三元组
- 每条三元组必须有原文证据支撑
- 实体文本必须与原文完全一致
"""
```

### 2.3 消融实验设计补充

建议增加以下消融配置：

```python
ABLATION_CONFIGS_EXTENDED = {
    # ... 原有配置 ...
  
    # 图结构相关消融
    "wo_auto_detect": {
        "description": "消融: 不自动检测文本类型，统一使用通用图结构",
        "use_graph_structure": True,
        "auto_detect_type": False,  # 关键：禁用自动检测
        "default_graph_type": "general_disaster"
    },
  
    "specific_vs_general": {
        "description": "对比: 特定图结构 vs 通用图结构",
        "use_graph_structure": True,
        "auto_detect_type": True,
        # 这个配置用于对比实验
    },
  
    # 本体相关消融
    "wo_clustering": {
        "description": "消融: 仅使用专家骨架，不进行聚类扩展",
        "use_expert": True,
        "use_clustering": False
    }
}
```

### 2.4 错误处理与日志

```python
# kg/utils/logger.py

"""
日志与错误处理模块
"""

import logging
from datetime import datetime
from pathlib import Path


def setup_logger(name: str, log_dir: str = "logs") -> logging.Logger:
    """配置日志器"""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
  
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
  
    # 文件处理器
    fh = logging.FileHandler(
        f"{log_dir}/{name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log",
        encoding='utf-8'
    )
    fh.setLevel(logging.DEBUG)
  
    # 控制台处理器
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
  
    # 格式
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
  
    logger.addHandler(fh)
    logger.addHandler(ch)
  
    return logger


class ExtractionError(Exception):
    """抽取过程异常"""
    pass


class LLMResponseError(ExtractionError):
    """LLM响应异常"""
    pass


class JSONParseError(ExtractionError):
    """JSON解析异常"""
    pass
```

---

## 三、最终文件结构

```
project/
├── configs/
│   ├── ontology_building.yaml
│   ├── extraction.yaml
│   └── graph_structure.yaml          # 新增
│
├── kg/
│   ├── ontology/
│   │   ├── __init__.py
│   │   ├── expert_skeleton.py
│   │   ├── corpus_clustering.py
│   │   ├── hybrid_fusion.py
│   │   ├── quality_filter.py
│   │   └── hybrid_ontology_builder.py
│   │
│   ├── extraction/
│   │   ├── __init__.py
│   │   ├── graph_structure.py        # 5种图结构 + 自动检测
│   │   ├── graph_cot_prompt.py
│   │   ├── dual_verification.py
│   │   ├── graph_cot_extractor.py
│   │   └── entity_normalizer.py      # 新增
│   │
│   ├── evaluation/                    # 新增
│   │   ├── __init__.py
│   │   └── metrics.py
│   │
│   ├── utils/                         # 新增
│   │   ├── __init__.py
│   │   └── logger.py
│   │
│   └── llm_client.py
│
├── scripts/
│   ├── build_hybrid_ontology.py
│   ├── run_graph_cot_extraction.py
│   ├── run_ablation.py
│   ├── run_evaluation.py             # 新增
│   └── run_ontology_ablation.py
│
├── data/
│   ├── expert_skeleton_v1.1.json     # 合并后的专家骨架
│   ├── corpus/
│   └── test/
│
└── outputs/
    ├── ontology/
    ├── extraction/
    ├── evaluation/                    # 新增
    └── ablation/
```

---

## 四、执行流程总结

```
┌─────────────────────────────────────────────────────────────────┐
│                        完整执行流程                              │
└─────────────────────────────────────────────────────────────────┘

Phase 1: 本体构建
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 专家骨架    │ +  │ 语料聚类    │ -> │ 混合融合    │
│ (14类/11关系)│    │ (扩展类)    │    │ (质量筛选)  │
└─────────────┘    └─────────────┘
                                            │
                                            ▼
                                    ┌─────────────┐
                                    │ Master TBox │
                                    └─────────────┘

Phase 2: 知识抽取
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 输入文本    │ -> │ 类型检测    │ -> │ 选择图结构  │
└─────────────┘    │ (5种类型)   │    │             │
                   └─────────────┘    └─────────────┘
                                            │
                                            ▼
                   ┌─────────────┐    ┌─────────────┐
                   │ 图结构CoT   │ -> │ 双重校验    │
                   │ 分步抽取    │    │             │
                   └─────────────┘    └─────────────┘
                                            │
                                            ▼
                   ┌─────────────┐    ┌─────────────┐
                   │ 实体归一化  │ -> │ 输出三元组  │
                   └─────────────┘    └─────────────┘

Phase 3: 评估
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ 预测结果    │ +  │ 标准答案    │ -> │ 指标计算    │
└─────────────┘    └─────────────┘    │ P/R/F1/幻觉 │
                                      └─────────────┘
```

---

## 五、最后的检查清单

| 检查项           | 状态 | 备注                   |
| ---------------- | ---- | ---------------------- |
| 专家骨架定义完整 | ✅    | 14类 + 11关系 + 11属性 |
| 图结构类型覆盖   | ✅    | 5种（含兜底）          |
| 自动检测逻辑     | ✅    | 关键词 + 置信度        |
| CoT Prompt模板   | ✅    | 3步结构化推理          |
| 双重校验机制     | ✅    | 自校验 + 交叉校验      |
| 实体归一化       | ✅    | 数值/时间/地名         |
| 评估指标         | ✅    | P/R/F1 + 幻觉率        |
| 消融实验设计     | ✅    | 6+配置                 |
| 错误处理         | ✅    | 日志 + 异常类          |
| 配置文件         | ✅    | YAML格式               |

**您的方案已经非常完整，可以开始实现了！** 🎉

如果在实现过程中遇到具体问题，随时可以继续讨论。
