import pytest
from common.yaml_util import load_config
from common.request_client import RequestClient
from api.login_api import login


@pytest.fixture(scope="session")
def admin_client():
    """管理端 client：整个会话只登录一次，返回带 token 的客户端。

    session 级 → 所有用例共享这一个 client，token 全局复用。
    """
    cnf = load_config()
    base_url = cnf["base_url"]
    admin_auth = cnf["auth"]
    rc = RequestClient(base_url)
    body, token = login(rc, admin_auth["admin_username"], admin_auth["admin_password"])
    rc.session.headers[admin_auth["admin_token_header"]] = token

    return rc
