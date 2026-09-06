from common.request_client import RequestClient
from common.assert_util import AssertUtil
from common.yaml_util import load_config


def test_login_success():
    """正向的测试用例"""
    config = load_config()
    base_url = config['base_url']
    rc = RequestClient(base_url)
    resp = rc.request(
        "POST",
        "/admin/employee/login",
        json={"username": "admin", "password": "123456"},
    )
    body = resp.json()

    # 分层断言
    AssertUtil.equals(resp.status_code, 200, "http响应状态码")
    AssertUtil.code_ok(body, 1, "登录业务码")
    AssertUtil.has_key(body["data"], "token", "含有token")


def test_employeeList_success(admin_client):
    resp = admin_client.request("GET", "/admin/employee/page")
    body = resp.json()
    AssertUtil.code_ok(body, 1, "员工分页查询业务码")
