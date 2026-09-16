"""通用工具: 配置加载、日志、环境变量读取。"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

import yaml


def load_config(path: str) -> Dict[str, Any]:
    """读取 YAML 配置文件; 文件不存在时给出明确提示。"""
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"找不到配置文件 {path!r}。可复制 config.example.yaml 为 config.yaml 后修改。"
        )
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    if not isinstance(cfg, dict):
        raise ValueError("配置文件格式不正确, 应为 YAML 映射结构。")
    return cfg


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("litpush")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
        )
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def env(name: str, required: bool = False, default: Optional[str] = None) -> Optional[str]:
    """读取环境变量; required 时缺失抛错。"""
    value = os.environ.get(name)
    if value is None or value == "":
        if required:
            raise RuntimeError(f"缺少必需的环境变量 {name}, 请在本地环境或 GitHub Secrets 中配置。")
        return default
    return value
