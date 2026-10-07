import allure
import pytest

from api.employee_api import list_employee_page
from api.login_api import login
from common.assert_util import AssertUtil
from common.yaml_util import load_config, load_yaml_data


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
def test_login_success(admin_client):
    """正向：登录成功，校验 token 存在、非空、且为合法 JWT 三段结构。

    这里**不再自己 new RequestClient**，而是复用 session 级 admin_client：
    会话级 client 已由 conftest 统一建好，用例再建一个只会多开连接、
    绕开统一配置（超时 / 日志 / 报文证据都在 client 上）。
    """
    config = load_config()
    body, token = login(admin_client,
                        config["auth"]["admin_username"],
                        config["auth"]["admin_password"])

    AssertUtil.code_ok(body, 1, "登录业务码")
    AssertUtil.has_key(body["data"], "token", "响应应含有 token 字段")
    AssertUtil.not_empty(token, "token 不应为空")
    # JWT = 三段 base64url 用 "." 连接。正则比 `len(token.split(".")) == 3` 更严：
    # 后者只数段数，"a.b.c!!!" 也会通过，前者还约束了每段的字符集。
    AssertUtil.match(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$",
                     token, "token 应为三段 base64url 组成的合法 JWT")


@allure.epic("苍穹外卖接口自动化")
@allure.feature("登录鉴权")
@allure.story("异常凭证")
@pytest.mark.parametrize("username,password,expected_code,expected_msg,desc", build_login_cases())
def test_login_invalid_credential(admin_client, username, password, expected_code, expected_msg, desc):
    """异常凭证登录应被拒绝（数据来自 data/login_cases.yaml）"""
    allure.dynamic.title(f"异常登录 - {desc}")  # 参数化用例：每组数据一个中文标题
    body, _token = login(admin_client, username, password)

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
    body = list_employee_page(admin_client).json()
    AssertUtil.code_ok(body, 1, "员工分页查询业务码")
