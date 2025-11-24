# kg/prompts.py
EXTRACT_PROMPT_TEMPLATE = """
你是一个长江流域灾害专家。
请从文本中抽取实体和关系。
文本：{text}
格式要求：JSON...
"""

# kg/extractor.py
from .prompts import EXTRACT_PROMPT_TEMPLATE
prompt = EXTRACT_PROMPT_TEMPLATE.format(text=text)