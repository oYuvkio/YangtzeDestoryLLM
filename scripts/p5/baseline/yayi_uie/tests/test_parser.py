"""
输出解析器单元测试
"""

import json

import pytest
from hypothesis import given, settings, strategies as st
from scripts.p5.baseline.yayi_uie.parser import (
    NEROutputParser,
    REOutputParser,
    EEOutputParser,
    OutputParserFactory,
)
from scripts.p5.baseline.yayi_uie.prompt import TaskType


class TestNEROutputParser:
    """NER 输出解析器测试"""
    
    def setup_method(self):
        self.parser = NEROutputParser()
    
    def test_parse_simple_output(self):
        """测试简单输出解析"""
        raw = '{"人物": ["张三", "李四"], "地点": ["北京"]}'
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["entities"]) == 1
        
        entity_map = result.data["entities"][0]
        assert "人物" in entity_map
        assert "地点" in entity_map
        assert "张三" in entity_map["人物"]
        assert "李四" in entity_map["人物"]
        assert "北京" in entity_map["地点"]
    
    def test_parse_with_prefix_text(self):
        """测试带前缀文本的输出"""
        raw = '根据文本分析，实体如下：{"人物": ["张三"]}'
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["entities"]) == 1
        entity_map = result.data["entities"][0]
        assert entity_map["人物"] == ["张三"]
    
    def test_parse_single_quotes(self):
        """测试单引号 JSON"""
        raw = "{'人物': ['张三']}"
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["entities"]) == 1
        entity_map = result.data["entities"][0]
        assert "张三" in entity_map.get("人物", [])
    
    def test_parse_empty_output(self):
        """测试空输出"""
        raw = ""
        result = self.parser.parse(raw)
        
        assert result.success is False
        assert result.data["entities"] == []
    
    def test_parse_no_json(self):
        """测试无 JSON 结构"""
        raw = "没有找到任何实体"
        result = self.parser.parse(raw)
        
        assert result.success is False


class TestREOutputParser:
    """RE 输出解析器测试"""
    
    def setup_method(self):
        self.parser = REOutputParser()
    
    def test_parse_array_output(self):
        """测试数组格式输出"""
        raw = '[{"relation": "位于", "head": "张三", "tail": "北京"}]'
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["triples"]) == 1
        
        triple = result.data["triples"][0]
        assert triple["subject"] == "张三"
        assert triple["predicate"] == "位于"
        assert triple["object"] == "北京"
    
    def test_parse_multiple_triples(self):
        """测试多个三元组"""
        raw = '''[
            {"relation": "位于", "head": "张三", "tail": "北京"},
            {"relation": "工作于", "head": "李四", "tail": "阿里巴巴"}
        ]'''
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["triples"]) == 2
    
    def test_parse_chinese_keys(self):
        """测试中文键名"""
        raw = '[{"关系": "位于", "头实体": "张三", "尾实体": "北京"}]'
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["triples"]) == 1
    
    def test_parse_nested_json(self):
        """测试嵌套 JSON"""
        raw = '前缀文本 [{"relation": "位于", "head": "张三", "tail": "北京", "extra": {"key": "value"}}] 后缀'
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["triples"]) == 1


class TestEEOutputParser:
    """EE 输出解析器测试"""
    
    def setup_method(self):
        self.parser = EEOutputParser()
    
    def test_parse_event_output(self):
        """测试事件输出解析"""
        raw = '{"事件类型": "洪水", "时间": "1998年", "地点": "长江流域"}'
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["events"]) == 1
        
        event = result.data["events"][0]
        assert event["event_type"] == "洪水"
        assert event["arguments"]["时间"] == "1998年"
        assert event["arguments"]["地点"] == "长江流域"
    
    def test_parse_event_list(self):
        """测试事件列表"""
        raw = '[{"事件类型": "洪水", "时间": "1998年"}, {"事件类型": "地震", "时间": "2008年"}]'
        result = self.parser.parse(raw)
        
        assert result.success is True
        assert len(result.data["events"]) == 2


class TestOutputParserFactory:
    """解析器工厂测试"""
    
    def test_get_ner_parser(self):
        """测试获取 NER 解析器"""
        parser = OutputParserFactory.get_parser(TaskType.NER)
        assert isinstance(parser, NEROutputParser)
    
    def test_get_re_parser(self):
        """测试获取 RE 解析器"""
        parser = OutputParserFactory.get_parser(TaskType.RE)
        assert isinstance(parser, REOutputParser)
    
    def test_get_ee_parser(self):
        """测试获取 EE 解析器"""
        parser = OutputParserFactory.get_parser(TaskType.EE)
        assert isinstance(parser, EEOutputParser)


@given(
    data=st.dictionaries(
        keys=st.text(alphabet="abcxyz", min_size=1, max_size=6),
        values=st.lists(st.text(alphabet="abcxyz123", min_size=1, max_size=8), min_size=1, max_size=4),
        min_size=1,
        max_size=4,
    )
)
@settings(max_examples=30)
def test_output_parsing_round_trip_ner(data):
    """Property 3: Output Parsing Round-Trip Consistency (NER)"""
    parser = NEROutputParser()
    raw = json.dumps(data, ensure_ascii=False)
    result = parser.parse(raw)
    
    expected = {
        (parser._normalize_text(entity), entity_type)
        for entity_type, entities in data.items()
        for entity in entities
    }
    entity_map = result.data["entities"][0] if result.data["entities"] else {}
    actual = set()
    for entity_type, entities in entity_map.items():
        if isinstance(entities, list):
            for entity in entities:
                actual.add((entity, entity_type))
    assert result.success is True
    assert actual == expected


@given(
    triples=st.lists(
        st.fixed_dictionaries(
            {
                "relation": st.text(alphabet="abcxyz", min_size=1, max_size=6),
                "head": st.text(alphabet="abcxyz123", min_size=1, max_size=8),
                "tail": st.text(alphabet="abcxyz123", min_size=1, max_size=8),
            }
        ),
        min_size=1,
        max_size=5,
    )
)
@settings(max_examples=30)
def test_output_parsing_round_trip_re(triples):
    """Property 3: Output Parsing Round-Trip Consistency (RE)"""
    parser = REOutputParser()
    raw = json.dumps(triples, ensure_ascii=False)
    result = parser.parse(raw)
    
    expected = {
        (
            parser._normalize_text(item["head"]),
            parser._normalize_text(item["relation"]),
            parser._normalize_text(item["tail"]),
        )
        for item in triples
    }
    actual = {
        (t["subject"], t["predicate"], t["object"])
        for t in result.data["triples"]
    }
    assert result.success is True
    assert actual == expected


@given(
    events=st.lists(
        st.fixed_dictionaries(
            {
                "事件类型": st.text(alphabet="abcxyz", min_size=1, max_size=6),
                "时间": st.text(alphabet="0123456789", min_size=1, max_size=6),
                "地点": st.text(alphabet="abcxyz", min_size=1, max_size=6),
            }
        ),
        min_size=1,
        max_size=3,
    )
)
@settings(max_examples=20)
def test_output_parsing_round_trip_ee(events):
    """Property 3: Output Parsing Round-Trip Consistency (EE)"""
    parser = EEOutputParser()
    raw = json.dumps(events, ensure_ascii=False)
    result = parser.parse(raw)
    assert result.success is True
    
    normalized = []
    for item in events:
        event_type = parser._normalize_text(item.get("事件类型", ""))
        arguments = {
            k: parser._normalize_text(v) for k, v in item.items() if k != "事件类型"
        }
        normalized.append((event_type, arguments))
    
    parsed = [
        (e["event_type"], e["arguments"])
        for e in result.data["events"]
    ]
    assert parsed == normalized


@given(
    triples=st.lists(
        st.fixed_dictionaries(
            {
                "relation": st.text(alphabet="abc", min_size=1, max_size=5),
                "head": st.text(alphabet="abc", min_size=1, max_size=5),
                "tail": st.text(alphabet="abc", min_size=1, max_size=5),
            }
        ),
        min_size=1,
        max_size=3,
    )
)
@settings(max_examples=20)
def test_malformed_json_fallback(triples):
    """Property 4: Malformed JSON Fallback"""
    parser = REOutputParser()
    raw = str(triples)  # 使用单引号的 Python repr
    result = parser.parse(raw)
    assert result.success is True
    assert len(result.data["triples"]) == len(triples)


@given(text=st.text(alphabet="abcdef123456", min_size=1).filter(lambda s: "{" not in s and "[" not in s))
@settings(max_examples=20)
def test_parse_failure_safety(text):
    """Property 5: Parse Failure Safety"""
    parser = NEROutputParser()
    result = parser.parse(text)
    assert result.success is False
    assert result.error is not None
    assert result.data["entities"] == []


@given(text=st.text(max_size=200))
@settings(max_examples=30)
def test_normalization_idempotence(text):
    """Property 6: Text Normalization Idempotence"""
    parser = REOutputParser()
    once = parser._normalize_text(text)
    twice = parser._normalize_text(once)
    assert once == twice
