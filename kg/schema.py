# 本体定义（规定了有哪些实体类型和关系）
"""
长江灾害知识图谱的模式定义。

本模块定义了高级属性键到图谱中边标签的映射。当将原始事件数据摄入
Neo4j 或内存中的 NetworkX 图时，应使用这些关系以确保创建的节点和边
具有一致的模式。这些键对应于知识抽取管道输出的 JSON 对象中的字段。

例如，一条记录如下：

{ "id": "event‑001", "type": "洪水", "time": "1998年6月中旬至9月上旬", "location": "江西省", "cause": "气候异常", "impact": "淹没大片农田", "measure": "退田还湖" }


在图中将表示为：

* (Event {id: "event‑001"})‑[:occurs_on]→(Time {name: "1998年6月中旬至9月上旬"})
* (Event {id: "event‑001"})‑[:occurs_in]→(Location {name: "江西省"})
* (Event {id: "event‑001"})‑[:has_cause]→(Cause {name: "气候异常"})
* (Event {id: "event‑001"})‑[:has_impact]→(Impact {name: "淹没大片农田"})
* (Event {id: "event‑001"})‑[:has_measure]→(Measure {name: "退田还湖"})

随着数据集的发展，请随意扩展或修改下面的映射。所有键都应映射到有效的
Cypher 关系标识符。节点标签由键的首字母大写派生而来。

"""

from dataclasses import dataclass
from typing import Dict


@dataclass
class Node:
    """表示图谱中的节点及其基本属性。"""
    id: str
    label: str  # e.g., "event", "location", "time", "cause", "impact", "measure"
    props: Dict


@dataclass
class Edge:
    """表示带方向的边，包含关系类型。"""
    src: str
    rel: str   # e.g., "occurs_in", "occurs_on", "caused_by", "has_impact", "handled_by"
    dst: str


RELATIONS = {
    # 时间属性，例如“1998年6月中旬至9月上旬”
    "time": "occurs_on",

    # 地点属性，例如“江西省”或“洞庭湖”
    "location": "occurs_in",

    # 导致灾害发生的因素，例如“气候异常”“降雨集中”
    "cause": "has_cause",

    # 灾害造成的影响，例如“淹没大片农田”“损失数亿元”
    "impact": "has_impact",

    # 应对措施，例如“退田还湖”“加固堤防”
    "measure": "has_measure",

    # 事件类别，例如“洪水”“干旱”“滑坡”等
    "type": "has_type",

    # 可以根据需要扩展更多属性，例如降雨量、受灾地区数量等
    # "rainfall": "has_rainfall",
    # "affected_population": "affects_population",
}

__all__ = ["RELATIONS"]
