# -*- coding: utf-8 -*-
"""employee_api.py —— 管理端员工接口封装（新增 / 查库 / 清理）。

为什么要单独封一层：URL 和请求体结构只在这个文件里出现一次。
接口改路径、改字段名时只改这里，用例不动 —— 这就是分层的意义。

同时把"构造数据"和"按主键清理"也收在这里，
让"造数"和"清理"这两个动作在代码里挨着，形成造删对称，
避免哪天只改了造数逻辑、忘了同步清理逻辑。
"""
import time


def build_employee_payload(id_number=None, ts=None):
    """构造一份字段值全局唯一的新增员工请求体。

    唯一性是数据隔离的前提：employee.username 上有唯一索引，
    两次运行撞车会直接失败，而这个失败**跟被测业务逻辑无关**。
    用毫秒时间戳 + 固定前缀，保证每次运行都不重复。

    :param id_number: 想复用别人的身份证号时传入（用于重复校验用例）
    :param ts: 时间戳种子，一般不用传
    """
    ts = ts or int(time.time() * 1000)
    return {
        "name": f"自动化{ts}",
        "username": f"auto_{ts}",                            # varchar(32)，唯一索引
        "phone": f"139{ts % 100000000:08d}",                 # varchar(11)
        "sex": "1",                                          # varchar(2)
        "idNumber": id_number or f"31010119900101{ts % 10000:04d}",  # varchar(18)
    }


def add_employee(rc, payload):
    """POST /admin/employee 新增员工，返回响应对象。

    注意：这个接口成功时 `data` 为 null，**不返回新记录的主键**。
    所以调用方必须自己查库拿 id，作为后续清理的锚点。
    """
    return rc.request("POST", "/admin/employee", json=payload)


def select_employee_by_username(db, username):
    """按 username 查一条员工记录；没查到返回 None。"""
    return db.query_one(
        "SELECT id, username, password, status, id_number FROM employee WHERE username=%s",
        (username,),
    )


def delete_employee_by_id(db, emp_id):
    """按主键精确删除一名员工。

    只认主键，绝不用 `WHERE username LIKE 'auto_%'` 这类模糊条件：
    条件越宽，误伤面越大。清理动作也要遵守最小影响面原则。
    """
    return db.execute("DELETE FROM employee WHERE id=%s", (emp_id,))
