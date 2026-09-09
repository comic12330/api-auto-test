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
        "name": name or f"auto_{_RUN_TAG}_{seq}",   # varchar(32)，唯一索引
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
