# UIE评估方案分析

## 一、您的理解是正确的

PP-UIE是一个**统一信息抽取框架**，支持多种任务。与您的Gold对比时，应该**分任务评估**：

| 任务              | PP-UIE Schema                                 | 对应Gold字段 | 评估指标 |
| ----------------- | --------------------------------------------- | ------------ | -------- |
| **实体识别(NER)** | `['时间', '地点', '洪水事件', ...]`           | `entities`   | P/R/F1   |
| **关系抽取(RE)**  | `{'洪水事件': ['发生时间', '影响区域', ...]}` | `triples`    | P/R/F1   |
| **事件抽取(EE)**  | 事件schema                                    | `events`     | P/R/F1   |

---

## 二、评估任务拆分

### 2.1 任务1：实体识别 (NER)

```python
# PP-UIE Schema
schema_ner = [
    '时间',           # → Time
    '地点',           # → Location
    '行政区划',       # → AdministrativeRegion
    '水体',           # → WaterBody
    '洪水事件',       # → FloodEvent
    '干旱事件',       # → DroughtEvent
    '致灾因子',       # → HazardFactor
    '灾害影响',       # → Impact
    '数值',           # → Value
    '水文站',         # → HydrologicalStation
    '水利设施',       # → Facility
    '机构',           # → Organization
    '应急响应',       # → EmergencyResponse
]

# 对比Gold中的entities字段
gold_entities = [
    {"name": "2016-2050年", "type": "Time"},
    {"name": "洪水灾害", "type": "FloodEvent"},
    {"name": "长江中下游地区", "type": "Location"},
    ...
]
```

### 2.2 任务2：关系抽取 (RE)

```python
# PP-UIE Schema（嵌套格式）
schema_re = {
    '洪水事件': ['发生时间', '影响区域', '致灾因子', '造成影响'],
    '干旱事件': ['发生时间', '影响区域', '致灾因子', '造成影响'],
    '水文站': ['监测水体', '所在位置', '测量值'],
    '应急响应': ['执行机构', '操作设施'],
}

# 对比Gold中的triples字段
gold_triples = [
    {
        "subject": "洪水灾害",
        "predicate": "occurs_at", 
        "object": "长江中下游地区"
    },
    ...
]
```

### 2.3 任务3：事件抽取 (EE)（可选）

```python
# 对比Gold中的events字段
gold_events = [
    {
        "event_type": "FloodEvent",
        "name": "2016-2050年极端降水洪水灾害",
        "time": {...},
        "space": {...},
        "causes": [...],
        "impacts": {...}
    }
]
```

---

## 三、推荐的评估流程

```
┌─────────────────────────────────────────────────────────┐
│                    评估流程                              │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  Gold数据 ──────────────────────────────────────────┐   │
│     │                                               │   │
│     ├── entities ──→ NER评估 ←── PP-UIE NER输出     │   │
│     │                   │                           │   │
│     │              Entity P/R/F1                    │   │
│     │                                               │   │
│     ├── triples ───→ RE评估 ←── PP-UIE RE输出       │   │
│     │                   │                           │   │
│     │              Triple P/R/F1                    │   │
│     │                                               │   │
│     └── events ────→ EE评估 ←── PP-UIE EE输出       │   │
│                         │                           │   │
│                    Event P/R/F1                     │   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

## 四、具体实现代码

### 4.1 PP-UIE调用脚本

```python
# scripts/run_ppuie_baseline.py

from paddlenlp import Taskflow
import json
from pathlib import Path

class PPUIEBaseline:
    """PP-UIE基线模型"""
  
    def __init__(self, model_name: str = "paddlenlp/PP-UIE-1.5B"):
        self.model_name = model_name
      
        # 实体识别Schema（映射到您的TBox类型）
        self.ner_schema = [
            '时间', '地点', '行政区划', '水体', 
            '洪水事件', '干旱事件', '致灾因子',
            '灾害影响', '数值', '水文站', 
            '水利设施', '机构', '应急响应'
        ]
      
        # 关系抽取Schema
        self.re_schema = {
            '洪水事件': ['发生时间', '影响区域', '致灾因子', '造成影响', '触发响应'],
            '干旱事件': ['发生时间', '影响区域', '致灾因子', '造成影响', '触发响应'],
            '水文站': ['监测水体', '所在位置', '测量值'],
            '应急响应': ['执行机构', '操作设施'],
            '水利设施': ['所在位置'],
        }
      
        # 类型映射：PP-UIE中文 → TBox英文
        self.type_mapping = {
            '时间': 'Time',
            '地点': 'Location',
            '行政区划': 'AdministrativeRegion',
            '水体': 'WaterBody',
            '洪水事件': 'FloodEvent',
            '干旱事件': 'DroughtEvent',
            '致灾因子': 'HazardFactor',
            '灾害影响': 'Impact',
            '数值': 'Value',
            '水文站': 'HydrologicalStation',
            '水利设施': 'Facility',
            '机构': 'Organization',
            '应急响应': 'EmergencyResponse',
        }
      
        # 关系映射：PP-UIE中文 → TBox英文
        self.relation_mapping = {
            '发生时间': 'occurs_during',
            '影响区域': 'affects_region',
            '致灾因子': 'has_cause',
            '造成影响': 'causes_impact',
            '触发响应': 'triggers_response',
            '监测水体': 'monitors',
            '所在位置': 'located_in',
            '测量值': 'has_value',
            '执行机构': 'executes',
            '操作设施': 'operates',
        }
      
        self.ie_ner = None
        self.ie_re = None
  
    def init_ner(self):
        """初始化NER模型"""
        self.ie_ner = Taskflow(
            'information_extraction',
            schema=self.ner_schema,
            schema_lang="zh",
            model=self.model_name,
            precision='float16'
        )
  
    def init_re(self):
        """初始化RE模型"""
        self.ie_re = Taskflow(
            'information_extraction',
            schema=self.re_schema,
            schema_lang="zh",
            model=self.model_name,
            precision='float16'
        )
  
    def extract_entities(self, text: str) -> list:
        """实体抽取"""
        if self.ie_ner is None:
            self.init_ner()
      
        results = self.ie_ner(text)
        entities = []
      
        for result in results:
            for cn_type, ents in result.items():
                en_type = self.type_mapping.get(cn_type, cn_type)
                for ent in ents:
                    entities.append({
                        "name": ent['text'],
                        "type": en_type
                    })
      
        return entities
  
    def extract_relations(self, text: str) -> list:
        """关系抽取"""
        if self.ie_re is None:
            self.init_re()
      
        results = self.ie_re(text)
        triples = []
      
        for result in results:
            for cn_subj_type, subjects in result.items():
                en_subj_type = self.type_mapping.get(cn_subj_type, cn_subj_type)
              
                for subj in subjects:
                    subj_text = subj['text']
                    relations = subj.get('relations', {})
                  
                    for cn_rel, objects in relations.items():
                        en_rel = self.relation_mapping.get(cn_rel, cn_rel)
                      
                        for obj in objects:
                            triples.append({
                                "subject": subj_text,
                                "subject_type": en_subj_type,
                                "predicate": en_rel,
                                "object": obj['text'],
                                "object_type": self._infer_object_type(cn_rel)
                            })
      
        return triples
  
    def _infer_object_type(self, cn_relation: str) -> str:
        """根据关系推断宾语类型"""
        rel_to_obj_type = {
            '发生时间': 'Time',
            '影响区域': 'Location',
            '致灾因子': 'HazardFactor',
            '造成影响': 'Impact',
            '触发响应': 'EmergencyResponse',
            '监测水体': 'WaterBody',
            '所在位置': 'Location',
            '测量值': 'Value',
            '执行机构': 'Organization',
            '操作设施': 'Facility',
        }
        return rel_to_obj_type.get(cn_relation, 'Unknown')
  
    def run_on_dataset(self, input_path: str, output_path: str):
        """在数据集上运行"""
        results = []
      
        with open(input_path, 'r', encoding='utf-8') as f:
            for line in f:
                data = json.loads(line)
                text = data.get('text', data.get('source_text', ''))
                doc_id = data.get('doc_id', '')
              
                # 抽取实体和关系
                entities = self.extract_entities(text)
                triples = self.extract_relations(text)
              
                results.append({
                    "doc_id": doc_id,
                    "entities": entities,
                    "triples": triples
                })
      
        with open(output_path, 'w', encoding='utf-8') as f:
            for r in results:
                f.write(json.dumps(r, ensure_ascii=False) + '\n')
      
        print(f"完成: {len(results)} 条记录 → {output_path}")


if __name__ == "__main__":
    import argparse
  
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="输入文件路径")
    parser.add_argument("--output", required=True, help="输出文件路径")
    parser.add_argument("--model", default="paddlenlp/PP-UIE-1.5B", help="模型名称")
    args = parser.parse_args()
  
    baseline = PPUIEBaseline(model_name=args.model)
    baseline.run_on_dataset(args.input, args.output)
```

### 4.2 评估脚本

```python
# scripts/evaluate_baseline.py

import json
from collections import defaultdict
from typing import List, Dict, Tuple

def normalize_entity(entity: dict) -> Tuple[str, str]:
    """标准化实体为(name, type)元组"""
    return (entity['name'].strip(), entity['type'])

def normalize_triple(triple: dict) -> Tuple[str, str, str]:
    """标准化三元组为(subject, predicate, object)元组"""
    return (
        triple['subject'].strip(),
        triple['predicate'],
        triple['object'].strip()
    )

def calculate_metrics(gold_set: set, pred_set: set) -> Dict[str, float]:
    """计算P/R/F1"""
    if len(pred_set) == 0:
        precision = 0.0
    else:
        precision = len(gold_set & pred_set) / len(pred_set)
  
    if len(gold_set) == 0:
        recall = 0.0
    else:
        recall = len(gold_set & pred_set) / len(gold_set)
  
    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
  
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "gold_count": len(gold_set),
        "pred_count": len(pred_set),
        "correct_count": len(gold_set & pred_set)
    }

def evaluate_ner(gold_data: List[dict], pred_data: List[dict]) -> Dict:
    """评估实体识别"""
    # 建立doc_id索引
    pred_by_id = {d['doc_id']: d for d in pred_data}
  
    all_gold_entities = set()
    all_pred_entities = set()
  
    type_metrics = defaultdict(lambda: {"gold": set(), "pred": set()})
  
    for gold in gold_data:
        doc_id = gold['doc_id']
        pred = pred_by_id.get(doc_id, {"entities": []})
      
        # 收集实体
        for ent in gold.get('entities', []):
            normalized = normalize_entity(ent)
            all_gold_entities.add((doc_id, normalized))
            type_metrics[ent['type']]["gold"].add((doc_id, normalized))
      
        for ent in pred.get('entities', []):
            normalized = normalize_entity(ent)
            all_pred_entities.add((doc_id, normalized))
            type_metrics[ent['type']]["pred"].add((doc_id, normalized))
  
    # 计算总体指标
    overall = calculate_metrics(all_gold_entities, all_pred_entities)
  
    # 计算分类型指标
    by_type = {}
    for ent_type, data in type_metrics.items():
        by_type[ent_type] = calculate_metrics(data["gold"], data["pred"])
  
    return {
        "overall": overall,
        "by_type": by_type
    }

def evaluate_re(gold_data: List[dict], pred_data: List[dict]) -> Dict:
    """评估关系抽取"""
    pred_by_id = {d['doc_id']: d for d in pred_data}
  
    all_gold_triples = set()
    all_pred_triples = set()
  
    rel_metrics = defaultdict(lambda: {"gold": set(), "pred": set()})
  
    for gold in gold_data:
        doc_id = gold['doc_id']
        pred = pred_by_id.get(doc_id, {"triples": []})
      
        for triple in gold.get('triples', []):
            normalized = normalize_triple(triple)
            all_gold_triples.add((doc_id, normalized))
            rel_metrics[triple['predicate']]["gold"].add((doc_id, normalized))
      
        for triple in pred.get('triples', []):
            normalized = normalize_triple(triple)
            all_pred_triples.add((doc_id, normalized))
            rel_metrics[triple['predicate']]["pred"].add((doc_id, normalized))
  
    overall = calculate_metrics(all_gold_triples, all_pred_triples)
  
    by_relation = {}
    for rel_type, data in rel_metrics.items():
        by_relation[rel_type] = calculate_metrics(data["gold"], data["pred"])
  
    return {
        "overall": overall,
        "by_relation": by_relation
    }

def main():
    import argparse
  
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", required=True, help="Gold标注文件")
    parser.add_argument("--pred", required=True, help="预测结果文件")
    parser.add_argument("--output", help="评估结果输出文件")
    args = parser.parse_args()
  
    # 加载数据
    with open(args.gold, 'r', encoding='utf-8') as f:
        gold_data = [json.loads(line) for line in f]
  
    with open(args.pred, 'r', encoding='utf-8') as f:
        pred_data = [json.loads(line) for line in f]
  
    print(f"Gold: {len(gold_data)} 条, Pred: {len(pred_data)} 条")
  
    # 评估NER
    print("\n" + "="*50)
    print("实体识别评估 (NER)")
    print("="*50)
    ner_results = evaluate_ner(gold_data, pred_data)
  
    print(f"\n【总体】")
    print(f"  Precision: {ner_results['overall']['precision']:.4f}")
    print(f"  Recall:    {ner_results['overall']['recall']:.4f}")
    print(f"  F1:        {ner_results['overall']['f1']:.4f}")
  
    print(f"\n【分类型】")
    for ent_type, metrics in sorted(ner_results['by_type'].items()):
        print(f"  {ent_type:20s} P={metrics['precision']:.3f} R={metrics['recall']:.3f} F1={metrics['f1']:.3f}")
  
    # 评估RE
    print("\n" + "="*50)
    print("关系抽取评估 (RE)")
    print("="*50)
    re_results = evaluate_re(gold_data, pred_data)
  
    print(f"\n【总体】")
    print(f"  Precision: {re_results['overall']['precision']:.4f}")
    print(f"  Recall:    {re_results['overall']['recall']:.4f}")
    print(f"  F1:        {re_results['overall']['f1']:.4f}")
  
    print(f"\n【分关系】")
    for rel_type, metrics in sorted(re_results['by_relation'].items()):
        print(f"  {rel_type:20s} P={metrics['precision']:.3f} R={metrics['recall']:.3f} F1={metrics['f1']:.3f}")
  
    # 保存结果
    if args.output:
        results = {
            "ner": ner_results,
            "re": re_results
        }
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n评估结果已保存至: {args.output}")

if __name__ == "__main__":
    main()
```

---

## 五、执行流程

```bash
# 1. 运行PP-UIE基线
python scripts/run_ppuie_baseline.py \
    --input data/test.jsonl \
    --output outputs/ppuie_pred.jsonl \
    --model paddlenlp/PP-UIE-1.5B

# 2. 评估（与Gold对比）
python scripts/evaluate_baseline.py \
    --gold outputs/gold.jsonl \
    --pred outputs/ppuie_pred.jsonl \
    --output outputs/ppuie_eval.json

# 3. 运行您的方法
python scripts/run_extraction_on_test.py \
    --input data/test.jsonl \
    --output outputs/ours_pred.jsonl \
    --model qwen-7b

# 4. 评估您的方法
python scripts/evaluate_baseline.py \
    --gold outputs/gold.jsonl \
    --pred outputs/ours_pred.jsonl \
    --output outputs/ours_eval.json
```

---

## 六、预期输出格式

```
==================================================
实体识别评估 (NER)
==================================================

【总体】
  Precision: 0.7234
  Recall:    0.6891
  F1:        0.7058

【分类型】
  Time                 P=0.812 R=0.756 F1=0.783
  Location             P=0.698 R=0.721 F1=0.709
  FloodEvent           P=0.654 R=0.612 F1=0.632
  ...

==================================================
关系抽取评估 (RE)
==================================================

【总体】
  Precision: 0.5123
  Recall:    0.4567
  F1:        0.4829

【分关系】
  occurs_during        P=0.623 R=0.589 F1=0.606
  affects_region       P=0.534 R=0.478 F1=0.504
  has_cause            P=0.412 R=0.389 F1=0.400
  ...
```

---

## 七、总结

| 评估维度     | Gold字段   | PP-UIE任务 | 指标          |
| ------------ | ---------- | ---------- | ------------- |
| **实体识别** | `entities` | NER        | Entity P/R/F1 |
| **关系抽取** | `triples`  | RE         | Triple P/R/F1 |
| **事件抽取** | `events`   | EE (可选)  | Event P/R/F1  |

**您的理解完全正确：分任务评估是标准做法。**