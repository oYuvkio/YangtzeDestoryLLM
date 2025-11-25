# YangtzeDestoryLLM

基于大语言模型与知识图谱的长江灾害知识问答系统 (Master Thesis Project)

本项目旨在构建一个端到端的 RAG 系统，结合**知识图谱结构化信息**与**大语言模型语义理解能力**，解决传统灾害问答中信息检索不准、推理能力弱的问题。

## ✨ 核心特性
- **智能知识抽取**：基于 Prompt Engineering 从非结构化文本（如年鉴、新闻）中自动抽取实体与关系。
- **GraphRAG 引擎**：利用图谱的多跳（Multi-hop）检索能力，捕捉灾害事件间的隐性关联。
- **多模型支持**：采用策略模式封装，支持 **ZhipuAI (ChatGLM)** 和 **Google Gemini** 无缝切换。
- **混合存储**：支持 **NetworkX**（内存图）快速实验与 **Neo4j**（图数据库）持久化存储。

## 🛠️ 安装与配置

### 1. 环境准备
建议使用 Conda 管理环境：
```bash
# 创建并激活环境
conda create -n YangtzeLLM python=3.10
conda activate YangtzeLLM

# 安装依赖
pip install -r requirements.txt