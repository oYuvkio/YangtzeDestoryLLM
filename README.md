# YangtzeDestoryLLM (proto)

## 安装
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

## 运行基线
python experiments/run_baseline.py --config configs/demo.yaml

## 评测示例
python experiments/eval.py --config configs/demo.yaml

## 目录
- data/processed: 示例事件与QA
- kg: 图谱构建、查询、LLM占位
- retrievers: 文本/图检索
- experiments: 基线与评测脚本

## 后续扩展
- 用 jieba 分词提升中文检索效果。
- 在 kg/llm_stub.py 接入真实 LLM，将 triples 作为上下文，生成最终答案。
- 扩充 data/processed/sample_events.jsonl 为真实长江灾害样本。
- 迁移 networkx 原型到 Neo4j 或向量库（FAISS/Milvus）。
