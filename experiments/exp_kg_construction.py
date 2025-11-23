import sys
import os
import json
import time
from tqdm import tqdm # 进度条库，pip install tqdm

# ----------------------------------------------------------------------
# 🔧 路径黑魔法：将项目根目录加入 sys.path，防止 import 报错
# ----------------------------------------------------------------------
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

from kg.extractor import KnowledgeExtractor

def run_extraction_experiment():
    """
    运行知识抽取实验：
    模拟从非结构化文本中抽取知识，并保存结果用于后续计算 F1 值。
    """
    print(">>> 开始运行：知识抽取对比实验 (Innovation 1) <<<")
    
    # 1. 准备数据 (这里用模拟数据，后续请替换为读取 data/raw/ 目录下的真实 txt 文件)
    test_docs = [
        {
            "doc_id": "doc_001",
            "text": "2020年7月，受强降雨影响，安徽省长江干流全线超警。洪水导致芜湖、铜陵等地农作物受灾面积达50万亩。省防指启动I级应急响应。"
        },
        {
            "doc_id": "doc_002",
            "text": "三峡水库在2022年干旱期间加大了下泄流量，有效缓解了长江中下游的水位下降问题，保障了航运安全。"
        }
    ]
    
    # 2. 初始化抽取器
    extractor = KnowledgeExtractor()
    
    results = []
    
    # 3. 批量处理
    for doc in tqdm(test_docs, desc="正在抽取"):
        start_time = time.time()
        
        # 调用核心抽取功能
        kg_data = extractor.extract(doc["text"])
        
        end_time = time.time()
        
        # 记录结果
        results.append({
            "doc_id": doc["doc_id"],
            "raw_text": doc["text"],
            "extraction_result": kg_data,
            "latency": end_time - start_time
        })
    
    # 4. 保存实验结果
    output_path = os.path.join(project_root, "experiments", "results_extraction.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
        
    print(f"\n✅ 实验完成！结果已保存至: {output_path}")
    print("下一步：请打开该 JSON 文件，人工核对抽取的实体和关系是否准确。")

if __name__ == "__main__":
    run_extraction_experiment()