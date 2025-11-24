import os
from dotenv import load_dotenv
load_dotenv()
# -------------------------------------------------------
# 🔥 核心修复：使用国内镜像加速下载 HuggingFace 模型
# -------------------------------------------------------
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import json
import networkx as nx
import matplotlib.pyplot as plt
import google.generativeai as genai # 导入Gemini库

# -------------------------------------------------------
# 修复 ImportError: 必须在导入 sentence_transformers 之前导入 numpy
# -------------------------------------------------------
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# ==========================================
# 配置区域
# ==========================================
# -------------------------------------------------------
# ⚠️ 请将 "YOUR_GEMINI_API_KEY" 替换为您的有效 Gemini API 密钥
# -------------------------------------------------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=GEMINI_API_KEY)

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
    print("正在进行知识抽取 (使用 Gemini)...")
    try:
        # 使用 Gemini-2.5-Flash 模型
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json"
            )
        )
        # Gemini 的返回在 response.text 中
        result = response.text
        return json.loads(result)
    except Exception as e:
        print(f"使用 Gemini 抽取失败: {e}")
        # 检查是否有关于API Key的错误
        if "API_KEY_INVALID" in str(e) or "permission" in str(e).lower():
             print("错误提示：您的 Gemini API Key 可能无效或未正确设置。")
        return {"entities": [], "relations": []}

# ==========================================
# 模块二：构建图谱
# ==========================================
def build_graph(kg_data):
    G = nx.DiGraph()
    if not kg_data or not kg_data.get('entities'):
        return G
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
        # 使用 try-except 避免图数据不一致导致的错误
        try:
            neighbors = list(G.neighbors(start_node))
            for neighbor in neighbors:
                edge_data = G.get_edge_data(start_node, neighbor)
                relation = edge_data.get('relation', '未知关系')
                context_triples.append(f"{start_node} --[{relation}]--> {neighbor}")

            predecessors = list(G.predecessors(start_node))
            for pred in predecessors:
                edge_data = G.get_edge_data(pred, start_node)
                relation = edge_data.get('relation', '未知关系')
                context_triples.append(f"{pred} --[{relation}]--> {start_node}")
        except nx.NetworkXError as e:
            print(f"检索节点 '{start_node}' 的邻居时出错: {e}")


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
    print("正在生成答案 (使用 Gemini)...")
    try:
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.5
            )
        )
        return response.text
    except Exception as e:
        print(f"使用 Gemini 生成答案失败: {e}")
        if "API_KEY_INVALID" in str(e) or "permission" in str(e).lower():
             print("错误提示：您的 Gemini API Key 可能无效或未正确设置。")
        return "抱歉，生成答案时遇到错误。"


# ==========================================
# 主程序
# ==========================================
if __name__ == "__main__":
    # 检查 API Key 是否已设置
    if 'YOUR_GEMINI_API_KEY' in GEMINI_API_KEY:
        print("="*50)
        print("‼️  请先在代码第 20 行设置您的 GEMINI_API_KEY")
        print("="*50)
        # API Key 未设置，直接退出
        exit()

    print(">>> STEP 1: 知识抽取")
    kg_data = extract_knowledge(RAW_TEXT)

    # 打印一下抽取结果，防止是空的
    if not kg_data or not kg_data.get('entities'):
        print("警告：知识抽取未返回有效数据，请检查API Key或模型调用。")
        # 使用备用Mock数据以继续运行
        print("使用备用Mock数据继续运行...")
        kg_data = {
            "entities": [
                {"name": "1998年长江全流域特大洪水", "type": "灾害事件"},
                {"name": "1954年大洪水", "type": "灾害事件"},
                {"name": "气候异常", "type": "原因"},
                {"name": "降雨集中", "type": "原因"},
                {"name": "生态破坏", "type": "原因"},
                {"name": "江西", "type": "地点"},
                {"name": "湖南", "type": "地点"},
                {"name": "湖北", "type": "地点"},
                {"name": "退田还湖", "type": "应对措施"},
                {"name": "加固堤防", "type": "应对措施"}
            ],
            "relations": [
                {"head": "1998年长江全流域特大洪水", "relation": "发生时间", "tail": "1998年6月中旬至9月上旬"},
                {"head": "1998年长江全流域特大洪水", "relation": "严重程度次于", "tail": "1954年大洪水"},
                {"head": "1998年长江全流域特大洪水", "relation": "主要原因", "tail": "气候异常"},
                {"head": "1998年长江全流域特大洪水", "relation": "主要原因", "tail": "降雨集中"},
                {"head": "1998年长江全流域特大洪水", "relation": "主要原因", "tail": "生态破坏"},
                {"head": "1998年长江全流域特大洪水", "relation": "淹没地区", "tail": "江西"},
                {"head": "1998年长江全流域特大洪水", "relation": "淹没地区", "tail": "湖南"},
                {"head": "1998年长江全流域特大洪水", "relation": "淹没地区", "tail": "湖北"},
                {"head": "1998年长江全流域特大洪水", "relation": "应对措施", "tail": "退田还湖"},
                {"head": "1998年长江全流域特大洪水", "relation": "应对措施", "tail": "加固堤防"}
            ]
        }


    print("\n>>> STEP 2: 构建图谱")
    G = build_graph(kg_data)

    print("\n>>> STEP 3: GraphRAG 语义检索")
    user_query = "1998年长江特大洪水的起因是什么？"
    print(f"用户提问: {user_query}")

    # 向量检索
    context = graph_retrieval_semantic(G, user_query)
    print(f"--- 检索到的上下文 ---\n{context}\n---------------------")

    if "未在知识库" not in context and "图谱为空" not in context:
        answer = generate_answer(user_query, context)
        print(f"\n>>> AI回答:\n{answer}")
    else:
        print("知识库中无相关信息，无法回答。")
