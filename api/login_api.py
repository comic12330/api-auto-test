# -*- coding: utf-8 -*-
"""login_api.py —— 管理端登录接口封装。

为什么登录也要单独成一层：登录既是"被测对象"（用例要测它），
又是"前置动作"（conftest.admin_client 靠它拿 token）。
两处共用同一份实现，就不会出现"用例里写一套、fixture 里另写一套"的重复。
"""


def login(rc, username, password):
    """POST /admin/employee/login 管理端登录。

    返回 `(body, token)`：
      - body  —— 完整响应体，交给用例做断言（业务码 / msg）
      - token —— 成功时是 JWT 字符串，失败时为 None

    为什么两个都返回：token 是"能直接用的结果"，body 是"能断言的原貌"。
    只返回 token 的话，用例就没法断言失败路径的提示语了。

    :param rc: 外部传入的请求客户端，**不在这里新建** ——
        必须复用同一会话，否则每调一次登录就多开一个 Session，
        与 conftest 里 session 级 client 的设计直接冲突。
    """
    resp = rc.request(
        "POST",
        "/admin/employee/login",
        json={"username": username, "password": password},
    )
    body = resp.json()
    token = body["data"]["token"] if body.get("code") == 1 else None
    return body, token
