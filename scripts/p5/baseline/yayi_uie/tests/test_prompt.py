"""
提示词构建器单元测试
"""

import pytest
from hypothesis import given, settings, strategies as st
from scripts.p5.baseline.yayi_uie.prompt import (
    TaskType,
    TBoxSchema,
    NERPromptBuilder,
    REPromptBuilder,
    EEPromptBuilder,
    PromptBuilderFactory,
    BasePromptBuilder,
)


class TestTBoxSchema:
    """TBox Schema 测试"""
    
    def test_from_tbox_json(self):
        """测试从 TBox JSON 创建 Schema"""
        tbox_data = {
            "classes": [{"name": "人物"}, {"name": "地点"}],
            "relations": [{"name": "位于"}, {"name": "工作于"}],
            "attributes": [{"name": "时间"}, {"name": "原因"}],
        }
        
        schema = TBoxSchema.from_tbox_json(tbox_data)
        
        assert "人物" in schema.entity_types
        assert "地点" in schema.entity_types
        assert "位于" in schema.relation_types
        assert "工作于" in schema.relation_types
        assert "时间" in schema.event_roles
        assert "原因" in schema.event_roles
    
    def test_default_event_roles(self):
        """测试默认事件角色"""
        tbox_data = {
            "classes": [{"name": "人物"}],
            "relations": [{"name": "位于"}],
        }
        
        schema = TBoxSchema.from_tbox_json(tbox_data)
        
        # 没有 attributes 时应使用默认角色
        assert len(schema.event_roles) > 0
        assert "事件类型" in schema.event_roles


class TestNERPromptBuilder:
    """NER 提示词构建器测试"""
    
    def setup_method(self):
        self.builder = NERPromptBuilder()
    
    def test_build_with_default_types(self):
        """测试使用默认实体类型"""
        prompt = self.builder.build("张三在北京工作。")
        
        assert "张三在北京工作" in prompt
        assert "实体抽取" in prompt
        assert BasePromptBuilder.HUMAN_TOKEN in prompt
        assert BasePromptBuilder.ASSISTANT_TOKEN in prompt
    
    def test_build_with_custom_schema(self):
        """测试使用自定义 Schema"""
        schema = TBoxSchema(entity_types=["人物", "组织"])
        prompt = self.builder.build("张三在阿里巴巴工作。", schema)
        
        assert "人物" in prompt
        assert "组织" in prompt


class TestREPromptBuilder:
    """RE 提示词构建器测试"""
    
    def setup_method(self):
        self.builder = REPromptBuilder()
    
    def test_build_with_default_relations(self):
        """测试使用默认关系类型"""
        prompt = self.builder.build("张三在北京工作。")
        
        assert "张三在北京工作" in prompt
        assert "关系抽取" in prompt
        assert "relation" in prompt
        assert "head" in prompt
        assert "tail" in prompt
    
    def test_build_with_custom_schema(self):
        """测试使用自定义 Schema"""
        schema = TBoxSchema(relation_types=["位于", "工作于", "毕业于"])
        prompt = self.builder.build("张三在北京大学毕业。", schema)
        
        assert "位于" in prompt
        assert "工作于" in prompt
        assert "毕业于" in prompt


class TestEEPromptBuilder:
    """EE 提示词构建器测试"""
    
    def setup_method(self):
        self.builder = EEPromptBuilder()
    
    def test_build_with_default_roles(self):
        """测试使用默认事件角色"""
        prompt = self.builder.build("1998年长江发生洪水。")
        
        assert "1998年长江发生洪水" in prompt
        assert "论元角色" in prompt
    
    def test_build_with_custom_schema(self):
        """测试使用自定义 Schema"""
        schema = TBoxSchema(event_roles=["事件类型", "发生时间", "发生地点", "影响范围"])
        prompt = self.builder.build("1998年长江发生洪水。", schema)
        
        assert "发生时间" in prompt
        assert "发生地点" in prompt


class TestPromptBuilderFactory:
    """提示词构建器工厂测试"""
    
    def test_get_ner_builder(self):
        """测试获取 NER 构建器"""
        builder = PromptBuilderFactory.get_builder(TaskType.NER)
        assert isinstance(builder, NERPromptBuilder)
    
    def test_get_re_builder(self):
        """测试获取 RE 构建器"""
        builder = PromptBuilderFactory.get_builder(TaskType.RE)
        assert isinstance(builder, REPromptBuilder)
    
    def test_get_ee_builder(self):
        """测试获取 EE 构建器"""
        builder = PromptBuilderFactory.get_builder(TaskType.EE)
        assert isinstance(builder, EEPromptBuilder)


@given(text=st.text(min_size=1, max_size=200))
@settings(max_examples=50)
def test_prompt_format_correctness(text):
    """Property 1: Prompt Format Correctness"""
    builders = [
        PromptBuilderFactory.get_builder(TaskType.NER),
        PromptBuilderFactory.get_builder(TaskType.RE),
        PromptBuilderFactory.get_builder(TaskType.EE),
    ]
    for builder in builders:
        prompt = builder.build(text)
        assert prompt.startswith(BasePromptBuilder.HUMAN_TOKEN)
        assert prompt.endswith(BasePromptBuilder.ASSISTANT_TOKEN)
        assert f"文本：{text}" in prompt


@given(
    entities=st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10), min_size=1, max_size=5),
    relations=st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10), min_size=1, max_size=5),
    roles=st.lists(st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=10), min_size=1, max_size=5),
)
@settings(max_examples=30)
def test_schema_integration_in_prompts(entities, relations, roles):
    """Property 2: Schema Integration in Prompts"""
    schema = TBoxSchema(
        entity_types=entities,
        relation_types=relations,
        event_roles=roles,
    )
    ner_prompt = NERPromptBuilder().build("text", schema)
    re_prompt = REPromptBuilder().build("text", schema)
    ee_prompt = EEPromptBuilder().build("text", schema)
    
    for etype in entities:
        assert etype in ner_prompt
    for relation in relations:
        assert relation in re_prompt
    for role in roles:
        assert role in ee_prompt
