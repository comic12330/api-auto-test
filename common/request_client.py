import requests

from common.context import TestContext, extract_by_jsonpath
from common.logger import get_logger
from common.report_util import attach_response


class RequestClient:
    """
    统一请求封装，管理base_url,headers

    除发请求外，还承担三件事（串联逻辑见 common/context.py）：
      - 渲染：path / params / json / data 里的 ${var} 自动替换成变量池里的值
      - 提取：extract={"变量名": "jsonpath 表达式"} → 从响应里取值存入变量池
      - 证据：每个请求的响应原文自动 attach 进 Allure 报告（见 common/report_util.py）
    """

    def __init__(self, base_url, headers=None):
        self.base_url = base_url
        self.session = requests.Session()
        self.timeout = (3, 10)
        self.logger = get_logger("request")
        # 变量池挂在 client 上：同一个 client 发出的请求共享一套上下文，
        # 这样"上一步提取的值"才能在"下一步请求"里用 ${} 引用。
        self.ctx = TestContext()
        if headers:
            self.session.headers.update(headers)

    def request(self, method, path, extract=None, **kwargs):
        """
        发请求：path 自动拼 base_url

        :param extract: {"变量名": "jsonpath 表达式"}，从响应 JSON 里提取值存入变量池。
                        例：extract={"dish_id": "$.data[0].id"}
        """
        # 渲染 ${var}：让上一步提取的值能直接写进这一步的请求里
        path = self.ctx.render(path)
        for key in ("params", "json", "data"):
            if key in kwargs and kwargs[key] is not None:
                kwargs[key] = self.ctx.render(kwargs[key])

        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        kwargs.setdefault("timeout", self.timeout)
        self.logger.info(f"【发送请求】：{method}，{path}")
        resp = self.session.request(method, url, **kwargs)
        self.logger.info(f"【接收响应】HTTP {resp.status_code} | 耗时 {resp.elapsed.total_seconds():.2f}s")

        # 报文证据在这里统一下发，不靠用例"记得写"。
        # 之前 attach_response 只在 4/7 个用例文件里被手动调用，最需要证据的
        # 下单链路反而没有 —— 能力只接了一半。放到请求出口就 100% 覆盖。
        attach_response(resp, name=f"{method} {path}")

        if extract:
            self._extract(resp, extract)
        return resp

    def _extract(self, resp, extract):
        """按 extract 配置从响应里取值存进变量池。

        注意：这里对非 JSON 响应做了显式判断。不判断的话 resp.json() 会抛
        JSONDecodeError，报错信息只是一堆 HTML（比如 502 页面），
        你根本看不出是"接口挂了"还是"提取表达式写错了"。
        """
        try:
            body = resp.json()
        except Exception as e:
            raise AssertionError(
                f"提取变量失败：响应不是合法 JSON，无法提取 {list(extract)}。"
                f"HTTP {resp.status_code}，响应前 200 字符={resp.text[:200]!r}"
            ) from e

        for name, expr in extract.items():
            value = extract_by_jsonpath(body, expr)
            self.ctx.set(name, value)
            self.logger.info(f"【提取变量】{name} = {value!r}  （表达式 {expr}）")
