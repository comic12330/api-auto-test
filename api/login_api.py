from common.request_client import RequestClient


def login(rc, username, password):
    """
    登录接口
    :param rc:外部传来请求客户端，不自己重新建，为确保都在同一会话之内
    """

    resp = rc.request(
        "POST",
        "/admin/employee/login",
        json={"username": username, "password": password},
    )
    body = resp.json()
    token = body["data"]["token"] if body.get("code") == 1 else None
    return body, token
