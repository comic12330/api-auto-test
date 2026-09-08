# -*- coding: utf-8 -*-
"""shopping_api.py —— 用户端「点单前置链路」接口封装。

覆盖：查分类 → 查菜品 → 加购物车 → 查购物车 → 清空购物车。
这条链路是下单业务链路（P1-10）的前置：**下单就是从购物车 submit**。

分层约定
--------
URL 和请求体结构只在这个文件里出现一次。

至于"从响应里提取哪个字段"，**由用例决定**并通过 `extract=` 传入，
api 层不替用例做这个决定 —— 否则换个场景就要回来改 api 层，
分层就白做了。所以这些函数都留了 `**kw` 把 extract 等参数透传下去。
"""


def get_default_address(rc, **kw):
    """GET /user/addressBook/default 取默认收货地址。

    下单必填 `addressBookId`，所以这一步是下单链路的第一环。
    用默认地址而不是写死 id：写死的话换环境就废了。
    """
    return rc.request("GET", "/user/addressBook/default", **kw)


def list_category(rc, category_type=1, **kw):
    """GET /user/category/list 查询分类列表。

    :param category_type: 1=菜品分类，2=套餐分类
    """
    return rc.request("GET", "/user/category/list",
                      params={"type": category_type}, **kw)


def list_dish(rc, category_id, **kw):
    """GET /user/dish/list 按分类查询起售中的菜品。

    category_id 可以直接传值，也可以传 "${category_id}" 让框架从上下文渲染。
    """
    return rc.request("GET", "/user/dish/list",
                      params={"categoryId": category_id}, **kw)


def add_to_cart(rc, dish_id, dish_flavor='["不辣"]', **kw):
    """POST /user/shoppingCart/add 加入购物车。

    ⚠️ dishFlavor 必须是 **JSON 字符串**而不是 Python 列表 —— 后端 DTO 是
    `private String dishFlavor`。写成 ["不辣"] 会被 json 序列化成数组，
    后端反序列化直接失败。这个坑查起来很浪费时间。
    """
    return rc.request("POST", "/user/shoppingCart/add", json={
        "dishId": dish_id,
        "setmealId": None,
        "dishFlavor": dish_flavor,
    }, **kw)


def list_cart(rc, **kw):
    """GET /user/shoppingCart/list 查询购物车。"""
    return rc.request("GET", "/user/shoppingCart/list", **kw)


def clean_cart(rc, **kw):
    """DELETE /user/shoppingCart/clean 清空当前用户的购物车。"""
    return rc.request("DELETE", "/user/shoppingCart/clean", **kw)
