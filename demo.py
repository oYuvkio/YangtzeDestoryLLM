import os
# -------------------------------------------------------
# 🔥 核心修复：使用国内镜像加速下载 HuggingFace 模型
# -------------------------------------------------------
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import json
import networkx as nx
import matplotlib.pyplot as plt
from openai import OpenAI
from zhipuai import ZhipuAI  # 注意大小写：包名小写，类名大写

# -------------------------------------------------------
# 修复 ImportError: 必须在导入 sentence_transformers 之前导入 numpy
# -------------------------------------------------------
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ==========================================
# 配置区域
# ==========================================
API_KEY = "797f9a64b59202a44accbae216ba9596.AfDfJzdZcVDnL4jH"

client = ZhipuAI(api_key=API_KEY)

# ==========================================
# 全局加载模型 (修复作用域问题)
# ==========================================
print("正在加载 Embedding 模型，首次运行可能需要下载...")
# 使用一个更小的中文模型，下载更快，效果也不错
embedding_model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
# 模拟数据
RAW_TEXT = """
1998年长江全流域特大洪水是20世纪以来仅次于1954年的大洪水。
此次洪水发生于1998年6月中旬至9月上旬。
灾害主要由气候异常、降雨集中以及生态破坏导致。
洪水淹没了江西、湖南、湖北等省份的广大地区。
针对此次灾害，政府采取了退田还湖、加固堤防等应对措施。
"""

# ==========================================
# 模块一：基于LLM的知识抽取
# ==========================================
def extract_knowledge(text):
    prompt = f"""
    你是一个长江流域灾害领域的知识图谱构建专家。
    请从以下文本中抽取实体和关系，构建知识三元组。
    
    文本内容：
    {text}

    请严格遵循以下JSON格式输出：
    {{
        "entities": [
            {{"name": "实体名", "type": "实体类型"}}
        ],
        "relations": [
            {{"head": "头实体名", "relation": "关系", "tail": "尾实体名"}}
        ]
    }}
    """
    print("正在进行知识抽取...")
    try:
        response = client.chat.completions.create(
            model="glm-4.5-flash",
            messages=[
                {"role": "system", "content": "你是一个精准的信息抽取助手。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        result = response.choices[0].message.content
        return json.loads(result)
    except Exception as e:
        print(f"抽取失败: {e}")
        return {"entities": [], "relations": []}

# ==========================================
# 模块二：构建图谱
# ==========================================
def build_graph(kg_data):
    G = nx.DiGraph()
    for entity in kg_data['entities']:
        G.add_node(entity['name'], type=entity['type'])
    for rel in kg_data['relations']:
        G.add_edge(rel['head'], rel['tail'], relation=rel['relation'])
    return G

# ==========================================
# 模块三：GraphRAG (语义检索优化版)
# ==========================================
def get_embedding(text):
    return embedding_model.encode(text)

def graph_retrieval_semantic(G, query, threshold=0.4): # 稍微调低阈值，确保能匹配上
    """
    基于语义向量的检索
    """
    print(f"正在对查询进行向量化: {query}")
    query_vec = get_embedding(query).reshape(1, -1)

    found_nodes = []
    node_list = list(G.nodes())

    if not node_list:
        return "图谱为空"

    node_vecs = embedding_model.encode(node_list)

    # 计算相似度
    similarities = cosine_similarity(query_vec, node_vecs)[0]

    for i, score in enumerate(similarities):
        # 打印相似度日志，方便你观察阈值设置是否合理
        # print(f"  - 节点: {node_list[i]} | 相似度: {score:.4f}")
        if score > threshold:
            node_name = node_list[i]
            print(f"语义匹配成功: {node_name} (相似度: {score:.4f})")
            found_nodes.append(node_name)

    if not found_nodes:
        return "未在知识库中找到相关实体。"

    # 检索子图 (获取结构化上下文)
    context_triples = []
    for start_node in found_nodes:
        neighbors = list(G.neighbors(start_node))
        for neighbor in neighbors:
            edge_data = G.get_edge_data(start_node, neighbor)
            relation = edge_data['relation']
            context_triples.append(f"{start_node} --[{relation}]--> {neighbor}")

        predecessors = list(G.predecessors(start_node))
        for pred in predecessors:
            edge_data = G.get_edge_data(pred, start_node)
            relation = edge_data['relation']
            context_triples.append(f"{pred} --[{relation}]--> {start_node}")

    if not context_triples:
        return "找到了实体，但该实体没有关联的三元组信息。"

    return "\n".join(list(set(context_triples)))

def generate_answer(query, graph_context):
    prompt = f"""
    你是一个基于知识图谱的问答助手。
    请根据以下检索到的结构化知识（三元组）回答用户问题。
    
    【检索到的知识图谱路径】：
    {graph_context}
    
    【用户问题】：
    {query}
    
    请基于证据回答。
    """
    response = client.chat.completions.create(
        model="glm-4.5-flash", # 确保这里也用智谱的模型
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.5
    )
    return response.choices[0].message.content

# ==========================================
# 主程序
# ==========================================
if __name__ == "__main__":
    print(">>> STEP 1: 知识抽取")
    kg_data = extract_knowledge(RAW_TEXT)

    # 打印一下抽取结果，防止是空的
    if not kg_data['entities']:
        print("警告：知识抽取未返回数据，使用备用Mock数据。")
        # ... (此处可以填入之前的Mock数据作为保底，省略以节省篇幅)

    print("\n>>> STEP 2: 构建图谱")
    G = build_graph(kg_data)

    print("\n>>> STEP 3: GraphRAG 语义检索")
    user_query = "1998年长江特大洪水的起因是什么？"
    print(f"用户提问: {user_query}")

    # 向量检索
    context = graph_retrieval_semantic(G, user_query)
    print(f"--- 检索到的上下文 ---\n{context}\n---------------------")

    if "未在知识库" not in context:
        answer = generate_answer(user_query, context)
        print(f"\n>>> AI回答:\n{answer}")
    else:
        print("知识库中无相关信息。")