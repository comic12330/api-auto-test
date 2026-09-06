# -*- coding: utf-8 -*-
"""yaml_util.py —— 读取 config.yaml 与 data/*.yaml 测试数据。"""
import os
from functools import lru_cache

import yaml

# 项目根目录 = common 的上一级
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@lru_cache(maxsize=None)
def load_config() -> dict:
    """读取 config.yaml（带缓存，全进程只读一次）。"""
    cfg_path = os.path.join(PROJECT_ROOT, "config.yaml")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_yaml_data(relative_path: str) -> dict:
    """读取 data/ 目录下的 YAML 测试数据文件。

    Args:
        relative_path: 相对 data/ 的路径，如 "login_data.yaml"
    Returns:
        解析出的 dict（list 场景建议直接在测试里用参数文件）
    """
    path = os.path.join(PROJECT_ROOT, "data", relative_path)
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_data_file_abs(relative_path: str) -> str:
    """返回 data 目录下文件的绝对路径（给 pytest 读入参用）。"""
    return os.path.join(PROJECT_ROOT, "data", relative_path)
