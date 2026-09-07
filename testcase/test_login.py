import allure
import pytest

from common.request_client import RequestClient
from common.assert_util import AssertUtil
from common.yaml_util import load_config, load_yaml_data
from common.report_util import attach_response


def build_login_cases():
    """从 yaml 读数据，动态拼成 parametrize 需要的参数列表。"""
    cases = load_yaml_data("login_cases.yaml")["cases"]
    params = []
    for c in cases:
        marks = []
        if c.get("xfail"):  # 缺陷标记由数据决定，不是写死在代码里
            marks.append(pytest.mark.xfail(reason=c.get("reason", ""), strict=True))
        params.append(
            pytest.param(c["username"], c["password"], c["expect_code"], c.get("expect_msg"), c["desc"],
                         marks=marks, id=c["id"])
        )
    return params


@allure.epic("苍穹外卖接口自动化")
@allure.feature("登录鉴权")
@allure.story("正向登录")
@allure.title("管理员使用正确账号密码登录成功")
@allure.severity(allure.severity_level.BLOCKER)
def test_login_success():
    """正向：登录成功，校验 token 存在、非空、且为合法 JWT 三段结构"""
    config = load_config()
    rc = RequestClient(config["base_url"])
    resp = rc.request(
        "POST",
        "/admin/employee/login",
        json={"username": config["auth"]["admin_username"], "password": config["auth"]["admin_password"]},
    )
    body = resp.json()
    attach_response(resp)

    AssertUtil.equals(resp.status_code, 200, "HTTP 状态码")
    AssertUtil.code_ok(body, 1, "登录业务码")
    AssertUtil.has_key(body["data"], "token", "响应应含有 token 字段")
    AssertUtil.not_empty(body["data"]["token"], "token 不应为空")
    AssertUtil.equals(len(body["data"]["token"].split(".")), 3, "JWT 应由三段组成")


@allure.epic("苍穹外卖接口自动化")
@allure.feature("登录鉴权")
@allure.story("异常凭证")
@pytest.mark.parametrize("username,password,expected_code,expected_msg,desc", build_login_cases())
def test_login_invalid_credential(username, password, expected_code, expected_msg, desc):
    """异常凭证登录应被拒绝（数据来自 data/login_cases.yaml）"""
    allure.dynamic.title(f"异常登录 - {desc}")  # 参数化用例：每组数据一个中文标题
    config = load_config()
    rc = RequestClient(config["base_url"])
    resp = rc.request("POST", "/admin/employee/login", json={"username": username, "password": password})
    body = resp.json()
    attach_response(resp)

    AssertUtil.equals(resp.status_code, 200, "HTTP 状态码")
    AssertUtil.code_ok(body, expected_code, "异常登录业务码")
    if expected_msg is not None:
        AssertUtil.equals(body.get("msg"), expected_msg, "异常提示信息")


@allure.epic("苍穹外卖接口自动化")
@allure.feature("员工管理")
@allure.story("分页查询")
@allure.title("管理端凭证查询员工分页列表")
@allure.severity(allure.severity_level.NORMAL)
def test_employeeList_success(admin_client):
    """员工分页查询：复用 session 级 admin_client，不再重复登录"""
    resp = admin_client.request("GET", "/admin/employee/page")
    attach_response(resp)
    AssertUtil.code_ok(resp.json(), 1, "员工分页查询业务码")
