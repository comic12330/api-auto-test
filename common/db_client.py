# -*- coding: utf-8 -*-
"""db_client.py —— 数据库访问封装（双层校验的数据源）。

为什么需要一个 db_client 而不是在用例里直接 pymysql.connect：
1. 连接复用：每用例新建连接开销大（TCP+MySQL认证），且异常时 conn.close() 可能不执行导致连接泄漏。
2. with 语句自动关闭：无论断言成功还是抛异常，退出 with 块都关闭连接，杜绝泄漏。
3. 返回可断言形态：查询结果统一转成 list[dict]，key 是列名，方便用例里比对字段。
4. 环境隔离：数据库连不上时给出清晰报错（可被 fixture 捕获转 skip），不污染业务失败。

⚠️ autocommit=True 是刻意开的，原因见 __init__ 里的注释（写后落库校验依赖它）。

用法：
    with DBClient() as db:
        rows = db.query("SELECT name, price FROM dish WHERE category_id=%s", (11,))
        # rows 形如 [{"name": "王老吉", "price": 6.00}, ...]

        db.execute("DELETE FROM employee WHERE id=%s", (86,))   # 写操作
"""
import pymysql

from common.yaml_util import load_config


class DBClient:
    """封装一次数据库会话。用 with 语句进入 / 退出，退出时自动关闭连接。"""

    def __init__(self):
        cfg = load_config()["mysql"]
        # 连不上的错误让它在进入 with 时抛出来，由调用方决定怎么处理
        self.conn = pymysql.connect(
            host=cfg["host"],
            port=cfg["port"],
            user=cfg["user"],
            password=cfg["password"],
            database=cfg["database"],
            charset=cfg.get("charset", "utf8mb4"),
            cursorclass=pymysql.cursors.DictCursor,  # 返回 dict，方便按列名取值
            # ⭐ 关键：必须开自动提交，否则写后落库校验会读到旧快照。
            #
            # 原因（实测踩到）：pymysql 默认 autocommit=False，第一条 SELECT 就隐式
            # 开启事务；MySQL InnoDB 默认隔离级别是 REPEATABLE READ，同一事务内的
            # 普通 SELECT 是快照读 —— 后端应用（另一个连接）刚提交的新行，这里看不见。
            # 表现为：POST 新增返回成功，紧接着 SELECT 却查不到，用例假红。
            #
            # 代价：写操作不可回滚。但黑盒 API 测试本就拿不到后端事务句柄，
            # 测试里的写操作都是"造数 + 清理"，不需要回滚能力，故这个代价可接受。
            autocommit=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()
        return False  # 不吞异常，让 with 块内的错误照常抛出

    def query(self, sql, params=None):
        """执行 SELECT，返回 list[dict]（每行一个 dict，key 为列名）。"""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()

    def query_one(self, sql, params=None):
        """执行 SELECT 取一行；没查到返回 None。"""
        with self.conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()

    def execute(self, sql, params=None):
        """执行写操作（INSERT / UPDATE / DELETE），返回受影响行数。

        因为连接已开 autocommit=True，这里不需要再手动 commit()。
        若哪天改成 autocommit=False，则必须在 execute 末尾补 self.conn.commit()，
        否则 DELETE 只在当前连接内"看起来生效"，换连接看数据还在 ——
        表现为"用例全绿、脏数据越堆越多"。
        """
        with self.conn.cursor() as cur:
            return cur.execute(sql, params)

    def execute(self, sql, params=None):
        """执行写操作（INSERT/UPDATE/DELETE），返回受影响行数。"""
        with self.conn.cursor() as cur:
            n = cur.execute(sql, params)
        self.conn.commit()
        return n
