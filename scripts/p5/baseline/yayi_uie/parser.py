"""
输出解析模块

解析模型输出为结构化 JSON。
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .prompt import TaskType


@dataclass
class ParseResult:
    """解析结果
    
    Attributes:
        success: 解析是否成功
        data: 解析后的结构化数据
        raw_output: 原始模型输出
        error: 错误信息（如果解析失败）
    """
    success: bool
    data: Dict[str, Any]
    raw_output: str
    error: Optional[str] = None


class BaseOutputParser(ABC):
    """输出解析器基类
    
    所有任务类型的输出解析器都应继承此类。
    """
    
    @abstractmethod
    def parse(self, raw_output: str) -> ParseResult:
        """解析模型输出
        
        Args:
            raw_output: 模型原始输出
        
        Returns:
            解析结果
        """
        pass
    
    def _extract_json(self, text: str) -> Optional[str]:
        """从文本中提取 JSON 字符串
        
        尝试多种模式匹配 JSON 结构，支持嵌套。
        
        Args:
            text: 包含 JSON 的文本
        
        Returns:
            提取的 JSON 字符串，如果未找到则返回 None
        """
        if not text:
            return None
        
        def find_balanced(s: str, open_char: str, close_char: str) -> Optional[str]:
            """查找平衡的括号对"""
            start = s.find(open_char)
            if start == -1:
                return None
            
            depth = 0
            in_string = False
            escape = False
            
            for i, c in enumerate(s[start:], start):
                if escape:
                    escape = False
                    continue
                if c == '\\':
                    escape = True
                    continue
                if c == '"' and not escape:
                    in_string = not in_string
                    continue
                if in_string:
                    continue
                if c == open_char:
                    depth += 1
                elif c == close_char:
                    depth -= 1
                    if depth == 0:
                        return s[start:i+1]
            return None
        
        # 优先尝试数组（RE 任务通常返回数组）
        arr_json = find_balanced(text, '[', ']')
        if arr_json:
            return arr_json
        
        # 尝试对象
        obj_json = find_balanced(text, '{', '}')
        if obj_json:
            return obj_json
        
        return None
    
    def _normalize_text(self, text: str) -> str:
        """标准化文本
        
        去除多余空白和特殊字符。
        
        Args:
            text: 原始文本
        
        Returns:
            标准化后的文本
        """
        if not text:
            return ""
        # 去除首尾空白
        text = str(text).strip()
        # 合并多个空白为单个空格
        text = re.sub(r'\s+', ' ', text)
        return text
    
    def _try_parse_json(self, json_str: str) -> Optional[Any]:
        """尝试解析 JSON 字符串
        
        Args:
            json_str: JSON 字符串
        
        Returns:
            解析后的对象，如果解析失败则返回 None
        """
        if not json_str:
            return None
        
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass
        
        # 尝试修复常见的 JSON 格式问题
        # 1. 单引号替换为双引号
        fixed = json_str.replace("'", '"')
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        
        # 2. 处理尾部逗号
        fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
        try:
            return json.loads(fixed)
        except json.JSONDecodeError:
            pass
        
        return None


class NEROutputParser(BaseOutputParser):
    """NER 输出解析器
    
    解析 {类型: [实体]} 格式的输出。
    
    Example:
        >>> parser = NEROutputParser()
        >>> result = parser.parse('{"人物": ["张三"], "地点": ["北京"]}')
        >>> print(result.data)
        {'entities': [{'人物': ['张三'], '地点': ['北京']}]}
    """
    
    def parse(self, raw_output: str) -> ParseResult:
        """解析 NER 输出"""
        try:
            json_str = self._extract_json(raw_output)
            if not json_str:
                return ParseResult(
                    success=False,
                    data={"entities": []},
                    raw_output=raw_output,
                    error="未找到 JSON 结构",
                )
            
            data = self._try_parse_json(json_str)
            if data is None:
                return ParseResult(
                    success=False,
                    data={"entities": []},
                    raw_output=raw_output,
                    error="JSON 解析失败",
                )
            
            entities: Dict[str, List[str]] = {}
            
            def add_entity(entity_type: str, entity_value: Any) -> None:
                name = self._normalize_text(str(entity_value))
                if not name:
                    return
                values = entities.setdefault(entity_type, [])
                if name not in values:
                    values.append(name)
            
            def handle_mapping(mapping: Dict[str, Any]) -> None:
                for entity_type, entity_list in mapping.items():
                    if isinstance(entity_list, list):
                        for entity in entity_list:
                            add_entity(entity_type, entity)
                    elif entity_list:
                        add_entity(entity_type, entity_list)
            
            if isinstance(data, dict):
                handle_mapping(data)
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, dict):
                        handle_mapping(item)
            else:
                return ParseResult(
                    success=False,
                    data={"entities": []},
                    raw_output=raw_output,
                    error="NER JSON 结构不符合预期",
                )
            
            entity_groups = [entities] if entities else []
            
            return ParseResult(
                success=True,
                data={"entities": entity_groups},
                raw_output=raw_output,
            )
        except Exception as e:
            return ParseResult(
                success=False,
                data={"entities": []},
                raw_output=raw_output,
                error=str(e),
            )


class REOutputParser(BaseOutputParser):
    """RE 输出解析器
    
    解析 [{'relation':'', 'head':'', 'tail':''}] 格式的输出。
    
    Example:
        >>> parser = REOutputParser()
        >>> result = parser.parse("[{'relation': '位于', 'head': '张三', 'tail': '北京'}]")
        >>> print(result.data)
        {'triples': [{'subject': '张三', 'predicate': '位于', 'object': '北京'}]}
    """
    
    def parse(self, raw_output: str) -> ParseResult:
        """解析 RE 输出"""
        try:
            json_str = self._extract_json(raw_output)
            if not json_str:
                return ParseResult(
                    success=False,
                    data={"triples": []},
                    raw_output=raw_output,
                    error="未找到 JSON 结构",
                )
            
            data = self._try_parse_json(json_str)
            if data is None:
                return ParseResult(
                    success=False,
                    data={"triples": []},
                    raw_output=raw_output,
                    error="JSON 解析失败",
                )
            
            triples = []
            
            # 确保是列表
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                # 提取三元组字段（支持多种字段名）
                subject = self._normalize_text(
                    item.get("head", "") or item.get("subject", "") or item.get("头实体", "")
                )
                predicate = self._normalize_text(
                    item.get("relation", "") or item.get("predicate", "") or item.get("关系", "")
                )
                obj = self._normalize_text(
                    item.get("tail", "") or item.get("object", "") or item.get("尾实体", "")
                )
                
                if subject and predicate and obj:
                    triples.append({
                        "subject": subject,
                        "predicate": predicate,
                        "object": obj,
                    })
            
            return ParseResult(
                success=True,
                data={"triples": triples},
                raw_output=raw_output,
            )
        except Exception as e:
            return ParseResult(
                success=False,
                data={"triples": []},
                raw_output=raw_output,
                error=str(e),
            )


class EEOutputParser(BaseOutputParser):
    """EE 输出解析器
    
    解析 {角色: 论元} 格式的输出。
    
    Example:
        >>> parser = EEOutputParser()
        >>> result = parser.parse('{"事件类型": "洪水", "时间": "1998年", "地点": "长江"}')
        >>> print(result.data)
        {'events': [{'event_type': '洪水', 'arguments': {'时间': '1998年', '地点': '长江'}}]}
    """
    
    def parse(self, raw_output: str) -> ParseResult:
        """解析 EE 输出"""
        try:
            json_str = self._extract_json(raw_output)
            if not json_str:
                return ParseResult(
                    success=False,
                    data={"events": []},
                    raw_output=raw_output,
                    error="未找到 JSON 结构",
                )
            
            data = self._try_parse_json(json_str)
            if data is None:
                return ParseResult(
                    success=False,
                    data={"events": []},
                    raw_output=raw_output,
                    error="JSON 解析失败",
                )
            
            events = []
            
            # 处理单个事件或事件列表
            items = data if isinstance(data, list) else [data]
            
            for item in items:
                if not isinstance(item, dict):
                    continue
                
                # 提取事件类型
                event_type = self._normalize_text(
                    item.get("事件类型", "") or item.get("event_type", "") or item.get("type", "")
                )
                
                # 提取论元
                arguments = {}
                for role, value in item.items():
                    if role in ("事件类型", "event_type", "type"):
                        continue
                    normalized_value = self._normalize_text(str(value))
                    if normalized_value:
                        arguments[role] = normalized_value
                
                if event_type or arguments:
                    events.append({
                        "event_type": event_type,
                        "arguments": arguments,
                    })
            
            return ParseResult(
                success=True,
                data={"events": events},
                raw_output=raw_output,
            )
        except Exception as e:
            return ParseResult(
                success=False,
                data={"events": []},
                raw_output=raw_output,
                error=str(e),
            )


class OutputParserFactory:
    """输出解析器工厂
    
    根据任务类型返回对应的解析器实例。
    
    Example:
        >>> parser = OutputParserFactory.get_parser(TaskType.NER)
        >>> result = parser.parse('{"人物": ["张三"]}')
    """
    
    _parsers = {
        TaskType.NER: NEROutputParser,
        TaskType.RE: REOutputParser,
        TaskType.EE: EEOutputParser,
    }
    
    @classmethod
    def get_parser(cls, task_type: TaskType) -> BaseOutputParser:
        """获取指定任务类型的解析器
        
        Args:
            task_type: 任务类型
        
        Returns:
            对应的输出解析器实例
        
        Raises:
            ValueError: 不支持的任务类型
        """
        parser_class = cls._parsers.get(task_type)
        if not parser_class:
            raise ValueError(f"不支持的任务类型: {task_type}")
        return parser_class()
    
    @classmethod
    def register_parser(cls, task_type: TaskType, parser_class: type) -> None:
        """注册自定义解析器
        
        Args:
            task_type: 任务类型
            parser_class: 解析器类
        """
        cls._parsers[task_type] = parser_class
