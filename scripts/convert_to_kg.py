from kg.schema import RELATIONS
import json
import os
import sys

# 添加项目根目录到路径，以便导入 kg.schema
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)


def invert_schema():
    """
    反转 schema 映射：从 'has_impact' (边) -> 'impact' (属性 key)
    """
    return {v: k for k, v in RELATIONS.items()}


def convert():
    # 1. 路径配置
    input_path = os.path.join(
        project_root, "experiments", "results_extraction.json")
    output_path = os.path.join(
        project_root, "data", "processed", "real_events.jsonl")

    print(f"📖 读取抽取结果: {input_path}")
    if not os.path.exists(input_path):
        print("❌ 文件不存在，请先运行 experiments/exp_kg_construction.py")
        return

    with open(input_path, "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    # 反转关系映射表
    rel_to_key = invert_schema()

    # 统计
    count = 0

    # 2. 转换逻辑
    # 策略：为了让 Neo4j 适配器能处理“一对多”关系（比如一个洪水有多个影响），
    # 我们将每个关系拆分成独立的一行 JSON 记录。
    # Neo4j 的 MERGE 语句具有幂等性，这会自动将它们合并到同一个事件节点上。

    with open(output_path, "w", encoding="utf-8-sig") as out_f:
        for doc in data:
            extraction = doc.get("extraction_result", {})
            relations = extraction.get("relations", [])

            if not relations:
                continue

            # 遍历该文档抽取出的所有关系
            for rel in relations:
                head = rel["head"]      # 例如：1998年洪水
                relation = rel["relation"]  # 例如：has_impact
                tail = rel["tail"]      # 例如：江西

                # 找到对应的 JSON key (例如 impact)
                key = rel_to_key.get(relation)

                if key:
                    # 构造一条“微记录”
                    # 适配器读到这就知道：找到 ID 为 head 的事件，给它添加一个 key 类型的边，指向 tail
                    record = {
                        "id": head,
                        key: tail,
                        "source": doc.get("doc_id", "unknown")
                    }

                    # 补充类型信息 (如果有)
                    # 尝试在实体列表中找 head 的类型
                    for ent in extraction.get("entities", []):
                        if ent["name"] == head:
                            record["type"] = ent["type"]
                            break

                    out_f.write(json.dumps(record, ensure_ascii=False) + "\n")
                    count += 1

    print(f"✅ 转换完成！共生成 {count} 条图谱记录。")
    print(f"💾 输出文件: {output_path}")


if __name__ == "__main__":
    convert()
