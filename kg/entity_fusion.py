"""
知识融合模块（P6）

功能：实体归一化 + 关系去重
位置：P5+校验之后、入库之前

核心原理：
1. 实体归一化：将指代同一对象的不同表述合并（如"长江"="扬子江"）
2. 关系去重：合并相同的(subject, predicate, object)三元组，统计支持度
"""

from __future__ import annotations

from typing import List, Dict, Tuple, Set, Optional
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class EntityFusion:
    """
    实体融合与关系去重

    功能1 - 实体归一化：
    - 使用预定义别名字典
    - 将同义实体映射到统一名称

    功能2 - 关系去重：
    - 合并相同的(subject, predicate, object)三元组
    - 记录支持度（出现次数）
    """

    def __init__(
        self,
        alias_dict: Optional[Dict[str, str]] = None,
        use_embedding: bool = False,
        embedding_threshold: float = 0.9
    ):
        """
        初始化融合器

        Args:
            alias_dict: 预定义的别名映射字典，格式 {"别名": "标准名"}
                       如果为None，使用内置的长江流域常见别名
            use_embedding: 是否使用向量相似度进行实体匹配（高级功能，可选）
            embedding_threshold: 向量相似度阈值
        """
        self.alias_dict = alias_dict if alias_dict is not None else self._default_alias_dict()
        self.use_embedding = use_embedding
        self.embedding_threshold = embedding_threshold

        # 统计信息
        self._entity_merge_count = 0
        self._original_triple_count = 0
        self._final_triple_count = 0
        self._merge_log: List[Dict] = []

    def _default_alias_dict(self) -> Dict[str, str]:
        """
        返回预定义的长江流域常见别名字典

        应包含：
        - 河流别名：扬子江->长江, 大江->长江
        - 湖泊别名：洞庭->洞庭湖, 鄱阳->鄱阳湖
        - 水库别名：三峡大坝->三峡水库
        - 城市别名：武汉市->武汉, 南京市->南京
        """
        return {
            # 河流别名
            "扬子江": "长江",
            "大江": "长江",
            "万里长江": "长江",
            "长江干流": "长江",

            # 湖泊别名
            "洞庭": "洞庭湖",
            "鄱阳": "鄱阳湖",
            "太湖流域": "太湖",
            "巢湖流域": "巢湖",

            # 水库别名
            "三峡大坝": "三峡水库",
            "三峡工程": "三峡水库",
            "葛洲坝工程": "葛洲坝水库",

            # 城市别名（去除"市"后缀）
            "武汉市": "武汉",
            "南京市": "南京",
            "重庆市": "重庆",
            "上海市": "上海",
            "南昌市": "南昌",
            "长沙市": "长沙",
            "合肥市": "合肥",
            "杭州市": "杭州",
            "成都市": "成都",
            "宜昌市": "宜昌",
            "荆州市": "荆州",
            "九江市": "九江",
            "芜湖市": "芜湖",
            "安庆市": "安庆",
            "岳阳市": "岳阳",
            "黄石市": "黄石",
            "镇江市": "镇江",
            "扬州市": "扬州",

            # 省份别名
            "湖北省": "湖北",
            "湖南省": "湖南",
            "江西省": "江西",
            "安徽省": "安徽",
            "江苏省": "江苏",
            "浙江省": "浙江",
            "四川省": "四川",
            "云南省": "云南",
            "贵州省": "贵州",
            "青海省": "青海",
            "西藏自治区": "西藏",
            "陕西省": "陕西",
            "河南省": "河南",
            "广西壮族自治区": "广西",

            # 流域别名
            "长江中下游": "长江中下游地区",
            "长江上游": "长江上游地区",
            "长江下游": "长江下游地区",
            "中下游干流": "长江中下游",
            "上游干流": "长江上游",

            # 机构别名
            "国家防总": "国家防汛抗旱总指挥部",
            "防总": "国家防汛抗旱总指挥部",
            "长江委": "长江水利委员会",
            "长委": "长江水利委员会",
            "水利部": "水利部",

            # 灾害类型别名
            "特大洪水": "洪水",
            "大洪水": "洪水",
            "流域性洪水": "洪水",
            "暴雨洪涝": "洪涝",
            "山洪": "洪水",
            "特大干旱": "干旱",
            "严重干旱": "干旱",
            "夏旱": "干旱",
            "伏旱": "干旱",
        }

    def normalize_entity(self, entity: str) -> str:
        """
        单个实体归一化

        处理逻辑：
        1. 去除首尾空白
        2. 查找预定义别名
        3. 处理常见后缀变体（如"武汉市"中的"市"）
        4. 返回标准化名称
        """
        if not entity:
            return entity

        # 1. 去除首尾空白
        normalized = entity.strip()

        # 2. 直接查找别名字典
        if normalized in self.alias_dict:
            original = normalized
            normalized = self.alias_dict[normalized]
            self._merge_log.append({
                "original": original,
                "normalized": normalized,
                "method": "alias_dict"
            })
            self._entity_merge_count += 1
            return normalized

        # 3. 处理常见后缀变体
        # 城市后缀
        for suffix in ["市", "县", "区"]:
            if normalized.endswith(suffix) and len(normalized) > 2:
                base_name = normalized[:-1]
                # 检查去除后缀后是否在别名字典中
                if base_name in self.alias_dict:
                    original = normalized
                    normalized = self.alias_dict[base_name]
                    self._merge_log.append({
                        "original": original,
                        "normalized": normalized,
                        "method": "suffix_removal"
                    })
                    self._entity_merge_count += 1
                    return normalized
                # 检查完整形式是否在字典中
                if f"{base_name}{suffix}" in self.alias_dict:
                    original = normalized
                    normalized = self.alias_dict[f"{base_name}{suffix}"]
                    self._merge_log.append({
                        "original": original,
                        "normalized": normalized,
                        "method": "suffix_match"
                    })
                    self._entity_merge_count += 1
                    return normalized

        # 省份后缀
        if normalized.endswith("省") and len(normalized) > 2:
            base_name = normalized[:-1]
            if f"{base_name}省" in self.alias_dict:
                original = normalized
                normalized = self.alias_dict[f"{base_name}省"]
                self._merge_log.append({
                    "original": original,
                    "normalized": normalized,
                    "method": "province_suffix"
                })
                self._entity_merge_count += 1
                return normalized

        return normalized

    def normalize_entities(self, triples: List[Dict]) -> List[Dict]:
        """
        批量归一化三元组中的实体

        对每个三元组的subject和object进行归一化
        记录归一化日志
        """
        if not triples:
            return []

        normalized_triples = []

        for triple in triples:
            new_triple = dict(triple)

            # 归一化subject
            if "subject" in new_triple:
                new_triple["subject"] = self.normalize_entity(new_triple["subject"])

            # 归一化object
            if "object" in new_triple:
                new_triple["object"] = self.normalize_entity(new_triple["object"])

            normalized_triples.append(new_triple)

        return normalized_triples

    def deduplicate_relations(
        self,
        triples: List[Dict],
        keep_evidence: bool = True
    ) -> List[Dict]:
        """
        关系去重

        Args:
            triples: 三元组列表
            keep_evidence: 是否保留所有evidence（合并为列表）

        Returns:
            去重后的三元组列表，每个三元组增加:
            - support: int, 出现次数
            - evidence: str或List[str], 原文证据

        处理逻辑：
        1. 以(subject, predicate, object)为key分组
        2. 合并同组三元组
        3. 统计支持度
        4. 合并evidence字段
        """
        if not triples:
            return []

        self._original_triple_count = len(triples)

        # 以(subject, predicate, object)为key分组
        groups: Dict[Tuple[str, str, str], List[Dict]] = defaultdict(list)

        for triple in triples:
            subject = triple.get("subject", "")
            predicate = triple.get("predicate", "")
            obj = triple.get("object", "")
            key = (subject, predicate, obj)
            groups[key].append(triple)

        # 合并同组三元组
        deduplicated = []

        for (subject, predicate, obj), group in groups.items():
            # 取第一个三元组作为基础
            merged = dict(group[0])
            merged["subject"] = subject
            merged["predicate"] = predicate
            merged["object"] = obj

            # 统计支持度
            merged["support"] = len(group)

            # 合并evidence
            if keep_evidence:
                evidences = []
                for t in group:
                    ev = t.get("evidence", "")
                    if ev and ev not in evidences:
                        evidences.append(ev)

                if len(evidences) == 1:
                    merged["evidence"] = evidences[0]
                elif len(evidences) > 1:
                    merged["evidence"] = evidences
                else:
                    merged["evidence"] = ""
            else:
                # 只保留第一个evidence
                merged["evidence"] = group[0].get("evidence", "")

            # 合并event_id（如果有多个不同的event_id）
            event_ids = set()
            for t in group:
                eid = t.get("event_id", "")
                if eid:
                    event_ids.add(eid)
            if len(event_ids) == 1:
                merged["event_id"] = list(event_ids)[0]
            elif len(event_ids) > 1:
                merged["event_id"] = list(event_ids)
            else:
                merged["event_id"] = ""

            deduplicated.append(merged)

        self._final_triple_count = len(deduplicated)

        logger.info(f"关系去重: {self._original_triple_count} -> {self._final_triple_count}")

        return deduplicated

    def get_statistics(self) -> Dict:
        """获取融合统计信息"""
        reduction_rate = 0.0
        if self._original_triple_count > 0:
            reduction_rate = 1 - (self._final_triple_count / self._original_triple_count)

        return {
            "entity_merges": self._entity_merge_count,
            "original_triple_count": self._original_triple_count,
            "final_triple_count": self._final_triple_count,
            "reduction_rate": reduction_rate,
            "merge_log": self._merge_log,
        }

    def reset_statistics(self):
        """重置统计信息"""
        self._entity_merge_count = 0
        self._original_triple_count = 0
        self._final_triple_count = 0
        self._merge_log = []


class SimpleEntityNormalizer:
    """
    简单实体标准化器

    仅做基础的格式统一，不做复杂的实体链接。
    主要功能：
    1. 去除首尾空白
    2. 统一空格
    3. 全角转半角数字

    Example:
        >>> normalizer = SimpleEntityNormalizer()
        >>> normalizer.normalize("  长江  ")
        '长江'
        >>> normalizer.normalize("２０２０年")
        '2020年'
    """

    def __init__(self):
        pass

    def normalize(self, entity: str) -> str:
        """
        标准化单个实体

        Args:
            entity: 原始实体字符串

        Returns:
            标准化后的实体字符串
        """
        if not entity:
            return entity

        import re

        # 1. 去除首尾空白
        entity = entity.strip()

        # 2. 去除全角空格（先处理，避免被统一空格转换）
        entity = entity.replace('　', '')

        # 3. 统一空格（多个空格合并为一个）
        entity = re.sub(r'\s+', ' ', entity)

        # 4. 去除多余空格（实体名中通常不需要空格）
        entity = entity.replace(' ', '')

        # 5. 全角转半角数字
        entity = self._full_to_half_digits(entity)

        return entity

    def normalize_triple(self, triple: Dict) -> Dict:
        """
        标准化单个三元组

        Args:
            triple: 原始三元组字典

        Returns:
            标准化后的三元组字典
        """
        normalized = triple.copy()

        if "subject" in normalized:
            normalized["subject"] = self.normalize(normalized["subject"])
        if "object" in normalized:
            normalized["object"] = self.normalize(normalized["object"])

        # predicate不做标准化（应与Schema保持一致）

        return normalized

    def normalize_triples(self, triples: List[Dict]) -> List[Dict]:
        """
        批量标准化三元组

        Args:
            triples: 三元组列表

        Returns:
            标准化后的三元组列表
        """
        return [self.normalize_triple(t) for t in triples]

    @staticmethod
    def _full_to_half_digits(text: str) -> str:
        """
        全角数字转半角

        ０１２３４５６７８９ -> 0123456789
        """
        result = []
        for char in text:
            code = ord(char)
            # 全角数字范围: 0xFF10 (０) - 0xFF19 (９)
            if 0xFF10 <= code <= 0xFF19:
                result.append(chr(code - 0xFEE0))
            else:
                result.append(char)
        return ''.join(result)


# 便捷函数
def fuse_knowledge(
    triples: List[Dict],
    alias_dict: Optional[Dict[str, str]] = None
) -> Tuple[List[Dict], Dict]:
    """
    便捷函数：完整的知识融合流程

    执行：实体归一化 -> 关系去重

    Returns:
        (fused_triples, statistics)

    statistics包含：
        - entity_merges: 实体合并次数
        - original_triple_count: 原始三元组数
        - final_triple_count: 最终三元组数
        - reduction_rate: 缩减比例
    """
    fusion = EntityFusion(alias_dict=alias_dict)

    # 1. 实体归一化
    normalized_triples = fusion.normalize_entities(triples)

    # 2. 关系去重
    fused_triples = fusion.deduplicate_relations(normalized_triples)

    # 3. 获取统计信息
    statistics = fusion.get_statistics()

    return fused_triples, statistics


def normalize_entities(triples: List[Dict]) -> List[Dict]:
    """
    便捷函数：标准化三元组列表中的实体

    Args:
        triples: 三元组列表

    Returns:
        标准化后的三元组列表
    """
    normalizer = SimpleEntityNormalizer()
    return normalizer.normalize_triples(triples)


if __name__ == "__main__":
    # 测试用例
    triples = [
        {"subject": "长江", "predicate": "发生", "object": "洪水", "evidence": "长江发生洪水"},
        {"subject": "扬子江", "predicate": "发生", "object": "洪水", "evidence": "扬子江发生大水"},
        {"subject": "长江", "predicate": "流经", "object": "武汉市", "evidence": "长江流经武汉"},
        {"subject": "长江", "predicate": "流经", "object": "武汉", "evidence": "长江穿过武汉"},
    ]

    fused, stats = fuse_knowledge(triples)

    print(f"原始: {stats['original_triple_count']}, 融合后: {stats['final_triple_count']}")
    print(f"缩减率: {stats['reduction_rate']:.1%}")

    for t in fused:
        print(f"  {t['subject']} --{t['predicate']}--> {t['object']} (支持度: {t['support']})")

    # 预期输出：
    # 原始: 4, 融合后: 2
    # 缩减率: 50.0%
    # 长江 --发生--> 洪水 (支持度: 2)
    # 长江 --流经--> 武汉 (支持度: 2)

    # 测试 SimpleEntityNormalizer
    print("\n--- SimpleEntityNormalizer 测试 ---")
    normalizer = SimpleEntityNormalizer()
    print(f"'  长江  ' -> '{normalizer.normalize('  长江  ')}'")
    print(f"'２０２０年' -> '{normalizer.normalize('２０２０年')}'")
