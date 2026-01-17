"""
格式转换工具

提供统一格式与旧格式之间的转换功能，支持向后兼容和渐进式迁移。

主要功能：
1. 从旧格式转换到统一格式
2. 从统一格式转换到旧格式
3. 从三元组中提取实体
4. 将实体嵌入到三元组中
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set
import logging

from .unified_formats import UnifiedEntity, UnifiedTriple, ProcessingStatus
from .normalization import TypeRegistry

logger = logging.getLogger(__name__)


class FormatConverter:
    """
    格式转换器

    提供统一格式与各种旧格式之间的双向转换。

    Example:
        >>> converter = FormatConverter()
        >>> # 从旧格式转换
        >>> entity = converter.from_legacy_entity({"name": "长江", "type": "河流"})
        >>> # 转换回旧格式
        >>> legacy = converter.to_legacy_entity(entity)
    """

    def __init__(self, type_registry: Optional[TypeRegistry] = None):
        """
        初始化转换器

        Args:
            type_registry: 类型注册表，用于类型规范化
        """
        self.type_registry = type_registry or TypeRegistry()

    # ==================== 实体转换 ====================

    def from_legacy_entity(self, data: Dict[str, Any]) -> UnifiedEntity:
        """
        从旧格式字典转换为UnifiedEntity

        支持的旧格式：
        1. {"name": str, "type": str}
        2. {"id": str, "label": str, "props": dict}  # Node dataclass
        3. 完整格式（已包含所有字段）

        Args:
            data: 旧格式字典

        Returns:
            UnifiedEntity对象
        """
        # 提取名称
        name = data.get("name") or data.get("id", "")
        if not name:
            raise ValueError("Entity must have a 'name' or 'id' field")

        # 提取类型
        entity_type = data.get("type") or data.get("label", "Unknown")

        # 规范化类型
        normalized_type, type_valid = self.type_registry.normalize_type(entity_type)
        cn_type = None
        if type_valid:
            cn_type = self.type_registry.get_chinese_name(normalized_type)
        else:
            # 如果类型无效，保留原始类型
            normalized_type = entity_type

        # 提取其他字段
        aliases = data.get("aliases", [])
        confidence = data.get("confidence", 1.0)
        source_text = data.get("source_text")
        doc_id = data.get("doc_id")

        # 提取处理标志
        normalized = data.get("normalized", False)
        aligned = data.get("aligned", False)
        verified = data.get("verified", False)

        # 提取状态
        status_str = data.get("status", "raw")
        if isinstance(status_str, str):
            try:
                status = ProcessingStatus(status_str)
            except ValueError:
                status = ProcessingStatus.RAW
        else:
            status = status_str

        # 提取元数据
        metadata = data.get("metadata", {})

        # 从props中提取额外信息（如果是Node格式）
        if "props" in data:
            props = data["props"]
            if isinstance(props, dict):
                metadata.update(props)

        return UnifiedEntity(
            name=name,
            type=normalized_type,
            cn_type=cn_type,
            aliases=aliases,
            confidence=confidence,
            source_text=source_text,
            doc_id=doc_id,
            normalized=normalized,
            aligned=aligned,
            verified=verified,
            status=status,
            metadata=metadata,
        )

    def to_legacy_entity(self, entity: UnifiedEntity, format_type: str = "simple") -> Dict[str, Any]:
        """
        将UnifiedEntity转换为旧格式

        Args:
            entity: UnifiedEntity对象
            format_type: 目标格式类型
                - "simple": {"name": str, "type": str}
                - "node": {"id": str, "label": str, "props": dict}
                - "full": 完整字典格式

        Returns:
            旧格式字典
        """
        if format_type == "simple":
            return {
                "name": entity.name,
                "type": entity.type,
            }
        elif format_type == "node":
            return {
                "id": entity.name,
                "label": entity.type,
                "props": entity.metadata.copy(),
            }
        elif format_type == "full":
            return entity.to_dict()
        else:
            raise ValueError(f"Unknown format type: {format_type}")

    # ==================== 三元组转换 ====================

    def from_legacy_triple(self, data: Dict[str, Any]) -> UnifiedTriple:
        """
        从旧格式字典转换为UnifiedTriple

        支持的旧格式：
        1. {"subject": str, "predicate": str, "object": str, "subject_type": str, "object_type": str}
        2. {"src": str, "rel": str, "dst": str}  # Edge dataclass
        3. 完整格式（已包含所有字段）

        Args:
            data: 旧格式字典

        Returns:
            UnifiedTriple对象
        """
        # 提取主语、谓词、宾语
        subject = data.get("subject") or data.get("src", "")
        predicate = data.get("predicate") or data.get("rel", "")
        obj = data.get("object") or data.get("dst", "")

        if not (subject and predicate and obj):
            raise ValueError("Triple must have subject, predicate, and object")

        # 提取类型
        subject_type = data.get("subject_type", "Unknown")
        object_type = data.get("object_type", "Unknown")

        # 规范化类型
        subject_type, _ = self.type_registry.normalize_type(subject_type)
        object_type, _ = self.type_registry.normalize_type(object_type)

        # 提取其他字段
        evidence = data.get("evidence")
        doc_id = data.get("doc_id") or data.get("event_id")
        support = data.get("support", 1)
        confidence = data.get("confidence", 1.0)

        # 提取处理标志
        normalized = data.get("normalized", False)
        direction_fixed = data.get("direction_fixed", False)
        verified = data.get("verified", False)

        # 提取状态
        status_str = data.get("status", "raw")
        if isinstance(status_str, str):
            try:
                status = ProcessingStatus(status_str)
            except ValueError:
                status = ProcessingStatus.RAW
        else:
            status = status_str

        # 提取元数据
        metadata = data.get("metadata", {})

        return UnifiedTriple(
            subject=subject,
            predicate=predicate,
            object=obj,
            subject_type=subject_type,
            object_type=object_type,
            evidence=evidence,
            doc_id=doc_id,
            support=support,
            confidence=confidence,
            normalized=normalized,
            direction_fixed=direction_fixed,
            verified=verified,
            status=status,
            metadata=metadata,
        )

    def to_legacy_triple(self, triple: UnifiedTriple, format_type: str = "simple") -> Dict[str, Any]:
        """
        将UnifiedTriple转换为旧格式

        Args:
            triple: UnifiedTriple对象
            format_type: 目标格式类型
                - "simple": {"subject": str, "predicate": str, "object": str}
                - "edge": {"src": str, "rel": str, "dst": str}
                - "full": 完整字典格式

        Returns:
            旧格式字典
        """
        if format_type == "simple":
            return {
                "subject": triple.subject,
                "predicate": triple.predicate,
                "object": triple.object,
            }
        elif format_type == "edge":
            return {
                "src": triple.subject,
                "rel": triple.predicate,
                "dst": triple.object,
            }
        elif format_type == "full":
            return triple.to_dict()
        else:
            raise ValueError(f"Unknown format type: {format_type}")

    # ==================== 批量转换 ====================

    def from_legacy_entities(self, data_list: List[Dict[str, Any]]) -> List[UnifiedEntity]:
        """
        批量转换实体

        Args:
            data_list: 旧格式实体列表

        Returns:
            UnifiedEntity列表
        """
        entities = []
        for data in data_list:
            try:
                entity = self.from_legacy_entity(data)
                entities.append(entity)
            except Exception as e:
                logger.warning(f"Failed to convert entity: {data}. Error: {e}")
        return entities

    def from_legacy_triples(self, data_list: List[Dict[str, Any]]) -> List[UnifiedTriple]:
        """
        批量转换三元组

        Args:
            data_list: 旧格式三元组列表

        Returns:
            UnifiedTriple列表
        """
        triples = []
        for data in data_list:
            try:
                triple = self.from_legacy_triple(data)
                triples.append(triple)
            except Exception as e:
                logger.warning(f"Failed to convert triple: {data}. Error: {e}")
        return triples

    def to_legacy_entities(
        self,
        entities: List[UnifiedEntity],
        format_type: str = "simple"
    ) -> List[Dict[str, Any]]:
        """
        批量转换实体到旧格式

        Args:
            entities: UnifiedEntity列表
            format_type: 目标格式类型

        Returns:
            旧格式实体列表
        """
        return [self.to_legacy_entity(e, format_type) for e in entities]

    def to_legacy_triples(
        self,
        triples: List[UnifiedTriple],
        format_type: str = "simple"
    ) -> List[Dict[str, Any]]:
        """
        批量转换三元组到旧格式

        Args:
            triples: UnifiedTriple列表
            format_type: 目标格式类型

        Returns:
            旧格式三元组列表
        """
        return [self.to_legacy_triple(t, format_type) for t in triples]

    # ==================== 实体提取与嵌入 ====================

    def extract_entities_from_triples(self, triples: List[UnifiedTriple]) -> List[UnifiedEntity]:
        """
        从三元组列表中提取所有唯一实体

        Args:
            triples: 三元组列表

        Returns:
            实体列表（去重后）
        """
        entity_dict: Dict[tuple, UnifiedEntity] = {}

        for triple in triples:
            # 提取主语实体
            subject_key = (triple.subject, triple.subject_type)
            if subject_key not in entity_dict:
                entity_dict[subject_key] = UnifiedEntity(
                    name=triple.subject,
                    type=triple.subject_type,
                    doc_id=triple.doc_id,
                    confidence=triple.confidence,
                    normalized=triple.normalized,
                    status=triple.status,
                )

            # 提取宾语实体
            object_key = (triple.object, triple.object_type)
            if object_key not in entity_dict:
                entity_dict[object_key] = UnifiedEntity(
                    name=triple.object,
                    type=triple.object_type,
                    doc_id=triple.doc_id,
                    confidence=triple.confidence,
                    normalized=triple.normalized,
                    status=triple.status,
                )

        return list(entity_dict.values())

    def embed_entities_in_triples(
        self,
        triples: List[Dict[str, Any]],
        entities: List[UnifiedEntity]
    ) -> List[UnifiedTriple]:
        """
        将实体信息嵌入到三元组中

        Args:
            triples: 简单三元组列表（可能缺少类型信息）
            entities: 实体列表（包含类型信息）

        Returns:
            完整的UnifiedTriple列表
        """
        # 构建实体名称到实体的映射
        entity_map: Dict[str, UnifiedEntity] = {}
        for entity in entities:
            entity_map[entity.name] = entity
            for alias in entity.aliases:
                entity_map[alias] = entity

        # 嵌入实体信息
        result = []
        for triple_data in triples:
            subject = triple_data.get("subject", "")
            obj = triple_data.get("object", "")

            # 查找实体类型
            subject_entity = entity_map.get(subject)
            object_entity = entity_map.get(obj)

            subject_type = subject_entity.type if subject_entity else triple_data.get("subject_type", "Unknown")
            object_type = object_entity.type if object_entity else triple_data.get("object_type", "Unknown")

            # 创建完整三元组
            triple = UnifiedTriple(
                subject=subject,
                predicate=triple_data.get("predicate", ""),
                object=obj,
                subject_type=subject_type,
                object_type=object_type,
                evidence=triple_data.get("evidence"),
                doc_id=triple_data.get("doc_id"),
                support=triple_data.get("support", 1),
                confidence=triple_data.get("confidence", 1.0),
            )
            result.append(triple)

        return result

    # ==================== 提取结果转换 ====================

    def from_extraction_result(self, result: Dict[str, Any]) -> tuple[List[UnifiedEntity], List[UnifiedTriple]]:
        """
        从提取结果转换为统一格式

        Args:
            result: 提取结果字典，包含 "entities" 和/或 "triples" 字段

        Returns:
            (实体列表, 三元组列表)
        """
        entities = []
        triples = []

        # 转换实体
        if "entities" in result:
            entities = self.from_legacy_entities(result["entities"])

        # 转换三元组
        if "triples" in result:
            triples = self.from_legacy_triples(result["triples"])

        # 如果没有显式的实体列表，从三元组中提取
        if not entities and triples:
            entities = self.extract_entities_from_triples(triples)

        return entities, triples

    def to_extraction_result(
        self,
        entities: List[UnifiedEntity],
        triples: List[UnifiedTriple],
        format_type: str = "full"
    ) -> Dict[str, Any]:
        """
        转换为提取结果格式

        Args:
            entities: 实体列表
            triples: 三元组列表
            format_type: 格式类型

        Returns:
            提取结果字典
        """
        return {
            "entities": self.to_legacy_entities(entities, format_type),
            "triples": self.to_legacy_triples(triples, format_type),
        }


# 便捷函数
def convert_from_legacy(data: Dict[str, Any], data_type: str = "auto") -> UnifiedEntity | UnifiedTriple:
    """
    便捷函数：从旧格式转换

    Args:
        data: 旧格式数据
        data_type: 数据类型（"entity", "triple", "auto"）

    Returns:
        UnifiedEntity或UnifiedTriple对象
    """
    converter = FormatConverter()

    if data_type == "auto":
        # 自动检测类型
        if "subject" in data or "src" in data:
            data_type = "triple"
        else:
            data_type = "entity"

    if data_type == "entity":
        return converter.from_legacy_entity(data)
    elif data_type == "triple":
        return converter.from_legacy_triple(data)
    else:
        raise ValueError(f"Unknown data type: {data_type}")


def convert_to_legacy(
    obj: UnifiedEntity | UnifiedTriple,
    format_type: str = "simple"
) -> Dict[str, Any]:
    """
    便捷函数：转换为旧格式

    Args:
        obj: UnifiedEntity或UnifiedTriple对象
        format_type: 目标格式类型

    Returns:
        旧格式字典
    """
    converter = FormatConverter()

    if isinstance(obj, UnifiedEntity):
        return converter.to_legacy_entity(obj, format_type)
    elif isinstance(obj, UnifiedTriple):
        return converter.to_legacy_triple(obj, format_type)
    else:
        raise ValueError(f"Unknown object type: {type(obj)}")


__all__ = [
    "FormatConverter",
    "convert_from_legacy",
    "convert_to_legacy",
]
