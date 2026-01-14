#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
根据 Manifest 过滤语料并导出（支持 P5/EVAL 二分法）。

功能：
- 根据 manifest 文件过滤输入语料
- 支持 doc 级或 section 级分流
- 自动拆分 EVAL 为 dev/test

使用示例：
    # 导出 P5 语料（建图用）
    python filters/apply_manifest.py \\
        --input data/corpus_for_kg/filtered_ytz_corpus/light_pool_dedup.jsonl \\
        --manifest data/manifests/purpose_manifest.jsonl \\
        --purpose P5 \\
        --out data/corpus_for_kg/p5_only.jsonl \\
        --log-file logs/manifest/apply_p5.log

    # 导出 EVAL 语料（评测用，自动拆分 dev/test）
    python filters/apply_manifest.py \\
        --input data/corpus_for_kg/filtered_ytz_corpus/light_pool_dedup.jsonl \\
        --manifest data/manifests/purpose_manifest.jsonl \\
        --purpose EVAL \\
        --out data/p5_eval_pool/pool.jsonl \\
        --log-file logs/manifest/apply_eval.log

    # 查看帮助
    python filters/apply_manifest.py --help
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Final, List, Optional, Set

# ==============================================================================
# 项目路径配置
# ==============================================================================
PROJECT_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ==============================================================================
# 常量定义
# ==============================================================================
class Constants:
    """全局常量"""
    VERSION: Final[str] = "2.0.0"
    TOOL_NAME: Final[str] = "Manifest 过滤导出工具"

    VALID_PURPOSES: Final[Set[str]] = {"P5", "EVAL"}
    VALID_SPLIT_LEVELS: Final[Set[str]] = {"doc", "section"}
    VALID_FOLDS: Final[Set[str]] = {"dev", "test"}


# ==============================================================================
# 日志配置
# ==============================================================================
def setup_logger(
    name: str = "apply_manifest",
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """配置并返回 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8", mode="a")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


logger = setup_logger()


# ==============================================================================
# 数据结构
# ==============================================================================
@dataclass
class FilterStats:
    """过滤统计"""
    input_count: int = 0
    matched_count: int = 0
    dev_count: int = 0
    test_count: int = 0
    section_filtered: int = 0


# ==============================================================================
# 核心功能
# ==============================================================================
class ManifestFilter:
    """改进版 Manifest 过滤器（支持多用途和 fold 过滤）"""
    
    def __init__(
        self,
        manifest_path: Path,
        purposes: Set[str],  # 支持多个用途
        split_level: str = "doc",
        fold_filter: Optional[str] = None,  # 仅导出特定 fold
    ):
        """
        初始化过滤器
        
        Args:
            manifest_path: Manifest 文件路径
            purposes: 目标用途集合（如 {"P5", "EVAL"}）
            split_level: 分流粒度（doc/section）
            fold_filter: 仅导出特定 fold（dev/test，None 表示不过滤）
        """
        invalid_purposes = purposes - Constants.VALID_PURPOSES
        if invalid_purposes:
            raise ValueError(f"无效的 purpose: {invalid_purposes}，有效值: {Constants.VALID_PURPOSES}")
        if split_level not in Constants.VALID_SPLIT_LEVELS:
            raise ValueError(f"无效的 split_level: {split_level}，有效值: {Constants.VALID_SPLIT_LEVELS}")
        if fold_filter and fold_filter not in Constants.VALID_FOLDS:
            raise ValueError(f"无效的 fold_filter: {fold_filter}，有效值: {Constants.VALID_FOLDS}")
        
        self.manifest_path = manifest_path
        self.purposes = purposes
        self.split_level = split_level
        self.fold_filter = fold_filter
        self.stats = FilterStats()
        
        # 加载 manifest
        self.manifest: Dict[str, Dict[str, Any]] = {}  # doc_id -> manifest_entry
        self._load_manifest()
    
    def _load_manifest(self) -> None:
        """加载 manifest 文件"""
        logger.info(f"加载 manifest: {self.manifest_path}")
        
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    entry = json.loads(line)
                    doc_id = entry.get("doc_id", "")
                    if doc_id:
                        self.manifest[doc_id] = entry
                except json.JSONDecodeError:
                    continue
        
        # 统计
        purpose_counts: Dict[str, int] = {}
        for entry in self.manifest.values():
            p = entry.get("purpose", "UNKNOWN")
            purpose_counts[p] = purpose_counts.get(p, 0) + 1
        
        logger.info(f"Manifest 加载完成，共 {len(self.manifest)} 条记录")
        for p, count in sorted(purpose_counts.items()):
            logger.info(f"  - {p}: {count}")
    
    def _get_doc_id(self, doc: Dict[str, Any]) -> str:
        """从文档中提取 doc_id"""
        doc_id = doc.get("id")
        if doc_id:
            return str(doc_id)
        
        rel_path = doc.get("rel_path", "")
        if rel_path:
            return hashlib.md5(rel_path.encode()).hexdigest()[:12]
        
        text = doc.get("text", "")[:200]
        return hashlib.md5(text.encode()).hexdigest()[:12]
    
    def _section_filter(self, doc: Dict[str, Any], entry: Dict[str, Any]) -> bool:
        """章节级过滤实现"""
        section_hint = entry.get("section_hint", "")
        if not section_hint:
            return True
        
        # 基于 section_hint 判断是否包含
        text = doc.get("text", "")
        # 混合内容返回 True，由上层决定如何处理
        if section_hint in ["mixed_content", "mixed_p4_dominant"]:
            return True
        
        return True
    
    def should_include(self, doc: Dict[str, Any]) -> bool:
        """
        判断文档是否应该被包含
        
        Args:
            doc: 输入文档
        
        Returns:
            是否包含
        """
        self.stats.input_count += 1
        
        doc_id = self._get_doc_id(doc)
        entry = self.manifest.get(doc_id)
        
        if not entry:
            return False
        
        # 检查用途（支持多个）
        if entry.get("purpose") not in self.purposes:
            return False
        
        # 检查 fold（如果指定）
        if self.fold_filter and entry.get("fold") != self.fold_filter:
            return False
        
        # section 级分流
        if self.split_level == "section" and entry.get("split_level") == "section":
            self.stats.section_filtered += 1
            if not self._section_filter(doc, entry):
                return False
        
        self.stats.matched_count += 1
        return True
    
    def get_fold(self, doc: Dict[str, Any]) -> Optional[str]:
        """获取 EVAL 的 fold（dev/test）"""
        doc_id = self._get_doc_id(doc)
        entry = self.manifest.get(doc_id, {})
        return entry.get("fold")


def apply_manifest(
    input_path: Path,
    manifest_path: Path,
    output_path: Path,
    purposes: Set[str],
    split_level: str = "doc",
    fold_filter: Optional[str] = None,
) -> FilterStats:
    """
    应用 manifest 过滤语料
    
    Args:
        input_path: 输入 JSONL 文件
        manifest_path: Manifest 文件
        output_path: 输出文件
        purposes: 目标用途集合（支持多个，如 {"P5", "EVAL"}）
        split_level: 分流粒度
        fold_filter: 仅导出特定 fold
    
    Returns:
        过滤统计
    """
    logger.info(f"开始过滤...")
    logger.info(f"输入: {input_path}")
    logger.info(f"Manifest: {manifest_path}")
    logger.info(f"目标用途: {purposes}")
    logger.info(f"分流粒度: {split_level}")
    if fold_filter:
        logger.info(f"Fold 过滤: {fold_filter}")
    logger.info(f"输出: {output_path}")
    
    filter_obj = ManifestFilter(
        manifest_path=manifest_path,
        purposes=purposes,
        split_level=split_level,
        fold_filter=fold_filter,
    )
    
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # EVAL 需要额外输出 dev/test（仅当单独导出 EVAL 且未指定 fold_filter 时）
    dev_path: Optional[Path] = None
    test_path: Optional[Path] = None
    dev_file = None
    test_file = None
    
    if purposes == {"EVAL"} and not fold_filter:
        dev_path = output_path.parent / "dev.jsonl"
        test_path = output_path.parent / "test.jsonl"
        dev_file = open(dev_path, "w", encoding="utf-8")
        test_file = open(test_path, "w", encoding="utf-8")
    
    try:
        with open(input_path, "r", encoding="utf-8") as fin, \
             open(output_path, "w", encoding="utf-8") as fout:
            
            for line in fin:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    doc = json.loads(line)
                except json.JSONDecodeError:
                    continue
                
                if filter_obj.should_include(doc):
                    fout.write(line + "\n")
                    
                    # EVAL 拆分 dev/test
                    if purposes == {"EVAL"} and not fold_filter:
                        fold = filter_obj.get_fold(doc)
                        if fold == "dev" and dev_file:
                            dev_file.write(line + "\n")
                            filter_obj.stats.dev_count += 1
                        elif fold == "test" and test_file:
                            test_file.write(line + "\n")
                            filter_obj.stats.test_count += 1
    finally:
        if dev_file:
            dev_file.close()
        if test_file:
            test_file.close()
    
    # 打印统计
    logger.info("=" * 60)
    logger.info("过滤统计")
    logger.info("=" * 60)
    logger.info(f"输入总数: {filter_obj.stats.input_count}")
    logger.info(f"匹配数量: {filter_obj.stats.matched_count}")
    logger.info(f"过滤率: {filter_obj.stats.matched_count/max(filter_obj.stats.input_count,1)*100:.1f}%")
    
    if purposes == {"EVAL"} and not fold_filter:
        logger.info(f"Dev 数量: {filter_obj.stats.dev_count}")
        logger.info(f"Test 数量: {filter_obj.stats.test_count}")
        logger.info(f"Dev 文件: {dev_path}")
        logger.info(f"Test 文件: {test_path}")
    
    if filter_obj.stats.section_filtered > 0:
        logger.info(f"章节级过滤: {filter_obj.stats.section_filtered}")
    
    logger.info("=" * 60)
    logger.info(f"✅ 输出已保存到: {output_path}")
    
    # 保存运行配置
    config_path = output_path.with_suffix(".config.json")
    run_config = {
        "tool": Constants.TOOL_NAME,
        "version": Constants.VERSION,
        "timestamp": datetime.now().isoformat(),
        "input": str(input_path),
        "manifest": str(manifest_path),
        "output": str(output_path),
        "purposes": list(purposes),
        "split_level": split_level,
        "fold_filter": fold_filter,
        "stats": {
            "input_count": filter_obj.stats.input_count,
            "matched_count": filter_obj.stats.matched_count,
            "dev_count": filter_obj.stats.dev_count,
            "test_count": filter_obj.stats.test_count,
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(run_config, f, ensure_ascii=False, indent=2)
    logger.info(f"✅ 配置已保存到: {config_path}")
    
    return filter_obj.stats


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description=Constants.TOOL_NAME,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 导出 P5 语料（建图用）
  python filters/apply_manifest.py --input data/pool.jsonl --manifest data/manifests/manifest.jsonl \\
      --purpose P5 --out data/corpus_for_kg/p5_only.jsonl

  # 导出 EVAL 语料（自动拆分 dev/test）
  python filters/apply_manifest.py --input data/pool.jsonl --manifest data/manifests/manifest.jsonl \\
      --purpose EVAL --out data/p5_eval_pool/pool.jsonl

  # 同时导出 P5 和 EVAL
  python filters/apply_manifest.py --input data/pool.jsonl --manifest data/manifests/manifest.jsonl \\
      --purpose P5,EVAL --out data/corpus_for_kg/p5_eval.jsonl

  # 仅导出 EVAL 的 dev 集
  python filters/apply_manifest.py --input data/pool.jsonl --manifest data/manifests/manifest.jsonl \\
      --purpose EVAL --fold dev --out data/p5_eval_pool/dev_only.jsonl
        """,
    )
    
    parser.add_argument(
        "--input", "-i",
        type=Path,
        required=True,
        help="输入 JSONL 文件路径",
    )
    parser.add_argument(
        "--manifest", "-m",
        type=Path,
        required=True,
        help="Manifest 文件路径",
    )
    parser.add_argument(
        "--purpose", "-p",
        type=str,
        required=True,
        help="目标用途，多个用逗号分隔（如 P5,EVAL）",
    )
    parser.add_argument(
        "--out", "-o",
        type=Path,
        required=True,
        help="输出文件路径",
    )
    parser.add_argument(
        "--fold",
        type=str,
        default=None,
        choices=list(Constants.VALID_FOLDS),
        help="仅导出特定 fold（dev/test，仅对 EVAL 有效）",
    )
    parser.add_argument(
        "--split-level",
        type=str,
        default="doc",
        choices=list(Constants.VALID_SPLIT_LEVELS),
        help="分流粒度（doc/section，默认 doc）",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=None,
        help="日志文件路径",
    )
    
    return parser.parse_args()


def main() -> int:
    """主入口"""
    args = parse_args()
    
    # 重新配置 logger
    global logger
    logger = setup_logger(log_file=args.log_file)
    
    logger.info("=" * 60)
    logger.info(f"{Constants.TOOL_NAME} v{Constants.VERSION}")
    logger.info("=" * 60)
    
    # 检查输入文件
    if not args.input.exists():
        logger.error(f"输入文件不存在: {args.input}")
        return 1
    
    if not args.manifest.exists():
        logger.error(f"Manifest 文件不存在: {args.manifest}")
        return 1
    
    # 解析多用途
    purposes = set(p.strip().upper() for p in args.purpose.split(","))
    invalid_purposes = purposes - Constants.VALID_PURPOSES
    if invalid_purposes:
        logger.error(f"无效的 purpose: {invalid_purposes}，有效值: {Constants.VALID_PURPOSES}")
        return 1
    
    try:
        apply_manifest(
            input_path=args.input,
            manifest_path=args.manifest,
            output_path=args.out,
            purposes=purposes,
            split_level=args.split_level,
            fold_filter=args.fold,
        )
        return 0
    except Exception as e:
        logger.exception(f"过滤失败: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
