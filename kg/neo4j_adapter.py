# 文件路径: kg/neo4j_adapter.py
import os
import json
from dotenv import load_dotenv
from neo4j import GraphDatabase
from tqdm import tqdm
from .schema import RELATIONS  # 复用你之前定义的 schema


load_dotenv()  # 加载 .env 文件中的环境变量

class Neo4jAdapter:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        self.driver.close()

    def clear_database(self):
        """清空数据库（慎用，仅测试用）"""
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
            print("⚠️ 数据库已清空！")

    def import_events(self, jsonl_path):
        """读取 JSONL 并写入 Neo4j"""
        print(f"正在将 {jsonl_path} 导入 Neo4j...")
        
        with self.driver.session() as session:
            with open(jsonl_path, "r", encoding="utf-8-sig") as f:
                lines = f.readlines()
                
            for line in tqdm(lines, desc="Importing"):
                if not line.strip(): continue
                event_data = json.loads(line)
                
                # 使用写事务写入单条数据
                session.execute_write(self._create_event_subgraph, event_data)

    @staticmethod
    def _create_event_subgraph(tx, data):
        """
        核心 Cypher 逻辑：
        1. 创建核心 Event 节点
        2. 创建属性节点（地点、时间等）
        3. 建立边
        """
        event_id = data.get("id")
        if not event_id: return

        # 1. MERGE 核心事件节点 (避免重复创建)
        # 注意：这里把原始 JSON 的所有字段都作为属性存进去了，方便检索
        q_event = """
        MERGE (e:Event {id: $id})
        SET e.type = $type, 
            e.description = $impact,
            e.original_text = $original_text
        """
        tx.run(q_event, id=event_id, type=data.get("type", "unknown"), 
               impact=data.get("impact", ""), original_text=json.dumps(data, ensure_ascii=False))

        # 2. 遍历 Schema 建立关联
        # RELATIONS = {"location": "occurs_in", "time": "occurs_on", ...}
        for key, rel_name in RELATIONS.items():
            val = data.get(key)
            if val:
                # 根据 key 生成节点标签 (Label)，例如 Location, Time, Cause
                label = key.capitalize() 
                
                # Cypher: 
                # MERGE (t:Location {name: "安徽"})
                # MERGE (e)-[:occurs_in]->(t)
                q_rel = f"""
                MATCH (e:Event {{id: $eid}})
                MERGE (t:{label} {{name: $val}})
                MERGE (e)-[:{rel_name}]->(t)
                """
                tx.run(q_rel, eid=event_id, val=val)

# ================= 测试代码 =================
if __name__ == "__main__":
    # 请根据实际情况修改密码
    adapter = Neo4jAdapter(os.getenv("NEO4J_URI"), os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD"))
    
    try:
        # 1. 先清空旧数据
        adapter.clear_database()
        
        # 2. 导入数据
        # 注意：这里用相对路径，确保你在项目根目录运行
        data_path = "data/processed/sample_events.jsonl" 
        if os.path.exists(data_path):
            adapter.import_events(data_path)
            print("✅ 导入成功！")
        else:
            print(f"❌ 文件不存在: {data_path}")
            
    finally:
        adapter.close()