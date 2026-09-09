# -*- coding: utf-8 -*-
"""test_category.py —— 管理端分类接口用例。"""
import allure
import pytest

from api.category_api import delete_category
from common.assert_util import AssertUtil


@allure.feature("分类管理")
@allure.story("新增分类写后落库")
@allure.title("新增分类后直查库：字段一致 + 默认启用")
def test_category_created_in_db(created_category):
    """新增分类 → 直查库确认真的写进去了、写得对。

    数据由 created_category fixture 造，用例跑完自动清理，
    所以这里可以放心断言"库里现在应该有这条"。
    """
    _category_id, payload, row = created_category

    AssertUtil.equals(row["name"], payload["name"], "落库 name 与请求一致")
    AssertUtil.equals(row["type"], payload["type"], "落库 type 与请求一致")
    AssertUtil.equals(row["sort"], payload["sort"], "落库 sort 与请求一致")
    # 这条断言的价值：status 是后端默认填的，接口响应里根本不返回，只有查库才知道。
    # 实测结论：新分类默认是**禁用 0**（CategoryServiceImpl.save 里写死
    # setStatus(StatusConstant.DISABLE)），跟新增员工默认启用(1)正好相反。
    # 教训：别拿另一个接口的经验做类比，要么查源码要么实测。
    AssertUtil.equals(row["status"], 0, "新分类默认禁用 status=0")


@allure.feature("分类管理")
@allure.story("删除分类的业务规则")
@allure.title("分类下挂了菜品/套餐时，删除必须被拒绝且数据不能少")
@pytest.mark.parametrize(
    "category_id, keyword",
    [(11, "菜品"), (13, "套餐")],
    ids=["被菜品关联", "被套餐关联"],
)
def test_delete_related_category_should_be_rejected(admin_client, db, category_id, keyword):
    """业务规则：分类下关联了菜品或套餐时禁止删除。

    用的是**存量数据**（id=11 挂 2 个菜品、id=13 挂 1 个套餐），只读不写，
    所以不需要造数、不需要清理 —— 这正是"读对账"和"写后落库"的分界：
    只有要写库的用例才需要 yield 造删对称。
    """
    body = delete_category(admin_client, category_id).json()

    AssertUtil.not_equals(body.get("code"), 1, f"挂了{keyword}的分类不该删除成功")
    assert keyword in (body.get("msg") or ""), (
        f"提示应说明被{keyword}关联，实际 msg={body.get('msg')}"
    )

    # 光看接口返回还不够：必须确认库里数据还在。
    # 否则"拒绝"可能只是接口嘴上说说，实际已经删了。
    row = db.query_one("SELECT id FROM category WHERE id=%s", (category_id,))
    assert row is not None, f"接口说不能删，但 id={category_id} 已经从库里消失了"
