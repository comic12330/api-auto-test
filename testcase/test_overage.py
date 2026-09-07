# 越权测试
import allure
import pytest

from common.request_client import RequestClient
from common.assert_util import AssertUtil
from common.yaml_util import load_config
from common.report_util import attach_response

ADMIN_PATH = "/admin/employee/page"
USER_PATH = "/user/dish/list"


@allure.epic("苍穹外卖接口自动化")
@allure.feature("权限安全")
@allure.story("越权拦截")
@allure.title("用户端凭证访问管理端接口应被拒绝")
@allure.severity(allure.severity_level.CRITICAL)
def test_user_token_cannot_access_admin(user_client, user_token):
    """① 越权：用户端凭证访问管理端接口，应被拦截"""
    resp = user_client.request("GET", ADMIN_PATH, headers={"token": user_token})
    attach_response(resp)
    AssertUtil.equals(resp.status_code, 401, "越权访问管理端应返回 401")


@allure.epic("苍穹外卖接口自动化")
@allure.feature("权限安全")
@allure.story("正向对照")
@allure.title("管理端凭证访问管理端接口应正常")
@allure.severity(allure.severity_level.NORMAL)
def test_admin_token_can_access_admin(admin_client):
    """② 对照：管理端凭证访问自己的接口正常 —— 证明接口本身是通的"""
    resp = admin_client.request("GET", ADMIN_PATH)
    attach_response(resp)
    AssertUtil.equals(resp.status_code, 200, "管理端凭证访问管理端接口状态码应为 200")
    AssertUtil.code_ok(resp.json(), 1, "管理端业务码应为 1")


@allure.epic("苍穹外卖接口自动化")
@allure.feature("权限安全")
@allure.story("凭证有效性")
@allure.title("用户端凭证访问用户端接口应正常")
@allure.severity(allure.severity_level.NORMAL)
def test_user_token_can_access_user(user_client):
    """③ 对照：用户端凭证访问自己的接口正常 —— 证明这个 token 本身有效"""
    resp = user_client.request("GET", USER_PATH, params={"categoryId": 1})
    attach_response(resp)
    AssertUtil.equals(resp.status_code, 200, "用户端凭证访问用户端接口状态码应为 200")
    AssertUtil.code_ok(resp.json(), 1, "用户端业务码应为 1")


@allure.epic("苍穹外卖接口自动化")
@allure.feature("菜品查询")
@allure.story("参数校验")
@allure.title("[已知缺陷] 缺失必填参数 categoryId 应返回 400")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.xfail(
    reason="缺陷：GET /user/dish/list 缺失必填参数 categoryId 时应返回 400，实际返回 500（入参校验缺失）",
    strict=True,
)
def test_dish_list_missing_categoryId_should_be_400(user_client):
    """④ 已知缺陷：必填参数缺失应返回 400，实际返回 500"""
    resp = user_client.request("GET", USER_PATH)
    attach_response(resp)
    AssertUtil.equals(resp.status_code, 400, "缺失必填参数 categoryId 应返回 400")
