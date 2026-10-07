# -*- coding: utf-8 -*-
"""order_api.py —— 订单接口封装（用户端下单 / 管理端履约）。

完整业务链路（这是整个框架最难也最值钱的一条）：

    用户端 submit(下单)   → status 1 待付款
    → payment(支付)       → status 2 待接单      ← 调微信支付，本地跑不通
    → 管理端 confirm      → status 3 已接单
    → 管理端 delivery     → status 4 派送中
    → 管理端 complete     → status 5 已完成

状态常量（源码 `sky-pojo/.../entity/Orders.java`，别背错）：
    1 待付款 | 2 待接单 | 3 已接单 | 4 派送中 | 5 已完成 | 6 已取消

⚠️ 状态校验的真实分布（读源码 + 实测，别想当然）：
`delivery` / `complete` / `rejection` 三个方法都有硬校验，状态不对会抛
`OrderBusinessException("订单状态错误")`；
但 **`confirm`（接单）一个校验都没有** —— 它直接 `update` 把 status 写成 3，
已取消、已完成、甚至不存在的 id 都照收不误（见 README 缺陷⑤）。

从"待付款"到"待接单"这一段，`payment` 在本地跑不通（调真实微信支付），
所以 `conftest.submitted_order` 用一行 DB SQL 推过去 —— 那是**环境妥协**，
不是被 `confirm` 的校验逼的。
"""
from datetime import datetime, timedelta


def submit_order(rc, address_book_id, remark=None, pay_method=1, **kw):
    """POST /user/order/submit 提交订单（用户端）。

    :param address_book_id: 地址簿 id，必填
    :param pay_method: 1 微信 / 2 支付宝
    :param remark: 备注。自动化用例建议传带标记的值，方便事后识别脏数据
    :return: 响应对象。`data` 里含 `id`（订单主键）和 `orderNumber`
    """
    eta = (datetime.now() + timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S")
    return rc.request("POST", "/user/order/submit", json={
        "addressBookId": address_book_id,
        "payMethod": pay_method,
        "remark": remark,
        "estimatedDeliveryTime": eta,      # 格式 yyyy-MM-dd HH:mm:ss，后端 @JsonFormat 有要求
        "deliveryStatus": 1,               # 1 立即送出
        "tablewareNumber": 1,
        "tablewareStatus": 1,              # 1 按餐量提供
        "packAmount": 1,
        "amount": 0,                       # 后端会按购物车重算，这里传什么都会被覆盖
    }, **kw)


def pay_order(rc, order_number, pay_method=1, **kw):
    """PUT /user/order/payment 支付（用户端）。

    ⚠️ 本环境**跑不通**：后端要调 `WeChatPayUtil` 走真实微信支付。
    保留这个方法是为了说明链路完整性，用例里不调用它。
    """
    return rc.request("PUT", "/user/order/payment", json={
        "orderNumber": order_number,
        "payMethod": pay_method,
    }, **kw)


def cancel_order(rc, order_id, **kw):
    """PUT /user/order/cancel/{id} 取消订单（用户端）。"""
    return rc.request("PUT", f"/user/order/cancel/{order_id}", **kw)


def get_user_order_detail(rc, order_id, **kw):
    """GET /user/order/orderDetail/{id} 查订单详情（用户端）。"""
    return rc.request("GET", f"/user/order/orderDetail/{order_id}", **kw)


# ---------- 管理端：履约 ----------

def confirm_order(rc, order_id, **kw):
    """PUT /admin/order/confirm 接单。

    ⚠️ 两个反直觉的事实（读源码 + 实测确认）：
      ① 请求体里的 `status` 是**死参数** —— Service 内部直接
         `Orders.builder().id(...).status(CONFIRMED)`，压根不读 DTO 的 status，
         传 99 也照样写成 3。
      ② 这个方法**没有任何状态校验**（对比 delivery / complete 都有）：
         已取消(6) / 已完成(5) 的订单都能被重新"接单"成 3，
         不存在的 id 也返回 code=1（见 README 缺陷⑤）。
    请求体仍按接口定义传 `{id, status}`，与后端 DTO 形状保持一致。
    """
    return rc.request("PUT", "/admin/order/confirm", json={
        "id": order_id,
        "status": 3,                       # 已接单
    }, **kw)


def delivery_order(rc, order_id, **kw):
    """PUT /admin/order/delivery/{id} 派送。"""
    return rc.request("PUT", f"/admin/order/delivery/{order_id}", **kw)


def complete_order(rc, order_id, **kw):
    """PUT /admin/order/complete/{id} 完成。"""
    return rc.request("PUT", f"/admin/order/complete/{order_id}", **kw)


def get_admin_order_detail(rc, order_id, **kw):
    """GET /admin/order/details/{id} 查订单详情（管理端）。"""
    return rc.request("GET", f"/admin/order/details/{order_id}", **kw)


# ---------- DB：对账与清理 ----------
# 按本项目的约定（见 employee_api.py），同一业务模块的 DB 查询也收在这里，
# 让"造数/对账/清理"三件事在代码里挨着。

def select_order_by_id(db, order_id):
    """按主键查订单主记录；没查到返回 None。"""
    return db.query_one(
        "SELECT id, number, status, user_id, amount, pay_status FROM orders WHERE id=%s",
        (order_id,),
    )


def select_order_details(db, order_id):
    """查订单明细（一个订单可能有多条，对应多个菜品）。"""
    return db.query(
        "SELECT id, order_id, dish_id, name, number, amount FROM order_detail WHERE order_id=%s",
        (order_id,),
    )


def delete_order_by_id(db, order_id):
    """按主键删除订单及其明细（测试环境专用清理动作）。

    为什么要直接删库：订单**没有删除接口**，`cancel` 只是把状态改成 6，
    记录还在表里。要让用例可重复执行，只能直连 DB 删。

    ⚠️ 删除顺序「先明细后主表」—— 但**不是因为有外键**。
    实测本库 `information_schema.KEY_COLUMN_USAGE` 里 **外键约束总数为 0**：
    `order_detail` 与 `orders` 都只有主键，没有 FOREIGN KEY。
    所以顺序反了**不会报错**。按"先子后父"删只是逻辑更清晰、
    也为将来加外键留余量。
    反证：库里现存 **2878 条孤儿明细**（`order_id` 指向已不存在的订单）——
    真有外键的话，这些孤儿根本不可能存在。
    （此处早前写"有外键、顺序反了会报错"，与库实况不符，已修正。）
    """
    db.execute("DELETE FROM order_detail WHERE order_id=%s", (order_id,))
    return db.execute("DELETE FROM orders WHERE id=%s", (order_id,))
