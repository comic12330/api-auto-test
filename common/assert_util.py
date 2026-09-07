# 断言工具
import re


class AssertUtil:
    """统一断言入口：失败抛 AssertionError，测试标红。"""

    @staticmethod
    def equals(actual, expected, msg="值不相等"):
        """精确值断言"""
        assert actual == expected, f"{msg} | 实际={actual}, 期望={expected}"

    @staticmethod
    def code_ok(body, expected =1, msg="业务码不正确"):
        """业务码断言：该系统成功 code==1"""
        assert body.get("code") == expected , f"{msg} | 期望code={expected }, 实际code={body.get('code')}, msg={body.get('msg')}"

    @staticmethod
    def contains(text, sub, msg="不包含期望内容"):
        """子串包含断言"""
        assert sub in text, f"{msg} | 实际={text}, 期望包含={sub}"

    @staticmethod
    def match(pattern, text, msg="正则不匹配"):
        """正则断言"""
        assert re.search(pattern, text), f"{msg} | 文本={text}, 模式={pattern}"

    @staticmethod
    def has_key(dic, key, msg="缺少字段"):
        """结构断言：字段存在"""
        assert key in dic, f"{msg} | 实际keys={list(dic.keys())}, 期望有={key}"

    @staticmethod
    def not_empty(value, msg="值不应为空"):
        assert value, f"{msg} | 实际={value!r}"

    @staticmethod
    def not_equals(actual, expected, msg="值不应相等"):
        """反向断言：用于"这个操作本该失败"的负向用例（如重复数据应被拒绝）。"""
        assert actual != expected, f"{msg} | 实际={actual}, 不期望={expected}"
