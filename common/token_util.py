# token_util.py —— 用户端凭证生成（本地替代微信授权）
import time
import jwt
from common.yaml_util import load_config


def gen_user_token(user_id=None):
    """生成用户端 JWT。

    user_id: 不传则用 config 里的默认值(4)
    """
    auth = load_config()["auth"]
    claims = dict(auth["user_claims"])
    if user_id:
        claims["userId"] = user_id
    claims["exp"] = int(time.time()) + auth["user_secret_ttl_ms"] // 1000
    return jwt.encode(claims, auth["user_secret_key"], algorithm=auth["sign_algorithm"])
