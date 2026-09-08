# -*- coding: utf-8 -*-
"""接口串联用例：分类 → 菜品 → 购物车。

演示 P1-9「jsonpath 提取 + 上下游传参」：
**每一步的输入都来自上一步的输出**，用例里不出现任何硬编码的 id。

为什么这条链路值得单独做：
它是下单业务链路的前置——下单就是从购物车 submit。
串联能力做不出来，下单链路就只能靠写死 dishId，那不叫业务链路，
那叫"把三个独立接口各调一遍"。
"""
import allure

from api.shopping_api import add_to_cart, list_cart, list_category, list_dish
from common.assert_util import AssertUtil


@allure.feature("接口串联")
@allure.story("分类 → 菜品 → 购物车")
@allure.title("三步串联：每步输入来自上一步输出，全链路无硬编码 id")
def test_cart_add_by_chain(user_client, empty_cart):
    """上下游传参：提取 → 存变量池 → 下一步用 ${} 引用。"""
    # ① 查分类，提取第一个分类的 id
    r1 = list_category(user_client, extract={"category_id": "$.data[0].id"})
    AssertUtil.code_ok(r1.json(), 1, "查询菜品分类")
    category_id = user_client.ctx.get("category_id")
    AssertUtil.not_empty(category_id, "分类 id 应提取成功")

    # ② 用 ${category_id} 查该分类下的菜品，提取第一个菜品的 id
    #    注意这里传的是字符串 "${category_id}"，不是 python 变量 ——
    #    框架会在发请求前把它渲染成真实值，这样同样的调用就能写进 YAML。
    r2 = list_dish(user_client, "${category_id}", extract={"dish_id": "$.data[0].id"})
    AssertUtil.code_ok(r2.json(), 1, "按分类查询菜品")
    dish_id = user_client.ctx.get("dish_id")
    AssertUtil.not_empty(dish_id, "菜品 id 应提取成功")

    # 渲染是否真的生效？菜品必须属于上一步提取出来的那个分类。
    # 这条断言是"串联成功"的证据：渲染错了这里就会红。
    AssertUtil.equals(r2.json()["data"][0]["categoryId"], category_id,
                      "查到的菜品应属于上一步提取的分类")

    # 提取出来的值要保持原始类型，不能变成字符串
    AssertUtil.equals(type(dish_id), int, "dish_id 应保持 int 类型（渲染时不能转成 str）")

    # ③ 加购物车 → 查回来验证
    r3 = add_to_cart(user_client, "${dish_id}")
    AssertUtil.code_ok(r3.json(), 1, "加入购物车")

    r4 = list_cart(user_client)
    cart = r4.json()
    AssertUtil.code_ok(cart, 1, "查询购物车")
    dish_ids_in_cart = [item["dishId"] for item in cart["data"]]
    AssertUtil.contains(str(dish_ids_in_cart), str(dish_id),
                        f"购物车应包含刚加入的菜品 {dish_id}")


@allure.feature("接口串联")
@allure.story("分类 → 菜品 → 购物车")
@allure.title("串联 + DB 双层校验：加购物车后查 shopping_cart 表确认落库")
def test_cart_add_written_to_db(user_client, empty_cart, db):
    """接口串联和 DB 校验结合：链路跑完，落库结果也要对得上。"""
    list_category(user_client, extract={"category_id": "$.data[0].id"})
    list_dish(user_client, "${category_id}", extract={"dish_id": "$.data[0].id"})
    dish_id = user_client.ctx.get("dish_id")
    add_to_cart(user_client, "${dish_id}")

    row = db.query_one(
        "SELECT id, dish_id, number, dish_flavor FROM shopping_cart "
        "WHERE user_id=4 AND dish_id=%s",
        (dish_id,),
    )
    assert row is not None, f"购物车未落库：user_id=4, dish_id={dish_id}"

    AssertUtil.equals(row["dish_id"], dish_id, "落库的 dish_id 应与请求一致")
    AssertUtil.equals(row["number"], 1, "首次加入数量应为 1")


@allure.feature("接口串联")
@allure.story("上下文隔离")
@allure.title("每个用例开始时变量池必须是空的")
def test_context_is_empty_at_start(user_client):
    """把「防用例间串味」这个设计固化成用例，防止以后被人改坏。

    如果哪天 _fresh_context 这个 autouse fixture 被删了，
    这条用例会立刻变红，而不是等到某个串联用例出现莫名其妙的假绿。
    """
    AssertUtil.equals(user_client.ctx.as_dict(), {}, "用例开始时变量池应为空")
