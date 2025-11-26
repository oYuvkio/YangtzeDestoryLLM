from kg.extractor import LLMExtractor
import sys
import os
import json
import time
import argparse  # 1. 新增参数解析
import yaml      # 2. 新增 yaml 读取
from dataclasses import asdict  # 3. 新增 dataclass 转字典工具
from tqdm import tqdm

# 🔧 路径黑魔法：将项目根目录加入 sys.path
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.append(project_root)

# 导入抽取器


def load_config(config_path):
    """加载 YAML 配置文件"""
    if not os.path.isabs(config_path):
        config_path = os.path.join(project_root, config_path)

    try:
        with open(config_path, "r", encoding="utf-8-sig") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ 配置文件未找到: {config_path}")
        sys.exit(1)


def run_extraction_experiment(args):
    """
    运行知识抽取实验：
    模拟从非结构化文本中抽取知识，并保存结果用于后续计算 F1 值。
    """
    print(">>> 开始运行：知识抽取对比实验 (Innovation 1) <<<")

    # 1. 准备数据 (这里用模拟数据，后续请替换为读取 data/raw/ 目录下的真实 txt 文件)
    # test_docs = [
    #     {
    #         "doc_id": "doc_001",
    #         "text": "2020年7月，受强降雨影响，安徽省长江干流全线超警。洪水导致芜湖、铜陵等地农作物受灾面积达50万亩。省防指启动I级应急响应。"
    #     },
    #     {
    #         "doc_id": "doc_002",
    #         "text": "三峡水库在2022年干旱期间加大了下泄流量，有效缓解了长江中下游的水位下降问题，保障了航运安全。"
    #     }
    # ]

    # 1. 加载配置
    cfg = load_config(args.config)
    print(f"已加载配置，使用模型: {cfg['llm'].get('model_name', 'default')}")

    # 2. 准备数据
    test_docs = []
    raw_data_dir = os.path.join(project_root, "data", "raw")

    for filename in os.listdir(raw_data_dir):
        if filename.endswith(".txt"):
            filepath = os.path.join(raw_data_dir, filename)
            with open(filepath, "r", encoding="utf-8-sig") as f:
                text = f.read()
                test_docs.append({
                    "doc_id": filename[:-4],  # 去掉 .txt 后缀
                    "text": text
                })
    print(f"找到 {len(test_docs)} 个文档待处理。")

    # 3. 初始化抽取器 (传入 llm 配置)
    # 这里的 cfg['llm'] 包含了 provider, model_name, temperature 等
    extractor = LLMExtractor(cfg['llm'])

    results = []

    # 4. 批量处理
    for doc in tqdm(test_docs, desc="正在抽取"):
        start_time = time.time()

        # 调用核心抽取功能
        try:
            kg_result_obj = extractor.extract(doc["text"])
            # 🔥 修复点：将 ExtractionResult 对象转换为字典
            kg_data = asdict(kg_result_obj)
        except Exception as e:
            print(f"\n⚠️ 文档 {doc['doc_id']} 抽取失败: {e}")
            kg_data = {"entities": [], "relations": [], "error": str(e)}

        end_time = time.time()

        # 记录结果
        results.append({
            "doc_id": doc["doc_id"],
            "raw_text": doc["text"],
            "extraction_result": kg_data,
            "latency": end_time - start_time
        })

    # 5. 保存实验结果
    output_path = os.path.join(
        project_root, "experiments", "results_extraction.json")
    with open(output_path, "w", encoding="utf-8-sig") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 实验完成！结果已保存至: {output_path}")
    print("下一步：请打开该 JSON 文件，人工核对抽取的实体和关系是否准确。")


if __name__ == "__main__":
    # 解析命令行参数
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/cfg.yaml",
                        help="Path to configuration file")
    args = parser.parse_args()

    run_extraction_experiment(args)
