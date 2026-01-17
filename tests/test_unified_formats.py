"""
统一格式和归一化模块的单元测试

测试覆盖：
1. UnifiedEntity 和 UnifiedTriple 数据类
2. UnifiedTextNormalizer 文本归一化
3. UnifiedEntityMatcher 实体匹配
4. TypeRegistry 类型注册表
5. FormatConverter 格式转换
"""

import pytest
from kg.unified_formats import UnifiedEntity, UnifiedTriple, ProcessingStatus
from kg.normalization import (
    UnifiedTextNormalizer,
    UnifiedEntityMatcher,
    TypeRegistry,
    NormalizationConfig,
    MatchingConfig,
    MatchResult,
)
from kg.format_converter import FormatConverter


class TestUnifiedEntity:
    """测试 UnifiedEntity 数据类"""

    def test_create_basic_entity(self):
        """测试创建基本实体"""
        entity = UnifiedEntity(name="长江", type="River")
        assert entity.name == "长江"
        assert entity.type == "River"
        assert entity.confidence == 1.0
        assert entity.status == ProcessingStatus.RAW

    def test_create_entity_with_all_fields(self):
        """测试创建包含所有字段的实体"""
        entity = UnifiedEntity(
            name="长江",
            type="River",
            cn_type="河流",
            aliases=["扬子江", "大江"],
            confidence=0.95,
            source_text="扬子江",
            doc_id="doc_001",
        )
        assert entity.name == "长江"
        assert entity.cn_type == "河流"
        assert len(entity.aliases) == 2
        assert "扬子江" in entity.aliases

    def test_entity_validation(self):
        """测试实体验证"""
        # 空名称应该抛出异常
        with pytest.raises(ValueError):
            UnifiedEntity(name="", type="River")

        # 空类型应该抛出异常
        with pytest.raises(ValueError):
            UnifiedEntity(name="长江", type="")

        # 无效置信度应该抛出异常
        with pytest.raises(ValueError):
            UnifiedEntity(name="长江", type="River", confidence=1.5)

    def test_entity_to_dict(self):
        """测试实体转字典"""
        entity = UnifiedEntity(name="长江", type="River", cn_type="河流")
        data = entity.to_dict()
        assert data["name"] == "长江"
        assert data["type"] == "River"
        assert data["cn_type"] == "河流"
        assert data["status"] == "raw"

    def test_entity_from_dict(self):
        """测试从字典创建实体"""
        data = {
            "name": "长江",
            "type": "River",
            "cn_type": "河流",
            "confidence": 0.9,
        }
        entity = UnifiedEntity.from_dict(data)
        assert entity.name == "长江"
        assert entity.type == "River"
        assert entity.confidence == 0.9

    def test_entity_add_alias(self):
        """测试添加别名"""
        entity = UnifiedEntity(name="长江", type="River")
        entity.add_alias("扬子江")
        entity.add_alias("大江")
        assert len(entity.aliases) == 2
        assert "扬子江" in entity.aliases

        # 不应该添加重复别名
        entity.add_alias("扬子江")
        assert len(entity.aliases) == 2

        # 不应该添加与名称相同的别名
        entity.add_alias("长江")
        assert len(entity.aliases) == 2

    def test_entity_status_transitions(self):
        """测试实体状态转换"""
        entity = UnifiedEntity(name="长江", type="River")
        assert entity.status == ProcessingStatus.RAW

        entity.mark_normalized()
        assert entity.normalized
        assert entity.status == ProcessingStatus.NORMALIZED

        entity.mark_aligned()
        assert entity.aligned
        assert entity.status == ProcessingStatus.ALIGNED

        entity.mark_verified()
        assert entity.verified
        assert entity.status == ProcessingStatus.VERIFIED


class TestUnifiedTriple:
    """测试 UnifiedTriple 数据类"""

    def test_create_basic_triple(self):
        """测试创建基本三元组"""
        triple = UnifiedTriple(
            subject="长江",
            predicate="flows_through",
            object="武汉",
            subject_type="River",
            object_type="City",
        )
        assert triple.subject == "长江"
        assert triple.predicate == "flows_through"
        assert triple.object == "武汉"
        assert triple.support == 1

    def test_triple_validation(self):
        """测试三元组验证"""
        # 空主语应该抛出异常
        with pytest.raises(ValueError):
            UnifiedTriple(
                subject="",
                predicate="flows_through",
                object="武汉",
                subject_type="River",
                object_type="City",
            )

        # 无效支持度应该抛出异常
        with pytest.raises(ValueError):
            UnifiedTriple(
                subject="长江",
                predicate="flows_through",
                object="武汉",
                subject_type="River",
                object_type="City",
                support=0,
            )

    def test_triple_get_key(self):
        """测试获取三元组唯一标识"""
        triple = UnifiedTriple(
            subject="长江",
            predicate="flows_through",
            object="武汉",
            subject_type="River",
            object_type="City",
        )
        key = triple.get_key()
        assert key == ("长江", "flows_through", "武汉")

    def test_triple_reverse(self):
        """测试反转三元组"""
        triple = UnifiedTriple(
            subject="长江",
            predicate="flows_through",
            object="武汉",
            subject_type="River",
            object_type="City",
            evidence="长江流经武汉",
        )
        reversed_triple = triple.reverse()
        assert reversed_triple.subject == "武汉"
        assert reversed_triple.object == "长江"
        assert reversed_triple.subject_type == "City"
        assert reversed_triple.object_type == "River"
        assert reversed_triple.direction_fixed


class TestUnifiedTextNormalizer:
    """测试 UnifiedTextNormalizer"""

    def test_normalize_standard(self):
        """测试标准归一化"""
        normalizer = UnifiedTextNormalizer()

        # 去除空格
        assert normalizer.normalize("  长江  ") == "长江"
        assert normalizer.normalize("长 江") == "长江"

        # 全角转半角
        assert normalizer.normalize("２０２０年") == "2020年"
        assert normalizer.normalize("ＡＢＣ") == "ABC"

        # 去除全角空格
        assert normalizer.normalize("长　江") == "长江"

    def test_normalize_strict(self):
        """测试严格归一化"""
        normalizer = UnifiedTextNormalizer()

        # 严格模式仅去除首尾空白
        result = normalizer.normalize("  长江  ", mode="strict")
        assert result == "长江"

        # 不去除中间空格
        result = normalizer.normalize("长 江", mode="strict")
        assert result == "长 江"

    def test_normalize_fuzzy(self):
        """测试模糊归一化"""
        normalizer = UnifiedTextNormalizer()

        # 模糊模式去除标点符号
        result = normalizer.normalize("长江、黄河", mode="fuzzy")
        assert result == "长江黄河"

        result = normalizer.normalize("长江（大江）", mode="fuzzy")
        assert result == "长江大江"

    def test_full_to_half(self):
        """测试全角转半角"""
        normalizer = UnifiedTextNormalizer()

        # 数字
        assert normalizer.normalize("０１２３４５６７８９") == "0123456789"

        # 字母
        assert normalizer.normalize("ＡＢＣａｂｃ") == "ABCabc"

        # 标点符号
        assert normalizer.normalize("！？。") == "!?。"  # 中文句号不转换

    def test_extract_numbers(self):
        """测试提取数字"""
        normalizer = UnifiedTextNormalizer()

        numbers = normalizer.extract_numbers("降雨量达到１２３．４５毫米")
        assert "123.45" in numbers

        numbers = normalizer.extract_numbers("受灾人口约500万人")
        assert "500" in numbers

    def test_is_empty_after_normalization(self):
        """测试归一化后是否为空"""
        normalizer = UnifiedTextNormalizer()

        assert normalizer.is_empty_after_normalization("   ")
        assert normalizer.is_empty_after_normalization("")
        assert not normalizer.is_empty_after_normalization("长江")


class TestUnifiedEntityMatcher:
    """测试 UnifiedEntityMatcher"""

    def test_exact_match(self):
        """测试精确匹配"""
        matcher = UnifiedEntityMatcher()
        entity1 = UnifiedEntity(name="长江", type="River")
        entity2 = UnifiedEntity(name="长江", type="River")

        result = matcher.match(entity1, entity2)
        assert result.is_match
        assert result.confidence == 1.0

    def test_normalized_match(self):
        """测试归一化匹配"""
        matcher = UnifiedEntityMatcher()
        entity1 = UnifiedEntity(name="  长江  ", type="River")
        entity2 = UnifiedEntity(name="长江", type="River")

        result = matcher.match(entity1, entity2)
        assert result.is_match
        assert result.confidence >= 0.9

    def test_synonym_match(self):
        """测试同义词匹配"""
        config = MatchingConfig()
        config.alias_dict = {"扬子江": "长江", "大江": "长江"}

        matcher = UnifiedEntityMatcher(config)
        entity1 = UnifiedEntity(name="扬子江", type="River")
        entity2 = UnifiedEntity(name="长江", type="River")

        result = matcher.match(entity1, entity2)
        assert result.is_match

    def test_alias_match(self):
        """测试别名匹配"""
        matcher = UnifiedEntityMatcher()
        entity1 = UnifiedEntity(name="长江", type="River", aliases=["扬子江"])
        entity2 = UnifiedEntity(name="扬子江", type="River")

        result = matcher.match(entity1, entity2)
        assert result.is_match

    def test_fuzzy_match(self):
        """测试模糊匹配"""
        config = MatchingConfig(fuzzy_threshold=0.8)
        matcher = UnifiedEntityMatcher(config)

        entity1 = UnifiedEntity(name="长江大桥", type="Location")
        entity2 = UnifiedEntity(name="长江大桥工程", type="Location")

        result = matcher.match(entity1, entity2)
        # 相似度应该较高
        assert result.confidence > 0.7

    def test_type_constraint(self):
        """测试类型约束"""
        config = MatchingConfig(use_type_constraint=True)
        matcher = UnifiedEntityMatcher(config)

        entity1 = UnifiedEntity(name="长江", type="River")
        entity2 = UnifiedEntity(name="长江", type="City")

        result = matcher.match(entity1, entity2)
        assert not result.is_match

    def test_match_names(self):
        """测试匹配名称（便捷方法）"""
        matcher = UnifiedEntityMatcher()
        result = matcher.match_names("长江", "长江", "River")
        assert result.is_match


class TestTypeRegistry:
    """测试 TypeRegistry"""

    def test_normalize_type_english(self):
        """测试英文类型规范化"""
        registry = TypeRegistry()

        # 有效类型
        normalized, success = registry.normalize_type("River")
        assert success
        assert normalized == "River"

        # 不区分大小写
        normalized, success = registry.normalize_type("river")
        assert success
        assert normalized == "River"

    def test_normalize_type_chinese(self):
        """测试中文类型规范化"""
        registry = TypeRegistry()

        # 中文类型应该转换为英文
        normalized, success = registry.normalize_type("河流")
        assert success
        assert normalized == "River"

        normalized, success = registry.normalize_type("城市")
        assert success
        assert normalized == "City"

    def test_normalize_type_alias(self):
        """测试类型别名规范化"""
        registry = TypeRegistry()

        # 别名应该转换为规范类型
        normalized, success = registry.normalize_type("洪灾")
        assert success
        assert normalized == "FloodEvent"

        normalized, success = registry.normalize_type("旱灾")
        assert success
        assert normalized == "DroughtEvent"

    def test_is_valid_type(self):
        """测试类型有效性检查"""
        registry = TypeRegistry()

        assert registry.is_valid_type("River")
        assert registry.is_valid_type("河流")
        assert registry.is_valid_type("洪灾")
        assert not registry.is_valid_type("UnknownType")

    def test_type_hierarchy(self):
        """测试类型层次结构"""
        registry = TypeRegistry()

        # 检查父类型
        parent = registry.get_parent_type("FloodEvent")
        assert parent == "DisasterEvent"

        parent = registry.get_parent_type("City")
        assert parent == "Location"

    def test_is_subtype_of(self):
        """测试子类型关系"""
        registry = TypeRegistry()

        assert registry.is_subtype_of("FloodEvent", "DisasterEvent")
        assert registry.is_subtype_of("City", "Location")
        assert not registry.is_subtype_of("River", "DisasterEvent")

        # 相同类型
        assert registry.is_subtype_of("River", "River")

    def test_get_all_subtypes(self):
        """测试获取所有子类型"""
        registry = TypeRegistry()

        subtypes = registry.get_all_subtypes("DisasterEvent")
        assert "FloodEvent" in subtypes
        assert "DroughtEvent" in subtypes
        assert len(subtypes) >= 2

    def test_get_chinese_name(self):
        """测试获取中文名称"""
        registry = TypeRegistry()

        cn_name = registry.get_chinese_name("River")
        assert cn_name == "河流"

        cn_name = registry.get_chinese_name("City")
        assert cn_name == "城市"


class TestFormatConverter:
    """测试 FormatConverter"""

    def test_from_legacy_entity_simple(self):
        """测试从简单格式转换实体"""
        converter = FormatConverter()
        data = {"name": "长江", "type": "河流"}

        entity = converter.from_legacy_entity(data)
        assert entity.name == "长江"
        assert entity.type == "River"  # 应该规范化为英文

    def test_from_legacy_entity_node(self):
        """测试从Node格式转换实体"""
        converter = FormatConverter()
        data = {
            "id": "长江",
            "label": "River",
            "props": {"length": "6300km"},
        }

        entity = converter.from_legacy_entity(data)
        assert entity.name == "长江"
        assert entity.type == "River"
        assert "length" in entity.metadata

    def test_to_legacy_entity_simple(self):
        """测试转换为简单格式"""
        converter = FormatConverter()
        entity = UnifiedEntity(name="长江", type="River")

        data = converter.to_legacy_entity(entity, format_type="simple")
        assert data["name"] == "长江"
        assert data["type"] == "River"

    def test_to_legacy_entity_node(self):
        """测试转换为Node格式"""
        converter = FormatConverter()
        entity = UnifiedEntity(name="长江", type="River")

        data = converter.to_legacy_entity(entity, format_type="node")
        assert data["id"] == "长江"
        assert data["label"] == "River"
        assert "props" in data

    def test_from_legacy_triple(self):
        """测试从旧格式转换三元组"""
        converter = FormatConverter()
        data = {
            "subject": "长江",
            "predicate": "flows_through",
            "object": "武汉",
            "subject_type": "河流",
            "object_type": "城市",
        }

        triple = converter.from_legacy_triple(data)
        assert triple.subject == "长江"
        assert triple.predicate == "flows_through"
        assert triple.object == "武汉"
        assert triple.subject_type == "River"  # 应该规范化
        assert triple.object_type == "City"

    def test_extract_entities_from_triples(self):
        """测试从三元组提取实体"""
        converter = FormatConverter()
        triples = [
            UnifiedTriple(
                subject="长江",
                predicate="flows_through",
                object="武汉",
                subject_type="River",
                object_type="City",
            ),
            UnifiedTriple(
                subject="长江",
                predicate="flows_through",
                object="南京",
                subject_type="River",
                object_type="City",
            ),
        ]

        entities = converter.extract_entities_from_triples(triples)
        # 应该提取出3个唯一实体：长江、武汉、南京
        assert len(entities) == 3

        entity_names = {e.name for e in entities}
        assert "长江" in entity_names
        assert "武汉" in entity_names
        assert "南京" in entity_names

    def test_batch_conversion(self):
        """测试批量转换"""
        converter = FormatConverter()
        data_list = [
            {"name": "长江", "type": "河流"},
            {"name": "武汉", "type": "城市"},
        ]

        entities = converter.from_legacy_entities(data_list)
        assert len(entities) == 2
        assert entities[0].name == "长江"
        assert entities[1].name == "武汉"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
