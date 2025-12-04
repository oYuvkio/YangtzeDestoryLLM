"""
统一日志初始化工具：
- 从 cfg.logging 读取 level/fmt/datefmt/file
- CLI 可自行覆盖后传入 init_logging
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Dict, Optional


def init_logging(cfg_logging: Optional[Dict] = None) -> logging.Logger:
    """
    初始化全局日志，返回根 logger。

    Args:
        cfg_logging: 配置字典，包含 level/fmt/datefmt/file
    """
    cfg_logging = cfg_logging or {}
    level_str = str(cfg_logging.get("level", "info")).lower()
    level_map = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL,
    }
    level = level_map.get(level_str, logging.INFO)
    fmt = cfg_logging.get("fmt", "%(asctime)s | %(levelname)s | %(message)s")
    datefmt = cfg_logging.get("datefmt", "%Y-%m-%d %H:%M:%S")
    log_file = cfg_logging.get("file") or ""

    logger = logging.getLogger()
    if logger.handlers:
        return logger  # 已初始化

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(level=level, format=fmt, datefmt=datefmt, handlers=handlers)
    return logger
