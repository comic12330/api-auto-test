# -*- coding: utf-8 -*-
"""context.py —— 接口串联的核心：变量池 + jsonpath 提取 + ${} 渲染。

解决什么问题
------------
接口之间有依赖：查菜品要先用"查分类"拿到的 categoryId，加购物车要先用
"查菜品"拿到的 dishId。如果每个用例都手写 `resp.json()["data"][0]["id"]`：

  1. 重复代码，N 个用例写 N 遍；
  2. 响应结构一变要改 N 处；
  3. **没法写进 YAML** —— 数据驱动直接废掉（YAML 里放不了 Python 表达式）。

所以拆成三件事：

  1. **变量池**  ：提取出来的值按名字存起来，后续步骤按名字取；
  2. **提取**    ：用 jsonpath 表达式取值，比一层层 `[]` 稳（结构变了只改表达式）；
  3. **渲染**    ：请求里的 `${var}` 自动替换成变量池里的值 —— 这是让串联
                   能写进 YAML 的关键（HttpRunner 就是这个思路）。

用法
----
    rc.request("GET", "/user/category/list", params={"type": 1},
               extract={"category_id": "$.data[0].id"})     # 提取并存入变量池
    rc.request("GET", "/user/dish/list",
               params={"categoryId": "${category_id}"})      # 自动渲染成真实值
"""
import re

from jsonpath_ng.ext import parse

# 整个字符串就是一个变量，如 "${dish_id}"
_VAR_WHOLE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
# 变量嵌在字符串里，如 "菜品-${dish_id}"
_VAR_INLINE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class TestContext:
    """变量池。挂在 RequestClient 上，生命周期跟 client 一致。"""

    def __init__(self):
        self._vars = {}

    def set(self, name, value):
        """存一个变量，返回存入的值（方便链式/调试）。"""
        self._vars[name] = value
        return value

    def get(self, name, default=None):
        """取一个变量；不存在返回 default。"""
        return self._vars.get(name, default)

    def clear(self):
        """清空变量池。每个用例开跑前必须清一次，见 conftest._fresh_context。"""
        self._vars.clear()

    def as_dict(self):
        """返回副本，防止外部改到内部状态。"""
        return dict(self._vars)

    def render(self, obj):
        """递归把 obj 里的 `${var}` 替换成变量池中的值。

        两种形态要分开处理：
          - `"${dish_id}"`        → 替换成**原值**，保留类型
          - `"菜品-${dish_id}"`   → 字符串拼接，结果必然是 str

        为什么要保留类型：JSON 里的 `dishId` 后端期望是数字，
        如果渲染成字符串 `"66"`，轻则类型不匹配，重则后端直接报错。
        这个坑不处理，排查时你会以为是接口问题。
        """
        if isinstance(obj, str):
            m = _VAR_WHOLE.match(obj)
            if m:                                  # 整个就是变量 → 原值原类型
                name = m.group(1)
                return self._vars.get(name, obj)   # 没取到就原样返回，让错误暴露出来
            return _VAR_INLINE.sub(
                lambda x: str(self._vars.get(x.group(1), x.group(0))), obj
            )
        if isinstance(obj, dict):
            return {k: self.render(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self.render(v) for v in obj]
        return obj


def extract_by_jsonpath(data, expr):
    """用 jsonpath 表达式从响应数据里取值，返回第一个匹配项。

    取不到时抛**人话**异常：说清表达式是什么、数据长什么样。
    不这么做，表达式写错的报错是 `list index out of range`，
    你根本看不出是第几步、哪个字段出了问题。
    """
    matches = parse(expr).find(data)
    if not matches:
        raise AssertionError(
            f"jsonpath 提取失败：表达式={expr!r} 在响应里没匹配到任何值。"
            f"响应片段={str(data)[:300]}"
        )
    return matches[0].value
