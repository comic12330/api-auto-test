# -*- coding: utf-8 -*-
"""employee_api.py —— 管理端员工接口封装（新增 / 查库 / 清理）。

为什么要单独封一层：URL 和请求体结构只在这个文件里出现一次。
接口改路径、改字段名时只改这里，用例不动 —— 这就是分层的意义。

同时把"构造数据"和"按主键清理"也收在这里，
让"造数"和"清理"这两个动作在代码里挨着，形成造删对称，
避免哪天只改了造数逻辑、忘了同步清理逻辑。
"""
import itertools
import time
import uuid


# 造数唯一性的两个来源（缺一不可，都被实测验证过）：
#   _RUN_TAG —— 一次测试运行（进程）内固定的随机短标识，隔离【不同的进程 / 机器】。
#   _SEQ     —— 进程内单调自增序号，隔离【同一进程内的多次调用】。
# 为什么不能只靠毫秒时间戳：实测连续调用 100 次只生成出 2 个不同的 username
# —— 同一毫秒内的调用返回值完全相同。而 employee.username 上有唯一索引，
# 撞车就是 DuplicateKeyException，这个失败跟被测业务无关，纯属浪费排查时间。
_RUN_TAG = uuid.uuid4().hex[:6]
_SEQ = itertools.count(1)


def build_employee_payload(id_number=None, ts=None):
    """构造一份字段值全局唯一的新增员工请求体。

    唯一性是数据隔离的前提：employee.username 上有唯一索引，
    两次运行撞车会直接失败，而这个失败**跟被测业务逻辑无关**。

    username = `auto_` + 运行标识 + 自增序号：
      - `auto_` 前缀 → 一眼认出是自动化数据，残留时可安全按标记清理
      - 运行标识     → 隔离并发的进程 / 机器（pytest-xdist、多机 CI）
      - 自增序号     → 隔离同一进程内的多次调用。**真正保证唯一的是它，
                       不是时间戳**（时间戳做不到，见上面的实测）

    :param id_number: 想复用别人的身份证号时传入（用于重复校验用例）
    :param ts: 只用于生成 phone / idNumber 的随机部分，不参与唯一性保证
    """
    ts = ts or int(time.time() * 1000)
    seq = next(_SEQ)
    return {
        "name": f"自动化{_RUN_TAG}_{seq}",
        "username": f"auto_{_RUN_TAG}_{seq}",                            # varchar(32)，唯一索引
        "phone": f"139{seq % 100000000:08d}",                            # varchar(11)
        "sex": "1",                                          # varchar(2)
        "idNumber": id_number or f"31010119900101{ts % 10000:04d}",  # varchar(18)
    }


def add_employee(rc, payload):
    """POST /admin/employee 新增员工，返回响应对象。

    注意：这个接口成功时 `data` 为 null，**不返回新记录的主键**。
    所以调用方必须自己查库拿 id，作为后续清理的锚点。
    """
    return rc.request("POST", "/admin/employee", json=payload)


def list_employee_page(rc, page=1, page_size=10, name=None, **kw):
    """GET /admin/employee/page —— 员工分页查询。

    参数名必须跟后端 `EmployeePageQueryDTO` 字段**逐字一致**（已读源码确认）：
    `name` / `page` / `pageSize`。写成 `page_size` 这类名字，Spring 绑不上
    且**不报错**，只会静默取默认值 —— 表现为"分页参数好像没生效"。

    `name` 为 None 时不带该参数：requests 会跳过值为 None 的 param，
    避免拼出 `name=` 空串，把"不过滤"变成"筛 name 为空"。

    `**kw` 用于透传 `headers` 等参数 —— 越权用例需要"带着错误凭证发这个请求"，
    有它就不必为了一个特例在用例里手写 URL、把分层撕开一个口子。
    """
    params = {"page": page, "pageSize": page_size}
    if name is not None:
        params["name"] = name
    return rc.request("GET", "/admin/employee/page", params=params, **kw)


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


def delete_employee_by_username(db, username):
    """按 username 精确删除（主键拿不到时的兜底锚点）。

    为什么它也是安全的：username 上有唯一索引，`WHERE username=%s`
    是唯一键精确匹配，**最多命中 1 行** —— 不是 LIKE 那种会误伤的模糊条件。
    用在「接口已写库但 select 没查到 id」这种极端场景：宁可多一个兜底，
    也不能让数据留在库里。
    """
    return db.execute("DELETE FROM employee WHERE username=%s", (username,))
