# -*- coding: utf-8 -*-
"""下单业务链路用例（P1-10）—— 整个框架最难也最值钱的一条。

跨端：用户端下单 → 管理端履约（接单 → 派送 → 完成）。
多表联动：`orders`（主表）+ `order_detail`（明细）+ `shopping_cart`（下单后清空）。

每一步都做**接口 + DB 双层断言**：
接口返回 `code=1` 只能说明"接口没报错"，
状态到底推进到哪一步，只有查库才知道。
"""
import allure

from api.order_api import (
    cancel_order,
    complete_order,
    confirm_order,
    delivery_order,
    get_user_order_detail,
    select_order_by_id,
    select_order_details,
)
from api.shopping_api import list_cart
from common.assert_util import AssertUtil


@allure.feature("下单业务链路")
@allure.story("管理端履约")
@allure.title("跨端链路：用户下单 → 接单 → 派送 → 完成，每步查库对账")
def test_order_full_lifecycle(submitted_order, admin_client, user_client, db):
    """完整状态流转：2 待接单 → 3 已接单 → 4 派送中 → 5 已完成。"""
    order_id = submitted_order

    # 起点必须是「待接单」，否则后面的接单会失败（后端有硬校验）
    AssertUtil.equals(select_order_by_id(db, order_id)["status"], 2,
                      "链路起点应为待接单(2)")

    # ① 接单：管理端
    AssertUtil.code_ok(confirm_order(admin_client, order_id).json(), 1, "管理端接单")
    AssertUtil.equals(select_order_by_id(db, order_id)["status"], 3,
                      "接单后 DB 状态应为已接单(3)")

    # ② 派送
    AssertUtil.code_ok(delivery_order(admin_client, order_id).json(), 1, "管理端派送")
    AssertUtil.equals(select_order_by_id(db, order_id)["status"], 4,
                      "派送后 DB 状态应为派送中(4)")

    # ③ 完成
    AssertUtil.code_ok(complete_order(admin_client, order_id).json(), 1, "管理端完成")
    AssertUtil.equals(select_order_by_id(db, order_id)["status"], 5,
                      "完成后 DB 状态应为已完成(5)")

    # ④ 用户端能查到这张订单（跨端数据一致）
    body = get_user_order_detail(user_client, order_id).json()
    AssertUtil.code_ok(body, 1, "用户端查询订单详情")


@allure.feature("下单业务链路")
@allure.story("落库校验")
@allure.title("下单后 orders + order_detail 同时落库，购物车被清空")
def test_order_submit_written_to_db(submitted_order, user_client, db):
    """多表联动：主表、明细表、购物车三处都要对得上。"""
    order = select_order_by_id(db, submitted_order)
    AssertUtil.not_empty(order, "订单主表应落库")
    AssertUtil.equals(order["status"], 2, "新订单应处于待接单(2)")

    details = select_order_details(db, submitted_order)
    AssertUtil.not_empty(details, "订单明细表应落库（至少 1 个菜品）")
    for d in details:
        AssertUtil.equals(d["order_id"], submitted_order, "明细的 order_id 应与主表一致")

    # 下单会清空购物车 —— 这是业务规则，也是最容易漏验的一条
    cart = list_cart(user_client).json()
    AssertUtil.code_ok(cart, 1, "查询购物车")
    AssertUtil.equals(len(cart["data"]), 0, "提交订单后购物车应被清空")


@allure.feature("下单业务链路")
@allure.story("逆向流程")
@allure.title("用户端取消订单，状态应转为已取消(6)")
def test_order_cancel_by_user(submitted_order, user_client, db):
    """逆向流程：正向链路测完，取消这条也要测 —— 状态机是双向的。"""
    AssertUtil.code_ok(cancel_order(user_client, submitted_order).json(), 1,
                       "用户端取消订单")
    AssertUtil.equals(select_order_by_id(db, submitted_order)["status"], 6,
                      "取消后 DB 状态应为已取消(6)")
