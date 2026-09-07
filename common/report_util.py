# -*- coding: utf-8 -*-
"""report_util.py —— Allure 报告相关的辅助方法。"""
import allure


def attach_response(resp, name="响应体"):
    """把接口响应原文贴进 Allure 报告，作为用例的可见证据。

    ⚠️ 调用时机：必须在断言**之前**。
    断言失败会抛异常，异常后面的代码不会再执行 ——
    而恰恰是用例失败的时候，最需要看响应原文来定位问题。

    用 resp.text 而不是 resp.json()：
    500 / 401 这类响应体可能不是合法 JSON（甚至是空的），
    json() 会直接抛异常，反而把真正的失败原因盖掉。
    """
    allure.attach(
        f"HTTP {resp.status_code}\n\n{resp.text}",
        name=name,
        attachment_type=allure.attachment_type.TEXT,
    )
