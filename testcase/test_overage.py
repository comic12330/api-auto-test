# 越权测试
import allure
import pytest

from api.employee_api import list_employee_page
from api.shopping_api import list_dish
from common.assert_util import AssertUtil


@allure.epic("食汇本地生活平台接口自动化")
@allure.feature("权限安全")
@allure.story("越权拦截")
@allure.title("用户端凭证访问管理端接口应被拒绝")
@allure.severity(allure.severity_level.CRITICAL)
def test_user_token_cannot_access_admin(user_client, user_token):
    """① 越权：把**用户端签发的凭证塞进管理端 header 名**，去打管理端接口，应被拦截。

    header 名刻意用 `token`（管理端那个），值却是用户端 JWT ——
    这才是"越权尝试"的真实形态：拦截器必须靠**验签失败**挡住它，
    而不是靠"header 名写错了"。如果只测 header 名不对，测不出任何安全性。
    """
    resp = list_employee_page(user_client, headers={"token": user_token})
    AssertUtil.equals(resp.status_code, 401, "越权访问管理端应返回 401")


@allure.epic("食汇本地生活平台接口自动化")
@allure.feature("权限安全")
@allure.story("正向对照")
@allure.title("管理端凭证访问管理端接口应正常")
@allure.severity(allure.severity_level.NORMAL)
def test_admin_token_can_access_admin(admin_client):
    """② 对照：管理端凭证访问自己的接口正常 —— 证明接口本身是通的"""
    resp = list_employee_page(admin_client)
    AssertUtil.equals(resp.status_code, 200, "管理端凭证访问管理端接口状态码应为 200")
    AssertUtil.code_ok(resp.json(), 1, "管理端业务码应为 1")


@allure.epic("食汇本地生活平台接口自动化")
@allure.feature("权限安全")
@allure.story("凭证有效性")
@allure.title("用户端凭证访问用户端接口应正常")
@allure.severity(allure.severity_level.NORMAL)
def test_user_token_can_access_user(user_client):
    """③ 对照：用户端凭证访问自己的接口正常 —— 证明这个 token 本身有效"""
    resp = list_dish(user_client, 1)
    AssertUtil.equals(resp.status_code, 200, "用户端凭证访问用户端接口状态码应为 200")
    AssertUtil.code_ok(resp.json(), 1, "用户端业务码应为 1")


@allure.epic("食汇本地生活平台接口自动化")
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
    # 传 None → requests 会跳过值为 None 的 param，等价于"完全不带 categoryId"
    resp = list_dish(user_client, None)
    AssertUtil.equals(resp.status_code, 400, "缺失必填参数 categoryId 应返回 400")
