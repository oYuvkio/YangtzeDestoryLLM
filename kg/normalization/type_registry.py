"""
类型注册表

管理实体类型的规范化、验证和层次结构。
整合了TBox schema中的类型定义，提供统一的类型系统。

主要功能：
1. 类型名称规范化（中文<->英文）
2. 类型有效性验证
3. 类型层次结构查询
4. 类型别名管理
"""

from __future__ import annotations

from typing import Dict, List, Optional, Set, Tuple
import logging

from .config import TypeConfig

logger = logging.getLogger(__name__)


class TypeRegistry:
    """
    类型注册表

    管理知识图谱中的实体类型系统，提供类型规范化、验证和层次结构查询。

    Example:
        >>> registry = TypeRegistry()
        >>> registry.add_type("River", "河流")
        >>> registry.normalize_type("河流")
        ('River', True)
        >>> registry.is_valid_type("River")
        True
    """

    def __init__(self, config: Optional[TypeConfig] = None):
        """
        初始化类型注册表

        Args:
            config: 类型配置，如果为None则使用默认配置
        """
        self.config = config or TypeConfig()
        self._initialize_default_types()

    def _initialize_default_types(self):
        """初始化默认类型（基于长江灾害知识图谱）"""
        # 灾害事件类型
        self.add_type("FloodEvent", "洪水事件", parent="DisasterEvent")
        self.add_type("DroughtEvent", "干旱事件", parent="DisasterEvent")
        self.add_type("LandslideEvent", "滑坡事件", parent="DisasterEvent")
        self.add_type("DebrisFlowEvent", "泥石流事件", parent="DisasterEvent")
        self.add_type("DisasterEvent", "灾害事件")

        # 地理位置类型
        self.add_type("Province", "省份", parent="Location")
        self.add_type("City", "城市", parent="Location")
        self.add_type("County", "县", parent="Location")
        self.add_type("River", "河流", parent="Location")
        self.add_type("Lake", "湖泊", parent="Location")
        self.add_type("Reservoir", "水库", parent="Location")
        self.add_type("Location", "地点")

        # 时间类型
        self.add_type("Time", "时间")
        self.add_type("TimePoint", "时间点", parent="Time")
        self.add_type("TimeRange", "时间段", parent="Time")

        # 原因类型
        self.add_type("Cause", "原因")
        self.add_type("NaturalCause", "自然原因", parent="Cause")
        self.add_type("HumanCause", "人为原因", parent="Cause")

        # 影响类型
        self.add_type("Impact", "影响")
        self.add_type("EconomicImpact", "经济影响", parent="Impact")
        self.add_type("SocialImpact", "社会影响", parent="Impact")
        self.add_type("EnvironmentalImpact", "环境影响", parent="Impact")

        # 措施类型
        self.add_type("Measure", "措施")
        self.add_type("PreventiveMeasure", "预防措施", parent="Measure")
        self.add_type("EmergencyResponse", "应急响应", parent="Measure")
        self.add_type("RecoveryMeasure", "恢复措施", parent="Measure")

        # 机构类型
        self.add_type("Organization", "机构")
        self.add_type("GovernmentAgency", "政府机构", parent="Organization")
        self.add_type("ResearchInstitution", "研究机构", parent="Organization")

        # 数值类型
        self.add_type("Quantity", "数量")
        self.add_type("Rainfall", "降雨量", parent="Quantity")
        self.add_type("WaterLevel", "水位", parent="Quantity")
        self.add_type("Population", "人口", parent="Quantity")

        # 添加常见别名
        self._add_default_aliases()

    def _add_default_aliases(self):
        """添加默认类型别名"""
        # 灾害类型别名
        self.add_alias("洪灾", "FloodEvent")
        self.add_alias("水灾", "FloodEvent")
        self.add_alias("洪水", "FloodEvent")
        self.add_alias("特大洪水", "FloodEvent")
        self.add_alias("大洪水", "FloodEvent")

        self.add_alias("旱灾", "DroughtEvent")
        self.add_alias("旱情", "DroughtEvent")
        self.add_alias("干旱", "DroughtEvent")
        self.add_alias("特大干旱", "DroughtEvent")

        self.add_alias("滑坡", "LandslideEvent")
        self.add_alias("山体滑坡", "LandslideEvent")

        self.add_alias("泥石流", "DebrisFlowEvent")

        # 地理位置别名
        self.add_alias("省", "Province")
        self.add_alias("省份", "Province")
        self.add_alias("市", "City")
        self.add_alias("城市", "City")
        self.add_alias("县", "County")
        self.add_alias("县城", "County")

        self.add_alias("河流", "River")
        self.add_alias("江", "River")
        self.add_alias("河", "River")

        self.add_alias("湖", "Lake")
        self.add_alias("湖泊", "Lake")

        self.add_alias("水库", "Reservoir")
        self.add_alias("大坝", "Reservoir")

        self.add_alias("地点", "Location")
        self.add_alias("地区", "Location")
        self.add_alias("区域", "Location")

        # 时间别名
        self.add_alias("时间", "Time")
        self.add_alias("日期", "Time")

        # 原因别名
        self.add_alias("原因", "Cause")
        self.add_alias("成因", "Cause")
        self.add_alias("致灾因子", "Cause")

        # 影响别名
        self.add_alias("影响", "Impact")
        self.add_alias("后果", "Impact")
        self.add_alias("损失", "Impact")

        # 措施别名
        self.add_alias("措施", "Measure")
        self.add_alias("对策", "Measure")
        self.add_alias("方案", "Measure")
        self.add_alias("应急响应", "EmergencyResponse")
        self.add_alias("应急处置", "EmergencyResponse")
        self.add_alias("紧急响应", "EmergencyResponse")

        # 机构别名
        self.add_alias("机构", "Organization")
        self.add_alias("组织", "Organization")
        self.add_alias("单位", "Organization")

    def add_type(
        self,
        en_name: str,
        cn_name: Optional[str] = None,
        parent: Optional[str] = None
    ):
        """
        添加类型定义

        Args:
            en_name: 英文类型名（规范名称）
            cn_name: 中文类型名（可选）
            parent: 父类型（可选）
        """
        self.config.add_type(en_name, cn_name, parent)

    def add_alias(self, alias: str, canonical: str):
        """
        添加类型别名

        Args:
            alias: 别名
            canonical: 规范类型名
        """
        self.config.add_alias(alias, canonical)

    def normalize_type(self, type_name: str) -> Tuple[str, bool]:
        """
        规范化类型名称

        将任意类型名称（中文、英文、别名）转换为规范的英文类型名。

        Args:
            type_name: 输入类型名称

        Returns:
            (规范类型名, 是否成功规范化)

        Example:
            >>> registry.normalize_type("洪水")
            ('FloodEvent', True)
            >>> registry.normalize_type("UnknownType")
            ('UnknownType', False)
        """
        if not type_name:
            return type_name, False

        # 去除首尾空白
        type_name = type_name.strip()

        # 1. 检查是否已经是有效的英文类型
        if type_name in self.config.valid_types:
            return type_name, True

        # 2. 检查是否是别名
        if type_name in self.config.type_aliases:
            canonical = self.config.type_aliases[type_name]
            return canonical, True

        # 3. 检查是否是中文类型名
        if type_name in self.config.cn_to_en:
            en_name = self.config.cn_to_en[type_name]
            return en_name, True

        # 4. 尝试不区分大小写匹配
        type_name_lower = type_name.lower()
        for valid_type in self.config.valid_types:
            if valid_type.lower() == type_name_lower:
                return valid_type, True

        # 5. 尝试别名不区分大小写匹配
        for alias, canonical in self.config.type_aliases.items():
            if alias.lower() == type_name_lower:
                return canonical, True

        # 无法规范化，返回原始名称
        logger.warning(f"Unable to normalize type: {type_name}")
        return type_name, False

    def is_valid_type(self, type_name: str) -> bool:
        """
        检查类型是否有效

        Args:
            type_name: 类型名称

        Returns:
            是否有效
        """
        normalized, success = self.normalize_type(type_name)
        return success

    def get_parent_type(self, type_name: str) -> Optional[str]:
        """
        获取父类型

        Args:
            type_name: 类型名称

        Returns:
            父类型名称，如果没有则返回None
        """
        normalized, success = self.normalize_type(type_name)
        if not success:
            return None

        return self.config.type_hierarchy.get(normalized)

    def is_subtype_of(self, child_type: str, parent_type: str) -> bool:
        """
        检查是否是子类型

        Args:
            child_type: 子类型名称
            parent_type: 父类型名称

        Returns:
            是否是子类型关系
        """
        # 规范化类型名称
        child_normalized, child_success = self.normalize_type(child_type)
        parent_normalized, parent_success = self.normalize_type(parent_type)

        if not (child_success and parent_success):
            return False

        # 相同类型
        if child_normalized == parent_normalized:
            return True

        # 沿着层次结构向上查找
        current = child_normalized
        visited = set()  # 防止循环

        while current and current not in visited:
            visited.add(current)
            parent = self.config.type_hierarchy.get(current)

            if parent == parent_normalized:
                return True

            current = parent

        return False

    def get_all_subtypes(self, parent_type: str) -> List[str]:
        """
        获取所有子类型

        Args:
            parent_type: 父类型名称

        Returns:
            子类型列表
        """
        parent_normalized, success = self.normalize_type(parent_type)
        if not success:
            return []

        subtypes = []
        for child_type in self.config.valid_types:
            if self.is_subtype_of(child_type, parent_normalized) and child_type != parent_normalized:
                subtypes.append(child_type)

        return subtypes

    def get_type_hierarchy(self, type_name: str) -> List[str]:
        """
        获取类型的完整层次结构（从根到当前类型）

        Args:
            type_name: 类型名称

        Returns:
            类型层次结构列表（从根到叶）
        """
        normalized, success = self.normalize_type(type_name)
        if not success:
            return [type_name]

        hierarchy = [normalized]
        current = normalized
        visited = set()

        while current and current not in visited:
            visited.add(current)
            parent = self.config.type_hierarchy.get(current)

            if parent:
                hierarchy.insert(0, parent)
                current = parent
            else:
                break

        return hierarchy

    def get_chinese_name(self, en_type: str) -> Optional[str]:
        """
        获取类型的中文名称

        Args:
            en_type: 英文类型名

        Returns:
            中文名称，如果没有则返回None
        """
        normalized, success = self.normalize_type(en_type)
        if not success:
            return None

        return self.config.en_to_cn.get(normalized)

    def get_all_types(self) -> Set[str]:
        """
        获取所有有效类型

        Returns:
            类型集合
        """
        return self.config.valid_types.copy()

    def get_statistics(self) -> Dict:
        """
        获取类型系统统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_types": len(self.config.valid_types),
            "total_aliases": len(self.config.type_aliases),
            "cn_to_en_mappings": len(self.config.cn_to_en),
            "hierarchy_relations": len(self.config.type_hierarchy),
        }


# 全局单例
_global_registry: Optional[TypeRegistry] = None


def get_global_registry() -> TypeRegistry:
    """
    获取全局类型注册表单例

    Returns:
        全局类型注册表
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = TypeRegistry()
    return _global_registry


# 便捷函数
def normalize_type(type_name: str) -> Tuple[str, bool]:
    """
    便捷函数：规范化类型名称

    Args:
        type_name: 类型名称

    Returns:
        (规范类型名, 是否成功)
    """
    registry = get_global_registry()
    return registry.normalize_type(type_name)


def is_valid_type(type_name: str) -> bool:
    """
    便捷函数：检查类型是否有效

    Args:
        type_name: 类型名称

    Returns:
        是否有效
    """
    registry = get_global_registry()
    return registry.is_valid_type(type_name)


__all__ = [
    "TypeRegistry",
    "get_global_registry",
    "normalize_type",
    "is_valid_type",
]
