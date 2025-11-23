# 文件路径: kg/llm.py
import os
from zhipuai import ZhipuAI

# 从环境变量或直接配置 API KEY
API_KEY = "797f9a64b59202a44accbae216ba9596.AfDfJzdZcVDnL4jH"  # 你的Key
client = ZhipuAI(api_key=API_KEY)

def chat_with_llm(prompt: str, system_prompt: str = "你是一个乐于助人的助手。", json_mode: bool = False) -> str:
    """封装智谱AI调用"""
    try:
        response = client.chat.completions.create(
            model="glm-4.5-flash",  # 或者 glm-4
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1 if json_mode else 0.7,
            response_format={"type": "json_object"} if json_mode else None
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"LLM调用失败: {e}")
        return ""

def draft_answer(question: str, evidence: list) -> str:
    """基于检索到的三元组生成答案"""
    # 将三元组列表转换为文本描述
    facts = "\n".join([f"- {s} {r} {o}" for s, r, o in evidence])
    
    prompt = f"""
    请根据以下检索到的长江灾害领域知识图谱信息，回答用户的问题。
    如果信息不足，请实事求是地说明。
    
    【知识证据】：
    {facts}
    
    【用户问题】：
    {question}
    
    请生成一段连贯、准确的回答，并引用证据中的关键信息。
    """
    return chat_with_llm(prompt, system_prompt="你是一个基于知识图谱的灾害问答专家。")