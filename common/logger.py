# -*- coding: utf-8 -*-
"""logger.py —— 统一日志封装：控制台 + 文件。"""
import logging
import os

from common.yaml_util import PROJECT_ROOT, load_config

_configured = False


def get_logger(name: str = "api_test") -> logging.Logger:
    """获取统一 logger（首次调用时初始化控制台 + 文件双 handler）。"""
    global _configured
    logger = logging.getLogger(name)

    if _configured:
        return logger

    cfg = load_config().get("logging", {})
    level = getattr(logging, cfg.get("level", "INFO").upper(), logging.INFO)
    log_file = os.path.join(PROJECT_ROOT, cfg.get("log_file", "logs/run.log"))

    logger.setLevel(level)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台
    sh = logging.StreamHandler()
    sh.setLevel(level)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    # 文件（目录不存在则创建）
    log_dir = os.path.dirname(log_file)
    os.makedirs(log_dir, exist_ok=True)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(level)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # 避免 pytest 的 root logger 重复打印
    logger.propagate = False
    _configured = True
    return logger
