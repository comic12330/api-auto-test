import time

import pytest

from common.assert_util import AssertUtil
from common.logger import get_logger
from common.token_util import gen_user_token
from common.yaml_util import load_config
from common.request_client import RequestClient
from common.db_client import DBClient
from api.login_api import login
from api.shopping_api import (
    add_to_cart,
    clean_cart,
    get_default_address,
    list_category,
    list_dish,
)
from api.order_api import (
    delete_order_by_id,
    submit_order,
)
from api.category_api import (
    add_category,
    build_category_payload,
    delete_category_by_id,
    delete_category_by_name,
    select_category_by_name,
)
from api.employee_api import (
    add_employee,
    build_employee_payload,
    delete_employee_by_id,
    delete_employee_by_username,
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


@pytest.fixture(autouse=True)
def _fresh_context(user_client, admin_client):
    """每个用例开跑前清空变量池（autouse，用例不用显式引用）。

    为什么必须清：client 是 session 级的，变量池挂在 client 上。
    不清的话，用例 A 提取的 category_id 会残留到用例 B ——
    万一 B 的提取失败，它会**静默用上 A 的旧值**，用例照样绿。
    这种"假绿"比直接报错难查十倍，因为它看起来一切正常。
    """
    user_client.ctx.clear()
    admin_client.ctx.clear()
    yield


@pytest.fixture
def empty_cart(user_client):
    """购物车清理：进入时清一次保证基线干净，退出时再清一次不留脏数据。

    为什么**两头都清**（这是跟 created_employee 不一样的地方）：
    created_employee 的数据是自己造的，库里本来没有；
    而购物车是 user 表 id=4 这个**真实用户**的数据，库里可能本来就有东西
    （别的用例残留的、或者手工调试留下的）。
      - 只在 teardown 清 → 断言"购物车里有 1 件"会被存量数据带偏；
      - 只在 setup 清   → 用例自己产生的脏数据会留给下一次运行。
    """
    clean_cart(user_client)
    yield user_client
    try:
        clean_cart(user_client)
    except Exception as e:
        # 同 created_employee：清理失败只告警，别让辅助动作盖掉真正的失败原因
        get_logger().warning(f"清理购物车失败：{e}")


@pytest.fixture
def submitted_order(user_client, db, empty_cart):
    """造一张「待接单」的订单 → 把 order_id 交给用例 → 用 DB 删除收尾。

    这条 fixture 有三个必须解释清楚的设计点（面试官会追问）：

    1. **为什么 teardown 用 DB 删，而不是调接口取消？**
       订单**没有删除接口** —— `cancel` 只是把状态改成 6（已取消），记录还在表里。
       要让用例能重复跑，只能直连 DB 删，而且要连带删 `order_detail`，
       否则留下孤儿明细。删除顺序：先明细后主表（外键约束）。

    2. **为什么用一行 SQL 把状态推进到「待接单」？**
       submit 之后状态是 1（待付款）。1 → 2 要走 `/user/order/payment`，
       而它调真实微信支付，本地必然失败 —— 这是**环境妥协**。
       推到 2 是为了让"起点 == 待接单"的断言成立（本文件的下游用例与
       `test_order_flow` 都以 2 为链路起点），也贴合"商户待接单"的真实业务状态。
       ⚠️ **不是为了过 `confirm` 的校验** —— 实测 `confirm` 根本没有状态校验，
       status=1 也能接单成功（见 README 缺陷⑤）。此处曾按"有硬校验"写过，已修正。
       妥协范围被严格限制在这一行 SQL：之后的接单 / 派送 / 完成全是接口驱动，
       断言也全基于接口 + DB。

    3. **为什么要依赖 empty_cart？**
       submit 会把购物车里**所有**商品转成订单。购物车不干净，
       订单金额和明细数量就不可控，断言根本没法写。
    """
    # ① 取默认地址（下单必填 addressBookId，用默认地址而不是写死 id）
    get_default_address(user_client, extract={"address_id": "$.data.id"})
    address_id = user_client.ctx.get("address_id")
    assert address_id is not None, "未取到默认地址，无法下单"

    # ② 加一个菜品进购物车（串联：分类 → 菜品 → 购物车）
    list_category(user_client, extract={"category_id": "$.data[0].id"})
    list_dish(user_client, "${category_id}", extract={"dish_id": "$.data[0].id"})
    add_to_cart(user_client, "${dish_id}")

    # ③ 提交订单，remark 打自动化标记（万一清理失败，能一眼认出并手工清）
    body = submit_order(user_client, "${address_id}",
                        remark=f"AUTO_TEST_{int(time.time())}").json()
    AssertUtil.code_ok(body, 1, "提交订单")
    order_id = body["data"]["id"]

    # ④ 跳过支付：把状态推进到「待接单」，理由见上面第 2 点
    db.execute("UPDATE orders SET status=2 WHERE id=%s", (order_id,))

    yield order_id

    try:
        delete_order_by_id(db, order_id)
    except Exception as e:
        get_logger().warning(f"清理订单失败 id={order_id}：{e}")


@pytest.fixture
def created_category(admin_client, db):
    """造一个分类 → 把主键交给用例 → 无论断言成败都精确删除。

    结构跟下面的 created_employee 一模一样，是同一套造删对称思路的复用：
      - 用 try/finally 而不是把清理写在 yield 之后：
        pytest 只对「已经执行到 yield」的 fixture 跑 yield 之后的代码，
        setup 段一旦在 yield 之前挂掉，数据已经进库而清理永远不执行。
        try/finally 由 Python 语言保证，异常穿过生成器时也一定执行。
      - 清理锚点主键优先，拿不到就退回唯一键 name（name 有唯一索引，最多命中 1 行）
      - 清理失败只 warning 不抛异常：抛了 pytest 标 ERROR，
        "清理失败"会盖住真正的"断言失败"

    返回 (category_id, payload, row)：row 是查库拿到的整条记录，
    直接交给用例当断言数据源，省得用例再查一遍。
    """
    category_id = None
    payload = None
    try:
        payload = build_category_payload()      # auto_ + 运行标识 + 自增序号，name 全局唯一

        body = add_category(admin_client, payload).json()
        AssertUtil.code_ok(body, 1, "新增分类业务码")

        row = select_category_by_name(db, payload["name"])
        # 同样是先断一句人话再取 row["id"]：
        # 否则报的是 TypeError: 'NoneType' object is not subscriptable，
        # 看不出是哪个 name、接口返回了什么。
        assert row is not None, f"新增分类未落库：name={payload['name']}，响应={body}"

        category_id = row["id"]
        yield category_id, payload, row
    finally:
        try:
            if category_id is not None:                     # 正常路径：按主键删
                delete_category_by_id(db, category_id)
            elif payload is not None:                       # 兜底：id 没拿到就按唯一键删
                delete_category_by_name(db, payload["name"])
        except Exception as e:
            get_logger().warning(f"清理分类失败 id={category_id}: {e}")


@pytest.fixture
def created_employee(admin_client, db):
    """造一个员工 → 把主键交给用例 → 无论断言成败都精确删除。

    这是「数据隔离策略④：造删对称」的落地。yield 把一段函数劈成两半：
      - yield 之前 = setup：造数据、查主键
      - yield 之后 = teardown：按主键清理
    用例无论断言成败还是抛异常，pytest 都会再驱动一次生成器，让 yield 之后的代码跑完。
    这比 unittest 的 tearDown() 可靠：后者在 setUp() 抛异常时根本不会跑，
    而那恰恰是最需要清理的时刻。

    但 yield 有个必须知道的前提（实测过）：
    **pytest 只对「已经执行到 yield」的 fixture 跑 yield 之后的语句。**
    如果 setup 段在 yield 之前就挂了（比如接口成功写库但 select 查不到 id），
    员工已经进库了，而 yield 之后的清理永远不执行 —— 数据残留。
    所以这里用 try/finally 而不是把清理写在 yield 之后：
    finally 由 Python 语言保证，异常穿过生成器时也一定执行。

    返回 (emp_id, payload, row)：把落库记录 row 也交给用例，
    省得用例再查一遍库（也保证用例断言的就是 setup 那一刻的数据）。
    """
    emp_id = None
    payload = None
    try:
        payload = build_employee_payload()      # auto_ + 运行标识 + 自增序号，字段值全局唯一

        body = add_employee(admin_client, payload).json()
        AssertUtil.code_ok(body, 1, "新增员工业务码")

        row = select_employee_by_username(db, payload["username"])
        # 先断一句人话，再去取 row["id"]。
        # 不做这步，下一行会抛 TypeError: 'NoneType' object is not subscriptable
        # —— 报错方向对（确实没落库），但看不出是哪个 username、接口返回了什么。
        assert row is not None, f"新增员工未落库：username={payload['username']}，响应={body}"

        emp_id = row["id"]
        yield emp_id, payload, row
    finally:
        # 用 finally 而不是把清理写在 yield 之后：
        # pytest 只对「已经执行到 yield」的 fixture 跑 yield 之后的语句。
        # 一旦 setup 段在 yield 之前挂掉（上面任意一步都可能），
        # 员工已经写进库了，而清理代码永远不会执行 —— 数据就残留在库里。
        # try/finally 由 Python 语言保证：异常穿过生成器时 finally 一定执行。
        try:
            if emp_id is not None:                      # 正常路径：按主键删
                delete_employee_by_id(db, emp_id)
            elif payload is not None:                   # 兜底：id 没拿到就按唯一键删
                delete_employee_by_username(db, payload["username"])
        except Exception as e:
            # 清理是辅助动作。它一旦抛异常，pytest 会把用例标成 ERROR，
            # 你看到的就变成"清理失败"而不是"断言失败"——真正的问题被盖住。
            # 清理失败值得告警，不值得判死刑。
            get_logger().warning(f"清理员工失败 id={emp_id}: {e}")
