"""
工具函数单元测试
"""

import pytest
from scripts.p5.baseline.yayi_uie.utils import (
    normalize_text,
    normalize_text_light,
    pick_doc_id,
    pick_source_text,
    compute_f1,
)


class TestNormalizeText:
    """文本标准化测试"""
    
    def test_basic_normalization(self):
        """测试基本标准化"""
        assert normalize_text("  Hello World  ") == "helloworld"
        assert normalize_text("张三") == "张三"
    
    def test_remove_punctuation(self):
        """测试移除标点"""
        assert normalize_text("你好，世界！") == "你好世界"
        assert normalize_text("Hello, World!") == "helloworld"
    
    def test_preserve_punctuation(self):
        """测试保留标点"""
        assert normalize_text("你好，世界", remove_punctuation=False) == "你好，世界"
    
    def test_empty_string(self):
        """测试空字符串"""
        assert normalize_text("") == ""
        assert normalize_text(None) == ""


class TestNormalizeTextLight:
    """轻量级文本标准化测试"""
    
    def test_basic(self):
        """测试基本功能"""
        assert normalize_text_light("  Hello  World  ") == "Hello World"
    
    def test_preserve_punctuation(self):
        """测试保留标点"""
        assert normalize_text_light("你好，世界！") == "你好，世界！"


class TestPickDocId:
    """doc_id 提取测试"""
    
    def test_doc_id_key(self):
        """测试 doc_id 键"""
        assert pick_doc_id({"doc_id": "123"}) == "123"
    
    def test_id_key(self):
        """测试 id 键"""
        assert pick_doc_id({"id": "456"}) == "456"
    
    def test_docid_key(self):
        """测试 docid 键"""
        assert pick_doc_id({"docid": "789"}) == "789"
    
    def test_default_value(self):
        """测试默认值"""
        assert pick_doc_id({}, "default") == "default"
        assert pick_doc_id({"other": "value"}) == ""


class TestPickSourceText:
    """源文本提取测试"""
    
    def test_source_text_key(self):
        """测试 source_text 键"""
        assert pick_source_text({"source_text": "hello"}) == "hello"
    
    def test_text_key(self):
        """测试 text 键"""
        assert pick_source_text({"text": "world"}) == "world"
    
    def test_content_key(self):
        """测试 content 键"""
        assert pick_source_text({"content": "foo"}) == "foo"
    
    def test_empty(self):
        """测试空值"""
        assert pick_source_text({}) == ""


class TestComputeF1:
    """F1 计算测试"""
    
    def test_perfect_score(self):
        """测试完美分数"""
        result = compute_f1(pred_count=10, gold_count=10, matched=10)
        assert result["precision"] == 1.0
        assert result["recall"] == 1.0
        assert result["f1"] == 1.0
    
    def test_zero_score(self):
        """测试零分"""
        result = compute_f1(pred_count=10, gold_count=10, matched=0)
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0
        assert result["f1"] == 0.0
    
    def test_partial_score(self):
        """测试部分分数"""
        result = compute_f1(pred_count=10, gold_count=10, matched=5)
        assert result["precision"] == 0.5
        assert result["recall"] == 0.5
        assert result["f1"] == 0.5
    
    def test_empty_predictions(self):
        """测试空预测"""
        result = compute_f1(pred_count=0, gold_count=10, matched=0)
        assert result["precision"] == 0.0
        assert result["recall"] == 0.0
        assert result["f1"] == 0.0
