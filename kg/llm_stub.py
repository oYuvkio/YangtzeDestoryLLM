from typing import List, Tuple

def draft_with_llm(question: str, triples: List[Tuple[str, str, str]]) -> str:
    """
    占位函数：当前仅用模板，后续可替换为真实LLM调用。
    triples 形如 (src, rel, dst)。
    """
    facts = "; ".join([f"{s} -{r}-> {o}" for s, r, o in triples[:8]])
    return f"问题: {question}。依据图谱事实: {facts}。请结合事实生成回答。"
