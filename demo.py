import os
import json
import networkx as nx


import matplotlib.pyplot as plt
from openai import OpenAI
from zai import ZhipuAiClient
# ==========================================
# 配置区域
# ==========================================
# 建议使用支持OpenAI格式的API，如Kimi (Moonshot), DeepSeek, 或 OpenAI
# 请在此处填入你的 API Key
API_KEY = "797f9a64b59202a44accbae216ba9596.AfDfJzdZcVDnL4jH"
BASE_URL = "" # 如果用Kimi，使用此URL；如果是OpenAI则去掉

# client = OpenAI(
#     api_key=API_KEY,
#     base_url=BASE_URL
# )
client = ZhipuAiClient(api_key=API_KEY)

# 模拟一段非结构化文本数据（来源：你的PDF提及的年鉴或报告风格）
RAW_TEXT = """
1998年长江全流域特大洪水是20世纪以来仅次于1954年的大洪水。
此次洪水发生于1998年6月中旬至9月上旬。
灾害主要由气候异常、降雨集中以及生态破坏导致。
洪水淹没了江西、湖南、湖北等省份的广大地区。
针对此次灾害，政府采取了退田还湖、加固堤防等应对措施。
"""

# ==========================================
# 模块一：基于LLM的知识抽取 (对应创新点一)
# ==========================================
def extract_knowledge(text):
    """
    利用Prompt工程，引导LLM提取实体和关系，输出JSON格式。
    这里体现了 'Prompt + 思维链' 的思想。
    """
    prompt = f"""
    你是一个长江流域灾害领域的知识图谱构建专家。
    请从以下文本中抽取实体和关系，构建知识三元组。
    
    文本内容：
    {text}

    请严格遵循以下JSON格式输出，不要包含Markdown标记或其他废话：
    {{
        "entities": [
            {{"name": "实体名", "type": "实体类型(如:灾害事件, 时间, 地点, 原因, 措施)"}}
        ],
        "relations": [
            {{"head": "头实体名", "relation": "关系(如:发生于, 导致, 影响, 采取)", "tail": "尾实体名"}}
        ]
    }}
    """

    print("正在进行知识抽取...")
    try:
        response = client.chat.completions.create(
            model="glm-4.5-flash", # 或 gpt-3.5-turbo, deepseek-chat
            messages=[
                {"role": "system", "content": "你是一个精准的信息抽取助手。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1, # 低温度保证输出稳定
            response_format={"type": "json_object"} # 强制JSON模式(如果模型支持)
        )
        result = response.choices[0].message.content
        return json.loads(result)
    except Exception as e:
        print(f"抽取失败: {e}")
        # 为了演示代码能跑通，如果API失败，返回一个Mock数据
        return {
            "entities": [
                {"name": "1998年长江全流域特大洪水", "type": "灾害事件"},
                {"name": "1998年6月中旬至9月上旬", "type": "时间"},
                {"name": "气候异常", "type": "原因"},
                {"name": "江西", "type": "地点"},
                {"name": "退田还湖", "type": "措施"}
            ],
            "relations": [
                {"head": "1998年长江全流域特大洪水", "relation": "发生于", "tail": "1998年6月中旬至9月上旬"},
                {"head": "气候异常", "relation": "导致", "tail": "1998年长江全流域特大洪水"},
                {"head": "1998年长江全流域特大洪水", "relation": "影响", "tail": "江西"},
                {"head": "1998年长江全流域特大洪水", "relation": "采取", "tail": "退田还湖"}
            ]
        }

# ==========================================
# 模块二：构建图谱 (简单模拟Neo4j)
# ==========================================
def build_graph(kg_data):
    G = nx.DiGraph()

    for entity in kg_data['entities']:
        G.add_node(entity['name'], type=entity['type'])

    for rel in kg_data['relations']:
        G.add_edge(rel['head'], rel['tail'], relation=rel['relation'])

    return G

def visualize_graph(G):
    """可视化图谱（仅用于调试）"""
    pos = nx.spring_layout(G)
    plt.figure(figsize=(10, 6))
    nx.draw(G, pos, with_labels=True, node_color='lightblue', node_size=2000, font_size=10, font_family='sans-serif')
    edge_labels = nx.get_edge_attributes(G, 'relation')
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
    plt.title("长江灾害知识图谱 (Demo)")
    plt.show()

# ==========================================
# 模块三：GraphRAG 检索与问答 (对应创新点二)
# ==========================================
def graph_retrieval(G, query, hop=1):
    """
    简单的图检索算法：
    1. 在Query中识别关键词（这里简化为匹配图中的节点）
    2. 检索该节点及其邻居（子图检索）
    """
    found_nodes = []
    for node in G.nodes():
        if node in query: # 简单的关键词匹配，实际可用向量相似度
            found_nodes.append(node)

    if not found_nodes:
        return "未在知识库中找到相关实体。"

    # 检索子图 (Innovation: 获取结构化上下文)
    context_triples = []
    for start_node in found_nodes:
        # 获取直接邻居 (1-hop)
        neighbors = list(G.neighbors(start_node))
        for neighbor in neighbors:
            edge_data = G.get_edge_data(start_node, neighbor)
            relation = edge_data['relation']
            context_triples.append(f"{start_node} --[{relation}]--> {neighbor}")

        # 获取指向该节点的边 (反向关系)
        predecessors = list(G.predecessors(start_node))
        for pred in predecessors:
            edge_data = G.get_edge_data(pred, start_node)
            relation = edge_data['relation']
            context_triples.append(f"{pred} --[{relation}]--> {start_node}")

    return "\n".join(list(set(context_triples)))

def generate_answer(query, graph_context):
    """
    RAG生成：结合图谱检索到的结构化知识回答
    """
    prompt = f"""
    你是一个基于知识图谱的问答助手。
    请根据以下检索到的结构化知识（三元组）回答用户问题。
    
    【检索到的知识图谱路径】：
    {graph_context}
    
    【用户问题】：
    {query}
    
    请基于证据回答，如果知识不足，请说明。回答要有条理。
    """

    response = client.chat.completions.create(
        model="moonshot-v1-8k",
        messages=[
            {"role": "user", "content": prompt}
        ],
        temperature=0.5
    )
    return response.choices[0].message.content

# ==========================================
# 主程序流程
# ==========================================
if __name__ == "__main__":
    print(">>> STEP 1: 知识抽取 (Innovation 1)")
    kg_data = extract_knowledge(RAW_TEXT)
    print("抽取结果:", json.dumps(kg_data, ensure_ascii=False, indent=2))

    print("\n>>> STEP 2: 构建图谱")
    G = build_graph(kg_data)
    # visualize_graph(G) # 如果在Jupyter或本地运行，取消注释可看到图

    print("\n>>> STEP 3: GraphRAG 问答 (Innovation 2)")
    user_query = "1998年长江特大洪水的起因是什么？采取了什么措施？"
    print(f"用户提问: {user_query}")

    # 3.1 检索
    context = graph_retrieval(G, user_query)
    print(f"--- 图检索到的结构化知识 ---\n{context}\n-------------------------")

    # 3.2 生成
    if "未在知识库" not in context:
        answer = generate_answer(user_query, context)
        print(f"\n>>> AI回答:\n{answer}")
    else:
        print("知识库中无相关信息，无法回答。")