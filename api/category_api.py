# -*- coding: utf-8 -*-
"""category_api.py —— 管理端分类接口封装（新增 / 查库 / 清理）。

结构跟 employee_api.py 完全同构：URL 和请求体只在这个文件里出现一次，
接口改路径或改字段名时只改这里，用例不动。

分类比员工多一个**业务规则考点**：
    CategoryServiceImpl.delete() 会先查这个分类下有没有挂菜品 / 套餐，
    有就抛 DeletionNotAllowedException，接口返回
    {"code":0, "msg":"当前分类关联了菜品,不能删除"}。
所以删除必须分两条用例写：空分类能删、被关联的不能删。
"""
import itertools
import uuid

# 造数唯一性（跟 employee 同一个套路，原因相同）：
#   _RUN_TAG —— 隔离不同进程 / 机器
#   _SEQ     —— 隔离同一进程内的多次调用。真正保证唯一的是它，不是时间戳
# 为什么必须唯一：category.name 上有唯一索引 idx_category_name（已实测确认），
# 撞车导致的失败跟被测业务无关。
_RUN_TAG = uuid.uuid4().hex[:6]
_SEQ = itertools.count(1)


def build_category_payload(name=None, category_type=1, sort=None):
    """构造一份 name 全局唯一的新增分类请求体。

    注意 name 字段是 **varchar(32)**，所以前缀必须短，
    `auto_` + 6 位运行标识 + 序号，长度安全。

    :param name: 想指定分类名时传入（如测"重名"场景）
    :param category_type: 1=菜品分类 2=套餐分类
    :param sort: 排序值，不传就用自增序号
    """
    seq = next(_SEQ)
    return {
        "name": name or f"auto_{_RUN_TAG}_{seq}",  # varchar(32)，唯一索引
        "type": category_type,
        "sort": sort if sort is not None else seq,
    }


def add_category(rc, payload):
    """POST /admin/category 新增分类，返回响应对象。

    跟新增员工一样：成功时 `data` 为 null，**不返回新记录的主键**，
    所以调用方必须自己查库拿 id，作为后续清理的锚点。
    """
    return rc.request("POST", "/admin/category", json=payload)


def select_category_by_name(db, name):
    """按 name 查一条分类记录；没查到返回 None。

    它同时服务两个目的（跟 select_employee_by_username 一样）：
      ① 拿清理锚点 id
      ② 拿到的 row 直接 yield 给用例当断言数据源，省得用例再查一遍
    """
    return db.query_one(
        "SELECT id, type, name, sort, status FROM category WHERE name=%s",
        (name,),
    )


def delete_category(rc, category_id):
    """DELETE /admin/category?id=xx —— **走接口**删除分类。

    注意跟下面两个函数的区别：
      - 这个走 HTTP 接口，用于**测业务规则**（比如被关联时应该被拒绝）
      - delete_category_by_id / by_name 直接操作数据库，只用于**清理**，
        绝不拿来做断言，否则等于绕过被测代码，测了个寂寞
    """
    return rc.request("DELETE", "/admin/category", params={"id": category_id})


def delete_category_by_id(db, category_id):
    """按主键精确删除一条分类（**清理用，直接操作库**，不走接口）。

    只认主键，绝不用 LIKE：条件越宽误伤面越大。
    """
    return db.execute("DELETE FROM category WHERE id=%s", (category_id,))


def delete_category_by_name(db, name):
    """按 name 精确删除（主键拿不到时的兜底锚点）。

    安全的理由：name 上有唯一索引，`WHERE name=%s` 是唯一键精确匹配，
    **最多命中 1 行**，不是会误伤的模糊条件。
    """
    return db.execute("DELETE FROM category WHERE name=%s", (name,))


def edit_category_by_id(rc, payload):
    """PUT /admin/category —— **走接口**修改分类。

    body 对应后端 CategoryDTO：`id` / `name` / `type` / `sort`，
    四个字段都可选，但**没有 id 就不知道该改谁**。

    两个来自源码的注意点（CategoryServiceImpl.edit，已读代码确认）：
      - 方法名是 `edit()` 不是 `update()`
      - Mapper 的 `<update>` 用 `<set>` + `<if test="x != null">` 动态 SQL，
        即**只更新传了的字段**，没传的保持原值、不会被置 null。
        由此多出一个高价值断言：**只改 name 时 type/sort 应保持不变**，
        可用来验证部分更新没有误清空其他字段。
    """
    return rc.request("PUT", "/admin/category", json=payload)


def set_category_status(rc, category_id, status):
    """POST /admin/category/status/{status}?id=xx —— 启用(1) / 禁用(0) 分类。

    两个必须知道的地方（均来自 Controller 源码，别凭直觉写）：

    1. **`id` 是查询参数，不是路径参数。** 方法签名是
       `startOrStop(@PathVariable Integer status, Long id)` —— 只有 status 带
       `@PathVariable`，`id` 裸着没有任何注解。Spring 对无注解的简单类型参数
       默认按**请求参数**绑定，所以只能写成 `?id=xx`；
       写成 `/status/{status}/{id}` 会 404。

    2. **它和「修改分类」共用同一个 Mapper 方法** `categoryMapper.update()`，
       而那条 SQL 是 `<set>` + `<if test="x != null">` 的动态更新。
       这里只 set 了 status 和 id → **只会更新 status 一列**，
       name / type / sort 不受影响。这正好是一条值得断言的安全边界。

    :param status: 1=启用，0=禁用（StatusConstant）
    """
    return rc.request("POST", f"/admin/category/status/{status}",
                      params={"id": category_id})


def get_category_page(rc, page, page_size, name=None, category_type=None):
    """GET /admin/category/page —— 分页查询分类，返回响应对象。

    ⚠️ 参数名必须跟后端 DTO 字段**逐字一致**（CategoryPageQueryDTO）：
    分页大小叫 `pageSize`，不是 `page_size`。写错 Spring 绑定不上，
    也**不会报错**，只会静默取默认值 —— 表现为"分页参数好像没生效"。

    `name` / `type` 是可选筛选条件，为 None 时不带这个参数
    （requests 会跳过值为 None 的 param），避免拼出 `name=` 空串，
    把"不过滤"变成"筛 name 为空"。

    :param category_type: 1=菜品分类 2=套餐分类；不用 `type` 做参数名，
        是为了不遮蔽 Python 内置的 type()
    """
    params = {"page": page, "pageSize": page_size}
    if name is not None:
        params["name"] = name
    if category_type is not None:
        params["type"] = category_type
    return rc.request("GET", "/admin/category/page", params=params)

