# -*- coding: utf-8 -*-
"""双层校验用例：接口响应 vs 数据库。

核心思想（双层校验）：
    普通用例只断言"接口说自己返回了什么"——那等于听后端自报成绩。
    双层校验再加一道保险：直查数据库，确认接口返回的数据在库里真实存在、
    数量一致。两端都对了，才算这条接口真的诚实。

比对的锚点是 id（dish 主键）：
    接口返回 list，DB 查出同分类、同 status 的行，两边各自取 id 组成集合。
    若两个集合相等 → 接口没多返回、没漏返回、每条都是库里真实数据。

数据驱动：查哪个分类、期望几条，来自 data/dish_cases.yaml。
"""
import allure
import pytest

from common.assert_util import AssertUtil
from common.report_util import attach_response
from common.yaml_util import load_yaml_data


def build_dish_cases():
    """读 yaml，拼成 (category_id, expect_count, case_id) 的参数。"""
    cases = load_yaml_data("dish_cases.yaml")["cases"]
    return [pytest.param(c["category_id"], c["expect_count"], id=c["id"]) for c in cases]


@allure.epic("苍穹外卖接口自动化")
@allure.feature("双层校验")
@allure.story("菜品接口对账数据库")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.parametrize("category_id, expect_count", build_dish_cases())
def test_dish_list_matches_db(user_client, db, category_id, expect_count):
    """用户端菜品列表：接口返回的菜品集合，必须与数据库一致。"""
    allure.dynamic.title(f"双层校验 - 分类{category_id}的菜品，接口返回与 DB 一致")

    # ---------- 第一层：走 HTTP 接口 ----------
    resp = user_client.request("GET", "/user/dish/list", params={"categoryId": category_id})
    body = resp.json()
    attach_response(resp)
    AssertUtil.code_ok(body, 1, "菜品列表业务码")
    api_dishes = body.get("data") or []

    # ---------- 第二层：直查数据库 ----------
    # 与接口同样口径：该分类下 status=1（在售）的菜品
    db_rows = db.query(
        "SELECT id, name FROM dish WHERE category_id=%s AND status=1", (category_id,)
    )

    # ---------- 双层对账 ----------
    # 两边各取 id 组成集合（集合无视顺序，只比"有哪些"）
    api_ids = {d["id"] for d in api_dishes}
    db_ids = {r["id"] for r in db_rows}

    # 断言1：数量一致（多返回 / 漏返回都能抓住）
    AssertUtil.equals(len(api_dishes), len(db_rows),
                      f"接口返回菜品数应等于 DB 行数（category_id={category_id}）")
    # 断言2：id 集合一致（逐条对上，证明没查错）
    AssertUtil.equals(api_ids, db_ids,
                      f"接口返回的菜品 id 集合应与 DB 一致（category_id={category_id}）")
    # 断言3：若 yaml 里写了期望数量，额外校验（不写则跳过，避免写死脆弱）
    if expect_count is not None:
        AssertUtil.equals(len(api_dishes), expect_count,
                          f"分类{category_id}菜品数应等于 yaml 期望值")
