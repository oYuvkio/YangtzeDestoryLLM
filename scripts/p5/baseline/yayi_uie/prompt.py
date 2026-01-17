"""
提示词构建模块

根据任务类型和 Schema 构建符合 YAYI-UIE 格式的提示词。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class TaskType(Enum):
    """抽取任务类型"""
    NER = "ner"   # 命名实体识别
    RE = "re"     # 关系抽取
    EE = "ee"     # 事件抽取


@dataclass
class TBoxSchema:
    """TBox 模式定义
    
    Attributes:
        entity_types: 实体类型列表，用于 NER 任务
        relation_types: 关系类型列表，用于 RE 任务
        event_roles: 事件论元角色列表，用于 EE 任务
    """
    entity_types: List[str] = field(default_factory=list)
    relation_types: List[str] = field(default_factory=list)
    event_roles: List[str] = field(default_factory=list)
    
    @classmethod
    def from_tbox_json(cls, tbox_data: dict) -> "TBoxSchema":
        """从 TBox JSON 数据创建 Schema
        
        Args:
            tbox_data: TBox JSON 数据，包含 classes, relations, attributes
        
        Returns:
            TBoxSchema 实例
        """
        entity_types = []
        relation_types = []
        event_roles = []
        
        # 从 classes 提取实体类型
        for c in tbox_data.get("classes", []):
            name = c.get("name", "")
            if name:
                entity_types.append(name)
        
        # 从 relations 提取关系类型
        for r in tbox_data.get("relations", []):
            name = r.get("name", "")
            if name:
                relation_types.append(name)
        
        # 从 attributes 提取事件角色（属性名作为角色）
        for a in tbox_data.get("attributes", []):
            name = a.get("name", "")
            if name:
                event_roles.append(name)
        
        # 如果没有 event_roles，使用默认角色
        if not event_roles:
            event_roles = ["事件类型", "时间", "地点", "原因", "影响", "措施"]
        
        return cls(
            entity_types=entity_types,
            relation_types=relation_types,
            event_roles=event_roles,
        )


class BasePromptBuilder(ABC):
    """提示词构建器基类
    
    所有任务类型的提示词构建器都应继承此类。
    """
    
    # YAYI-UIE 特殊标记
    HUMAN_TOKEN = "<reserved_13>"
    ASSISTANT_TOKEN = "<reserved_14>"
    
    @abstractmethod
    def build(self, text: str, schema: Optional[TBoxSchema] = None) -> str:
        """构建提示词
        
        Args:
            text: 待抽取的文本
            schema: TBox 模式定义，可选
        
        Returns:
            构建好的提示词
        """
        pass
    
    def wrap_prompt(self, prompt: str) -> str:
        """添加特殊标记包装
        
        Args:
            prompt: 原始提示词
        
        Returns:
            包装后的提示词
        """
        return f"{self.HUMAN_TOKEN}{prompt}{self.ASSISTANT_TOKEN}"


class NERPromptBuilder(BasePromptBuilder):
    """NER 任务提示词构建器
    
    构建命名实体识别任务的提示词，格式：
    文本：{text}
    【实体抽取】抽取文本中可能存在的实体，并以json{类型1/类型2：[实体]}格式输出。
    """
    
    # 默认实体类型
    DEFAULT_ENTITY_TYPES = ["人物", "地点", "机构", "时间", "事件"]
    
    def build(self, text: str, schema: Optional[TBoxSchema] = None) -> str:
        """构建 NER 提示词"""
        if schema and schema.entity_types:
            types_str = "/".join(schema.entity_types)
        else:
            types_str = "/".join(self.DEFAULT_ENTITY_TYPES)
        
        prompt = (
            f"文本：{text}\n"
            f"【实体抽取】抽取文本中可能存在的实体，"
            f"并以json{{{types_str}：[实体]}}格式输出。"
        )
        return self.wrap_prompt(prompt)


class REPromptBuilder(BasePromptBuilder):
    """RE 任务提示词构建器
    
    构建关系抽取任务的提示词，格式：
    文本：{text}
    【关系抽取】已知关系列表是[关系1,关系2,...]。根据关系列表抽取关系三元组，
    按照json[{'relation':'', 'head':'', 'tail':''}, ]的格式输出。
    """
    
    # 默认关系类型
    DEFAULT_RELATION_TYPES = ["位于", "发生于", "导致", "影响", "措施"]
    
    def build(self, text: str, schema: Optional[TBoxSchema] = None) -> str:
        """构建 RE 提示词"""
        if schema and schema.relation_types:
            relations_str = ",".join(schema.relation_types)
        else:
            relations_str = ",".join(self.DEFAULT_RELATION_TYPES)
        
        prompt = (
            f"文本：{text}\n"
            f"【关系抽取】已知关系列表是[{relations_str}]。"
            f"根据关系列表抽取关系三元组，"
            f"按照json[{{'relation':'', 'head':'', 'tail':''}}, ]的格式输出。"
        )
        return self.wrap_prompt(prompt)


class EEPromptBuilder(BasePromptBuilder):
    """EE 任务提示词构建器
    
    构建事件抽取任务的提示词，格式：
    文本：{text}
    已知论元角色列表是[角色1,角色2,...]，请根据论元角色列表从给定的输入中抽取可能的论元，
    以json{角色:论元,}格式输出。
    """
    
    # 默认事件角色
    DEFAULT_EVENT_ROLES = ["事件类型", "时间", "地点", "原因", "影响", "措施"]
    
    def build(self, text: str, schema: Optional[TBoxSchema] = None) -> str:
        """构建 EE 提示词"""
        if schema and schema.event_roles:
            roles_str = ",".join(schema.event_roles)
        else:
            roles_str = ",".join(self.DEFAULT_EVENT_ROLES)
        
        prompt = (
            f"文本：{text}\n"
            f"已知论元角色列表是[{roles_str}]，"
            f"请根据论元角色列表从给定的输入中抽取可能的论元，"
            f"以json{{角色:论元,}}格式输出。"
        )
        return self.wrap_prompt(prompt)


class PromptBuilderFactory:
    """提示词构建器工厂
    
    根据任务类型返回对应的构建器实例。
    
    Example:
        >>> builder = PromptBuilderFactory.get_builder(TaskType.NER)
        >>> prompt = builder.build("张三在北京工作。")
    """
    
    _builders = {
        TaskType.NER: NERPromptBuilder,
        TaskType.RE: REPromptBuilder,
        TaskType.EE: EEPromptBuilder,
    }
    
    @classmethod
    def get_builder(cls, task_type: TaskType) -> BasePromptBuilder:
        """获取指定任务类型的构建器
        
        Args:
            task_type: 任务类型
        
        Returns:
            对应的提示词构建器实例
        
        Raises:
            ValueError: 不支持的任务类型
        """
        builder_class = cls._builders.get(task_type)
        if not builder_class:
            raise ValueError(f"不支持的任务类型: {task_type}")
        return builder_class()
    
    @classmethod
    def register_builder(cls, task_type: TaskType, builder_class: type) -> None:
        """注册自定义构建器
        
        Args:
            task_type: 任务类型
            builder_class: 构建器类
        """
        cls._builders[task_type] = builder_class
