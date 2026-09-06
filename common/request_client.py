import requests
from common.logger import get_logger


class RequestClient:
    """
    统一请求封装，管理base_url,headers
    """

    def __init__(self, base_url, headers=None):
        self.base_url = base_url
        self.session = requests.Session()
        self.timeout = (3, 10)
        self.logger = get_logger("request")
        if headers:
            self.session.headers.update(headers)

    def request(self, method, path, **kwargs):
        """
        发请求：path 自动拼 base_url
        """
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        kwargs.setdefault("timeout", self.timeout)
        self.logger.info(f"【发送请求】：{method}，{path }")
        resp = self.session.request(method, url, **kwargs)
        self.logger.info(f"【接收响应】HTTP {resp.status_code} | 耗时 {resp.elapsed.total_seconds():.2f}s")
        return resp
