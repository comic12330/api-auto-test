# -*- coding: utf-8 -*-
"""db_client.py —— 数据库访问封装（双层校验的数据源）。

为什么需要一个 db_client 而不是在用例里直接 pymysql.connect：
1. 连接复用：每用例新建连接开销大（TCP+MySQL认证），且异常时 conn.close() 可能不执行导致连接泄漏。
2. with 语句自动关闭：无论断言成功还是抛异常，退出 with 块都关闭连接，杜绝泄漏。
3. 返回可断言形态：查询结果统一转成 list[dict]，key 是列名，方便用例里比对字段。
4. 环境隔离：数据库连不上时给出清晰报错（可被 fixture 捕获转 skip），不污染业务失败。

用法：
    with DBClient() as db:
        rows = db.query("SELECT name, price FROM dish WHERE category_id=%s", (11,))
        # rows 形如 [{"name": "王老吉", "price": 6.00}, ...]
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
