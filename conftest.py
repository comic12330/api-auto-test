import pytest

from common.assert_util import AssertUtil
from common.logger import get_logger
from common.token_util import gen_user_token
from common.yaml_util import load_config
from common.request_client import RequestClient
from common.db_client import DBClient
from api.login_api import login
from api.employee_api import (
    add_employee,
    build_employee_payload,
    delete_employee_by_id,
    select_employee_by_username,
)


@pytest.fixture(scope="session")
def db():
    """数据库会话 fixture（双层校验的数据源）。

    关键设计：探测连接是否可用。若 MySQL 没起 / 配置错，
    直接 pytest.skip —— 这样"DB 不可用"不会伪装成"业务失败"，
    而是在报告里明确标成 skipped，一眼看出是环境问题而非用例问题。
    """
    try:
        with DBClient() as client:
            # 用最廉价的查询验证连接确实可用（也顺便验证当前库存在）
            client.query_one("SELECT 1")
            yield client  # 在这个已确认可用的连接上让用例取数据
    except Exception as e:
        pytest.skip(f"数据库不可用，跳过依赖 DB 的用例：{e}")



@pytest.fixture(scope="session")
def admin_client():
    """管理端 client：整个会话只登录一次，返回带 token 的客户端。

    session 级 → 所有用例共享这一个 client，token 全局复用。
    """
    cnf = load_config()
    base_url = cnf["base_url"]
    admin_auth = cnf["auth"]
    rc = RequestClient(base_url)
    body, token = login(rc, admin_auth["admin_username"], admin_auth["admin_password"])
    rc.session.headers[admin_auth["admin_token_header"]] = token
    return rc


@pytest.fixture(scope="session")
def user_token():
    """
    用户端 JWT（自签，本地替代微信授权）
    """
    return gen_user_token()


@pytest.fixture(scope="session")
def user_client(user_token):
    """
    用户端 client：带 authentication header
    """
    cnf = load_config()
    base_url = cnf["base_url"]
    rc = RequestClient(base_url)
    rc.session.headers[cnf["auth"]["user_token_header"]] = user_token
    return rc


@pytest.fixture
def created_employee(admin_client, db):
    """造一个员工 → 把主键交给用例 → 无论断言成败都精确删除。

    这是「数据隔离策略④：造删对称」的落地。yield 把一段函数劈成两半：
      - yield 之前 = setup：造数据、查主键
      - yield 之后 = teardown：按主键清理
    pytest 保证 teardown 一定执行 —— 即使用例断言失败、甚至抛异常。
    这比 unittest 的 tearDown() 可靠：后者在 setUp() 抛异常时根本不会跑，
    而那恰恰是最需要清理的时刻。

    返回 (emp_id, payload, row)：把落库记录 row 也交给用例，
    省得用例再查一遍库（也保证用例断言的就是 setup 那一刻的数据）。
    """
    payload = build_employee_payload()          # 毫秒时间戳，字段值全局唯一

    body = add_employee(admin_client, payload).json()
    AssertUtil.code_ok(body, 1, "新增员工业务码")

    row = select_employee_by_username(db, payload["username"])
    # 先断一句人话，再去取 row["id"]。
    # 不做这步，下一行会抛 TypeError: 'NoneType' object is not subscriptable
    # —— 报错方向对（确实没落库），但看不出是哪个 username、接口返回了什么。
    assert row is not None, f"新增员工未落库：username={payload['username']}，响应={body}"

    yield row["id"], payload, row

    try:
        delete_employee_by_id(db, row["id"])
    except Exception as e:
        # 清理是辅助动作。它一旦抛异常，pytest 会把用例标成 ERROR，
        # 你看到的就变成"清理失败"而不是"断言失败"——真正的问题被盖住。
        # 清理失败值得告警，不值得判死刑。
        get_logger().warning(f"清理员工失败 id={row['id']}: {e}")
