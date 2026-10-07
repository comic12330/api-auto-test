# -*- coding: utf-8 -*-
"""下单业务链路用例（P1-10）—— 整个框架最难也最值钱的一条。

跨端：用户端下单 → 管理端履约（接单 → 派送 → 完成）。
多表联动：`orders`（主表）+ `order_detail`（明细）+ `shopping_cart`（下单后清空）。

每一步都做**接口 + DB 双层断言**：
接口返回 `code=1` 只能说明"接口没报错"，
状态到底推进到哪一步，只有查库才知道。
"""
from decimal import Decimal

import allure
import pytest

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

    # 起点断言：链路必须从「待接单(2)」出发，后面 3→4→5 才成立。
    # ⚠️ 不是 confirm 要求的 —— confirm 无任何状态校验（见 README 缺陷表⑤）。
    # 断言起点是为了保证后续推进处在合法的业务链路上，而不是因为接口会拒绝。
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

    # ④ 用户端能查到这张订单 —— 这里要验的是**跨端数据一致**，
    #    所以必须逐字段与库对账，不能只断 `code=1`。
    #    （只断 code 是「空断言」：接口只要返回成功就绿，一个字段都没验到，
    #      连"返回的是不是这张订单"都不知道。原先注释写"跨端数据一致"，
    #      与断言强度不符，已按事实修正。）
    body = get_user_order_detail(user_client, order_id).json()
    AssertUtil.code_ok(body, 1, "用户端查询订单详情")

    detail = body["data"]
    order_row = select_order_by_id(db, order_id)
    AssertUtil.equals(detail["id"], order_id, "用户端详情应返回该订单")
    AssertUtil.equals(detail["number"], order_row["number"], "订单编号应与库一致")
    AssertUtil.equals(detail["status"], order_row["status"], "订单状态应与库一致")
    AssertUtil.equals(Decimal(str(detail["amount"])), Decimal(str(order_row["amount"])),
                      "订单金额应与库一致")
    # 明细也要对得上：id 集合必须与库完全一致，不能只看条数
    AssertUtil.equals(
        sorted(d["id"] for d in detail["orderDetailList"]),
        sorted(d["id"] for d in select_order_details(db, order_id)),
        "订单明细应与库完全一致",
    )


@allure.feature("下单业务链路")
@allure.story("越权（数据归属）")
@allure.title("用户端订单详情应校验归属：拿别人的 token 不应读到这张订单")
@pytest.mark.xfail(strict=True,
                   reason="缺陷⑥：orderDetail 不校验数据归属，任意 user token 可读任意订单（见 README 缺陷表）")
def test_order_detail_should_reject_other_user(submitted_order, stranger_client, db):
    """越权门禁：用**另一个用户**的身份去读这张订单，应当被拒绝。

    对照 `historyOrders`：它把 `userId` 塞进了查询条件
    （`BaseContext.getCurrentId()`），列表天然只能看到自己的；
    而 `orderDetail(id)` 只按 id 查，没有任何归属校验 ——
    JWT 拦截器只保证"这个 token 合法"，不保证"这张订单属于他"。

    缺陷修复后这条会 XPASS，`xfail_strict=true` 让流水线变红提醒清理标记。
    """
    owner_id = select_order_by_id(db, submitted_order)["user_id"]

    body = get_user_order_detail(stranger_client, submitted_order).json()
    data = body.get("data") or {}

    assert data.get("id") != submitted_order, (
        f"越权成功：订单 {submitted_order}（归属 userId={owner_id}）"
        f"被另一个用户的 token 读到了，响应里 userId={data.get('userId')}"
    )


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


@allure.feature("下单业务链路")
@allure.story("状态机校验")
@allure.title("接单应校验状态：已取消的订单不应被重新接单")
@pytest.mark.xfail(strict=True,
                   reason="缺陷⑤：/admin/order/confirm 无任何状态校验（见 README 缺陷表）")
def test_confirm_should_reject_invalid_status(submitted_order, admin_client, user_client, db):
    """状态机完整性门禁 —— `confirm` 是该系统订单动作里**唯一没有校验**的那个。

    读源码（`OrderServiceImpl`）可以看到校验的真实分布：

        delivery   → if (status != 3) throw OrderBusinessException
        complete   → if (status != 4) throw OrderBusinessException
        rejection  → if (status != 2) throw OrderBusinessException
        confirm    → 无任何判断，直接 update 把 status 写成 3

    探针场景选「已取消(6)」：一张已经取消掉的订单，被管理端重新"接单"成
    已接单(3) —— 业务上这绝不该发生（用户已经放弃的订单会被重新派单）。

    ⚠️ 前置用**真实接口** `cancel_order` 把状态推到 6，而不是直接改库 ——
    要验的是"接口允许非法状态转移"，起点就必须是接口产生的合法状态，
    否则测到的只是"我手工给了个脏状态，接口没拦住"。

    缺陷修复后这条会 XPASS，`xfail_strict=true` 让流水线变红提醒清理标记。

    同源的另外两个场景实测同样成立，不在本用例重复（一条用例只留一个断点，
    否则第一个断言失败后面的根本不会执行）：
      - 已完成(5) 的订单同样能被"接单"回 3；
      - **不存在的 id** 也返回 code=1（update 影响 0 行，但接口层没接返回值）。
    """
    # 前置：走真实接口取消订单（2 待接单 → 6 已取消）
    AssertUtil.code_ok(cancel_order(user_client, submitted_order).json(), 1,
                       "前置：用户端取消订单")
    AssertUtil.equals(select_order_by_id(db, submitted_order)["status"], 6,
                      "前置条件：取消后应为已取消(6)")

    # 管理端"接单" —— 正确行为是被拒绝
    body = confirm_order(admin_client, submitted_order).json()
    after = select_order_by_id(db, submitted_order)["status"]

    assert body.get("code") != 1, (
        f"缺陷⑤：已取消(6)的订单被重新接单 —— 接口返回 code={body.get('code')}，"
        f"DB 状态 6 → {after}（应被拒绝且保持 6）"
    )
