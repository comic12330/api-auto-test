# api-auto-test

基于 **Python + pytest + requests** 的接口自动化测试框架，覆盖登录鉴权、越权安全、入参校验、数据库双层校验、接口串联、下单业务链路等场景。被测系统为本地部署的**食汇本地生活平台**（外卖 / 本地生活类系统，Spring Boot，管理端 / 用户端双端）。

> 本仓库仅包含测试侧代码，不含被测系统的业务源码。

![Python](https://img.shields.io/badge/Python-3.11-blue)
![pytest](https://img.shields.io/badge/pytest-9.1.1-green)
![requests](https://img.shields.io/badge/requests-2.32.3-orange)
![allure](https://img.shields.io/badge/allure-2.13.5-red)

---

## 目录结构

```
api_auto_test/
├── api/                  # 接口定义层：只描述"接口长什么样"，不含断言
│   ├── login_api.py      #   管理端登录（用户端不走登录接口，见 token_util.py）
│   ├── employee_api.py   #   员工新增 / 分页查询 / 查库 / 清理
│   ├── category_api.py   #   分类增删改查 + 启停用 + 清理
│   ├── shopping_api.py   #   分类 / 菜品 / 购物车 / 收货地址
│   └── order_api.py      #   用户端下单 + 管理端履约
├── common/               # 通用能力层
│   ├── request_client.py #   requests.Session 封装：URL 拼接 / 超时 / 日志 / 变量渲染 / 报文证据
│   ├── context.py        #   用例间变量池：jsonpath 提取 + ${} 渲染
│   ├── assert_util.py    #   断言工具：equals / code_ok / contains / match ...
│   ├── token_util.py     #   用户端 JWT 自签
│   ├── yaml_util.py      #   yaml 读取（已处理 Windows 编码）
│   ├── db_client.py      #   数据库访问封装（with 语句管理连接，防泄漏）
│   ├── report_util.py    #   Allure 响应体附件（由 request_client 统一调用）
│   └── logger.py
├── data/                 # 数据层：测试数据外置
│   ├── login_cases.yaml
│   └── dish_cases.yaml
├── testcase/             # 用例层：只写业务语义
│   ├── test_login.py     #   登录鉴权 + 数据驱动
│   ├── test_overage.py   #   越权安全 + 入参校验
│   ├── test_dish_db.py   #   DB 双层校验（接口响应 vs 数据库对账）
│   ├── test_employee_db.py
│   ├── test_cart_chain.py  # 接口串联（分类 → 菜品 → 购物车）
│   ├── test_order_flow.py  # 下单业务链路（跨端 token）
│   └── test_category.py    # 分类管理 + 分页 / 修改 / 启停用 / 删除业务规则
├── conftest.py           # fixture：admin_client / user_client / db / created_* / submitted_order
├── config.example.yaml   # 配置模板（脱敏，入库）
├── config.yaml           # 真实配置（含密钥，不入库）
└── pytest.ini
```

**分层的目的**：接口改路径、改参数，只动 `api/` 一层；加用例场景，只动 `data/`；断言规则变了，只动 `common/assert_util.py`。用例文件本身尽量不改。

---

## 快速开始

```bash
# 1. 建虚拟环境并装依赖
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 生成真实配置
cp config.example.yaml config.yaml     # 然后填自己的 base_url / 账号 / JWT 密钥

# 3. 启动被测后端（默认 http://localhost:8080），MySQL 与 Redis 需先起来

# 4. 跑测试
.venv\Scripts\python.exe -m pytest
```

Allure 报告（需要 Java 8+ 和 allure 命令行工具）：

```bash
.venv\Scripts\python.exe -m pytest --alluredir=allure-results --clean-alluredir
allure generate allure-results -o allure-report --clean
allure open allure-report -p 8081
```

> ⚠️ 报告必须走 `allure open` 起的 http 服务打开。直接双击 `index.html` 会白屏 —— 报告用 fetch 加载 JSON，`file://` 协议下被浏览器拦截。

---

## 设计要点

**1. 凭证全局复用**
`conftest.py` 中 `scope="session"` 的 fixture 让整个测试会话只登录一次，token 注入 `Session.headers` 后所有请求自动携带，无需在每个用例里重复获取。

**2. 用户端 token 自签（本项目最特殊的一点）**
用户端走微信小程序登录，本地无法复现真实授权流程。方案是**按后端拦截器的验签规则自签 JWT**：

| 端 | 密钥 | Header | Claims |
|---|---|---|---|
| 管理端 | 后端 `jwt.admin-secret-key` | `token` | 登录接口返回 |
| 用户端 | 后端 `jwt.user-secret-key` | `authentication` | `{userId: 4}` |

自签能成立的前提：用户端拦截器**只验签、不查 session** —— 从 header 取 token、用固定密钥验签、取出 `userId` 放入上下文即可，不依赖任何服务端会话状态。

**3. 断言分层（L1–L5）**
L1 HTTP 状态码 → L2 业务码 → L3 结构（字段是否存在）→ L4 字段值 → L5 动态规则（正则 / 格式校验）。
例如正向登录：断 200 + `code==1` + `data` 含 `token` 字段 + token 非空 + JWT 按 `.` 切分是 3 段。

**4. 数据驱动**
测试数据放在 `data/login_cases.yaml`，`build_login_cases()` 在收集阶段把 yaml 翻译成 `pytest.param` 列表。**是否挂 xfail 由数据里的 `xfail: true` 决定**，而不是写死在代码里。

**5. 用 xfail 做缺陷回归门禁**
已知缺陷不删用例，而是挂 `@pytest.mark.xfail(strict=True)`，断言里写**正确的期望值**：

| 阶段 | 用例状态 | 流水线 |
|---|---|---|
| 发现缺陷 | failed | 红 |
| 标记 xfail | xfailed | 绿 |
| 开发修复 | XPASS → FAILED | **红（提醒清理标记）** |
| 删掉标记 | passed | 绿 |

`xfail_strict = true` 配在 `pytest.ini`，保证 XPASS 一定报错。

**6. DB 双层校验（对账）**
接口断言只听后端自报成绩。`test_dish_db.py` 再直查数据库，比对"接口返回的菜品 id 集合"与"DB 查出的同分类、在售菜品 id 集合"是否一致——数量对、id 集合对，才算接口真的诚实。
用 `with DBClient() as db:` 管理连接（防泄漏）；MySQL 连不上时 `db` fixture 直接 `pytest.skip`，不把环境问题伪装成业务失败刷红。

**7. 写后落库校验 + 造删对称的数据隔离**

读对账验证"接口诚实"，写后落库验证"接口没骗人"——`POST /admin/employee` 返回 `code=1` 不等于数据真的进库了，必须直查 `employee` 表确认。断言三层：字段一致（`username` / `id_number`）→ 业务默认值（`status=1`）→ 安全维度（密码是 MD5 密文而非明文）。

写操作必然污染数据库，因此采用**唯一标记 + 造删对称**：

- 造数用 `auto_` + 运行标识（uuid 短码）+ 进程内自增序号构造全局唯一字段值。不用时间戳做唯一性来源——同一毫秒内的多次调用会得到相同结果，撞上唯一索引后的失败原因会与被测业务混淆；
- `created_employee` 等 fixture 采用 **yield 两段式**：`yield` 前造数并查库拿主键，`yield` 后清理，用例拿到的主键同时作为断言数据源；
- 清理写在 **`try/finally`** 里，而不是直接写在 `yield` 之后。pytest 只对**已经执行到 `yield`** 的 fixture 运行收尾代码，一旦 setup 段在 `yield` 之前失败（例如写库成功但查主键失败），数据已经进库而清理永不执行；
- 清理**只按主键**，不用 `WHERE username LIKE 'auto_%'` 这类模糊条件——条件越宽误伤面越大，清理动作同样要遵守最小影响面；
- 清理失败只记 `logger.warning` 不抛异常——否则用例被标成 ERROR，"清理失败"会盖住真正的"断言失败"。

`DBClient` 连接显式开启 `autocommit`：`pymysql` 默认 `autocommit=False`，首条 SELECT 就会隐式开启事务；InnoDB 默认 `REPEATABLE READ` 下同一事务内是快照读，读不到其他连接（后端应用）刚提交的新行，表现为"接口返回成功、紧接着查库却查不到"。代价是写操作不可回滚，但黑盒 API 测试本就拿不到后端事务句柄，可接受。

**8. 接口串联：jsonpath 提取 + 上下文变量池 + `${}` 渲染**

接口之间存在依赖：查菜品要用"查分类"返回的 `categoryId`，加购物车要用"查菜品"返回的 `dishId`。如果每个用例都手写 `resp.json()["data"][0]["id"]`，一来重复，二来响应结构一变要改 N 处，三来**没法写进 YAML**（数据驱动就废了）。

所以拆成三件事（见 `common/context.py`）：

```python
# 提取：用 jsonpath 表达式取值，存进变量池
list_category(user_client, extract={"category_id": "$.data[0].id"})

# 渲染：请求里的 ${var} 发请求前自动替换成真实值
list_dish(user_client, "${category_id}", extract={"dish_id": "$.data[0].id"})
add_to_cart(user_client, "${dish_id}")
```

- 提取失败报可读错误（带表达式 + 响应片段），不是 `list index out of range`
- `${var}` 支持嵌套结构（dict / list 递归替换）。整个字符串就是一个变量时**保留原类型**——`${dish_id}` 渲染成 `int 66` 而不是 `"66"`，否则后端反序列化可能失败
- 变量取不到时**原样返回** `${not_exist}`，不静默替换成 `None`——让错误在接口层暴露出来，而不是变成一次"查不到数据"的假绿
- 每个用例开跑前清空变量池（`_fresh_context` autouse fixture）。client 是 session 级的，不清的话用例 A 的 `category_id` 会残留到用例 B，B 提取失败时会**静默用上 A 的旧值**，这种假绿极难排查；该守卫本身也固化成了一条用例

**9. 下单业务链路：跨端 token 切换 + 多表联动**

用户端下单 → 管理端履约（接单 → 派送 → 完成），状态流转 **2 待接单 → 3 已接单 → 4 派送中 → 5 已完成**。
每一步都做接口 + DB 双层断言：`code=1` 只说明"接口没报错"，状态推进到哪一步只有查库才知道。

三个关键工程决策：

- **用 DB 把状态推进到「待接单」**：`submit` 之后订单是 1（待付款），而 `confirm` 在后端有硬校验——**status 必须 = 2 才给接单**。1 → 2 要走 `/user/order/payment`，而它调用真实微信支付，本地必然失败。这是环境妥协而非设计，且被严格限制在一行 SQL 之内，其后的接单 / 派送 / 完成全部由接口驱动；
- **teardown 用 DB 删而非接口取消**：订单**没有删除接口**，`cancel` 只是把状态改成 6，记录还在。要可重复执行只能直连 DB 删，且**必须先删 `order_detail` 再删 `orders`**（外键约束，顺序反了直接报错）；
- **依赖 `empty_cart`**：`submit` 会把购物车里的所有商品转成订单，购物车不干净则金额与明细数量不可控。

**10. 分层收口：请求出口唯一，证据自动落地**

分层不是文档里的口号，而是可以被机械验证的约束：

- **测试层不出现任何裸 URL、不直接调用 `rc.request()`**。所有请求经 `api/` 层函数发出，接口改路径只动一处。越权用例需要"带错误凭证发同一个请求"这类特例，也通过 api 函数的 `**kw` 透传 `headers` 解决，不为一个特例把分层撕开一个口子；
- **响应报文附件不靠用例手写**。早期 `attach_response()` 由用例自己记得调用，结果只覆盖 4/7 个用例文件——恰恰最需要证据的下单链路没有留痕。现在统一下发在 `RequestClient.request()` 的出口，覆盖率天然 100%，用例也不必再关心报告怎么留痕。

---

## 用例清单（29 条）

当前状态：**23 passed + 6 xfailed，零 failed**。6 条 `xfail` 对应 6 个已知缺陷的回归门禁——缺陷修复后用例自动 XPASS，`xfail_strict = true` 会让流水线变红，提醒清理标记转回普通用例。

| 模块 | 用例 | 说明 | 结果 |
|---|---|---|---|
| 登录鉴权 | `test_login_success` | 正确账号密码，校验 JWT 三段结构 | passed |
| 登录鉴权 | `test_login_invalid_credential` × 4 | 密码错误 / 密码为空 / 账号不存在 / 空用户名 | 3 passed + **1 xfailed** |
| 登录鉴权 | `test_employeeList_success` | 带 token 查员工列表 | passed |
| 越权安全 | `test_user_token_cannot_access_admin` | 用户端 token 调管理端接口 | passed（401） |
| 越权安全 | `test_admin_token_can_access_admin` | 管理端 token 调自己的接口 | passed（200） |
| 越权安全 | `test_user_token_can_access_user` | 用户端 token 调用户端接口 | passed（200） |
| 入参校验 | `test_dish_list_missing_categoryId_should_be_400` | 缺必填参数 | **xfailed** |
| DB 双层校验 | `test_dish_list_matches_db` × 2 | 分类 11/12 菜品：接口返回 id 集合 vs 数据库对账 | passed |
| DB 写后落库 | `test_employee_created_in_db` | 新增员工后直查库：字段一致 + status=1 + 密码 MD5 落库 | passed |
| 数据完整性 | `test_id_number_duplicate_should_be_rejected` | 相同身份证号再次新增应被拒绝 | **xfailed** |
| 接口串联 | `test_cart_add_by_chain` | 分类 → 菜品 → 购物车三步串联，每步输入来自上一步输出 | passed |
| 接口串联 | `test_cart_add_written_to_db` | 串联 + DB 双层校验：加购物车后查 `shopping_cart` 表 | passed |
| 接口串联 | `test_context_is_empty_at_start` | 每个用例开始时变量池必须为空（防用例间串味的守卫用例） | passed |
| 下单链路 | `test_order_full_lifecycle` | 跨端履约：用户下单 → 接单 → 派送 → 完成，每步接口 + 查库对账；收尾逐字段核对用户端详情与库一致 | passed |
| 下单链路 | `test_order_submit_written_to_db` | 多表联动：`orders` + `order_detail` 落库，购物车被清空 | passed |
| 下单链路 | `test_order_cancel_by_user` | 逆向流程：用户端取消，状态转已取消(6) | passed |
| 状态机 | `test_confirm_should_reject_invalid_status` | 接单应校验状态：已取消(6) 的订单不应被重新接单 | **xfailed** |
| 越权安全 | `test_order_detail_should_reject_other_user` | 订单详情校验数据归属：另一用户 token 读他人订单应被拒绝 | **xfailed** |
| 分类管理 | `test_category_created_in_db` | 新增分类后直查库：字段一致 + 默认 `status=0`（禁用） | passed |
| 分类管理 | `test_delete_related_category_should_be_rejected` × 2 | 分类下挂菜品(11) / 套餐(13) 时删除被拒绝，且库里数据不能少 | passed |
| 分类管理 | `test_category_page_filter_and_paging` | 分页：`name` 过滤真的在过滤 + `pageSize` 真的在切页 + `total` 不随 pageSize 变化 | passed |
| 分类管理 | `test_category_page_no_duplicate_or_missing` | 分页不变量：翻完所有页拼起来不重不漏，且与 DB 全量一致 | **xfailed** |
| 分类管理 | `test_edit_category_only_updates_given_fields` | 只改 `name` 时 `type` / `sort` / `status` 不被连带清空（部分更新契约） | passed |
| 分类管理 | `test_category_status_toggle_affects_user_visibility` | 启停用只改 `status`；启用后在用户端列表可见、禁用后消失 | passed |

---

## 缺陷检出

框架在联调过程中检出以下真实缺陷。前 6 条已用 `xfail` 用例固化为回归门禁，后 3 条待补门禁：

| 接口 | 问题 | 类型 | 门禁 |
|---|---|---|---|
| `/admin/employee/login` | 空用户名 + 默认密码可登录管理后台 | 鉴权绕过 | xfail |
| `/user/dish/list` | 缺失必填参数 `categoryId` 时返回 500，应返回 400 | 入参校验缺失 | xfail |
| `/admin/employee` | `id_number` 无唯一约束与格式校验，可重复落库 | 数据完整性 | xfail |
| `/admin/category/page` | 分类 `sort` 值相同时排序不固定，翻页会重复返回同一条记录、并漏掉另一条 | 分页不稳定 | xfail |
| `/admin/order/confirm` | 接单接口无任何状态校验：已取消 / 已完成 / 甚至不存在的订单都能被"接单"成已接单(3)；`status` 字段为死参数 | 状态机校验缺失 | xfail |
| `/user/order/orderDetail/{id}` | 订单详情不校验归属，任意用户 token 可读任意订单（`historyOrders` 有 `userId` 过滤，详情接口没有） | 越权访问 | xfail |
| `/user/order/cancel/{id}` | 订单 id 不存在时返回 500（`getById` 返回 null 后直接取 `getStatus()`），应返回 404 / 业务错误码 | 空值处理缺失 | 待补 |
| `/admin/order/cancel` | 管理端取消同样无状态校验：已完成(5) / 已取消(6) / 不存在的订单都能被改成已取消(6)。与 `/admin/order/confirm` 属同一类缺失——该系统订单状态机仅 `delivery` / `complete` / `rejection` 三个动作有校验 | 状态机校验缺失 | 待补 |
| `order_detail` 表结构 | `order_id` 无外键约束，订单删除后明细可残留（实测孤儿明细 2878 条），数据库层无任何保护 | 数据完整性 | 待补 |

这批用例同时是"发现过缺陷"的可展示证据：开发修复后用例转为 `XPASS`，`strict=True` 会让流水线变红，提醒清理标记。

---

## 常用命令

```bash
# 只跑某条用例
.venv\Scripts\python.exe -m pytest -k "empty-username" -v

# 只看收集结果，不执行（改参数化 id 时很好用）
.venv\Scripts\python.exe -m pytest --collect-only -q

# 失败重试（需装 pytest-rerunfailures）
.venv\Scripts\python.exe -m pytest --reruns 2
```
