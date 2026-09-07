import pytest

from common.token_util import gen_user_token
from common.yaml_util import load_config
from common.request_client import RequestClient
from common.db_client import DBClient
from api.login_api import login


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
