# api-auto-test

基于 **Python + pytest + requests** 的接口自动化测试框架，被测系统为本地部署的**苍穹外卖**（管理端 + 用户端双端，Spring Boot 项目）。

> 说明：苍穹外卖是公开的教程项目，本项目把它当**被测对象**使用，不包含其业务代码。仓库里只有测试侧代码。

![Python](https://img.shields.io/badge/Python-3.11-blue)
![pytest](https://img.shields.io/badge/pytest-9.1.1-green)
![requests](https://img.shields.io/badge/requests-2.32.3-orange)
![allure](https://img.shields.io/badge/allure-2.13.5-red)

当前状态：**14 条用例，11 passed / 3 xfailed**（3 条 xfail 为已确认缺陷，见下方「实测发现的缺陷」）。

---

## 目录结构

```
api_auto_test/
├── api/                  # 接口定义层：只描述"接口长什么样"，不含断言
│   └── login_api.py
├── common/               # 通用能力层
│   ├── request_client.py #   requests.Session 封装：URL 拼接 / 超时 / 日志
│   ├── assert_util.py    #   断言工具：equals / code_ok / not_empty / match ...
│   ├── token_util.py     #   用户端 JWT 自签
│   ├── yaml_util.py      #   yaml 读取（已处理 Windows 编码）
│   ├── db_client.py      #   数据库访问封装（with 语句管理连接，防泄漏）
│   ├── report_util.py    #   Allure 响应体附件
│   └── logger.py
├── data/                 # 数据层：测试数据外置
│   ├── login_cases.yaml
│   └── dish_cases.yaml
├── testcase/             # 用例层：只写业务语义
│   ├── test_login.py
│   ├── test_overage.py
│   └── test_dish_db.py   #   DB 双层校验（接口响应 vs 数据库对账）
├── conftest.py           # fixture：admin_client / user_client / user_token / db
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
`conftest.py` 里用 `scope="session"` 的 fixture，整个测试会话只登录一次，token 注入 `Session.headers`，后续所有请求自动携带。避免"token 过期就逐条替换"。

**2. 用户端 token 自签（本项目最特殊的一点）**
用户端是微信小程序登录，本地无法复现真实登录流程。方案是**按后端拦截器的验签规则自签 JWT**：

| 端 | 密钥 | Header | Claims |
|---|---|---|---|
| 管理端 | `itcast` | `token` | 登录接口返回 |
| 用户端 | `itheima` | `authentication` | `{userId: 4}` |

自签能成立的前提：后端拦截器**只验签、不查 session**。已实测 3 个用户端接口携带自签 token 返回 `code=1`。

**3. 断言分层（L1–L5）**
L1 HTTP 状态码 → L2 业务码 → L3 结构（字段是否存在）→ L4 字段值 → L5 动态规则（正则 / 格式校验）。
例如正向登录：断 200 + `code==1` + `data` 含 `token` 字段 + token 非空 + JWT 按 `.` 切分是 3 段。

**4. 数据驱动**
测试数据放在 `data/login_cases.yaml`，`build_login_cases()` 在收集阶段把 yaml 翻译成 `pytest.param` 列表。**是否挂 xfail 由数据里的 `xfail: true` 决定**，而不是写死在代码里。

**5. 用 xfail 做缺陷回归门禁**
已知缺陷不删用例，而是挂 `@pytest.mark.xfail(strict=True)`，断言里写**正确的期望值**：

| 阶段 | 用例状态 | CI |
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

读对账验证"接口诚实"，写后落库验证"接口没骗人"——`POST /admin/employee` 返回 `code=1` 不等于数据真的进库了，必须直查 `employee` 表确认。断言三层：字段一致（`username`/`id_number`）→ 业务默认值（`status=1`）→ 安全维度（密码是 MD5 密文而非明文）。

写操作必然污染数据库，所以用**唯一标记 + 造删对称**处理：
- 造数用毫秒时间戳构造全局唯一字段值，撞上唯一索引的失败**与被测业务无关**，必须避免；
- `created_employee` fixture 用 **yield 两段式**：`yield` 前造数并查库拿主键，`yield` 后 `DELETE WHERE id=?` 清理。**pytest 保证 teardown 一定执行**，即使用例断言失败或抛异常——这比 unittest 的 `tearDown()` 可靠（后者在 `setUp()` 抛异常时根本不跑，而那恰恰最需要清理）；
- 清理**只按主键**，绝不用 `WHERE username LIKE 'auto_%'` 这类模糊条件：条件越宽误伤面越大，清理动作也要遵守最小影响面；
- 清理失败只 `logger.warning` 不抛异常——否则用例被标成 ERROR，"清理失败"会盖住真正的"断言失败"。

已实测：故意让用例断言失败，`auto_` 前缀残留仍为 0，员工表总行数不变。

> ⚠️ **踩过的坑**：`pymysql` 默认 `autocommit=False`，第一条 SELECT 就隐式开启事务；MySQL InnoDB 默认 `REPEATABLE READ`，同一事务内是快照读——**后端应用（另一个连接）刚提交的新行读不到**，表现为"POST 返回成功，紧接着 SELECT 查不到"，用例假红且伪装成后端 bug。故 `DBClient` 连接显式开 `autocommit=True`。代价是写操作不可回滚，但黑盒 API 测试本就拿不到后端事务句柄，可接受。

---

## 用例清单（14 条）

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

---

## 实测发现的缺陷

三个都是跑用例时发现的真实问题，不是构造的演示数据。

### 缺陷 1：空用户名 + 默认密码可登录管理后台（高危）

| 项 | 内容 |
|---|---|
| 接口 | `POST /admin/employee/login` |
| 复现 | `{"username": "", "password": "123456"}` |
| 实际 | `code=1` 登录成功，返回 `id=75 / name=测试员工` 的合法 JWT |
| 期望 | 拒绝登录 |
| 根因 | ① 新增员工接口未校验 `username` 非空，允许创建空用户名账号 ② 登录接口未拒绝空用户名 |
| 备注 | `username: " "`（空格）同样成功；`nonexistuser` 正常返回"账号不存在" |

### 缺陷 2：缺失必填参数返回 500（中）

| 项 | 内容 |
|---|---|
| 接口 | `GET /user/dish/list` |
| 复现 | 不传 `categoryId` 直接请求 |
| 实际 | HTTP 500 |
| 期望 | HTTP 400（客户端参数错误） |
| 定性 | 入参校验缺失，异常冒泡成 5xx，会污染监控告警 |

### 缺陷 3：`employee.id_number` 无任何校验（中 / P2）

| 项 | 内容 |
|---|---|
| 接口 | `POST /admin/employee` |
| 复现 | 用**相同 `idNumber`**、不同 `username` 连续新增两名员工 |
| 实际 | 两次均 `code=1` 成功，`id_number` 完全相同地落库 |
| 期望 | 第二次被拒绝，并提示"该身份证号已存在" |
| 证据 | DB 层 `SHOW INDEX` 仅 `PRIMARY(id)` 与 `idx_username(UNIQUE)`，`id_number` 无索引无约束；`EmployeeServiceImpl.save()` 无任何查重与格式校验；存量 21 行里已有 2 组重复身份证（id 82/83、12/13），另有 1 条空字符串 |
| 定级依据 | 管理端接口需 admin JWT，外部无法利用 → **不是安全漏洞**；危害是数据质量与业务逻辑（同一人两个员工账号 → 考勤/工资/权限重复）。对比缺陷 1（任何人可打的鉴权绕过）量级不同，故定"中 / P2"，建议修复而非阻塞发布 |
| 提单论据 | 同表 `username` 建了唯一索引，说明开发者有"业务唯一字段加约束"的意识；`id_number` 业务上同为自然人唯一标识却无约束 → 是**遗漏，不是设计选择**。用同类字段的不一致做论据，比"我觉得应该唯一"硬得多 |
| 修复建议 | DB 加 `UNIQUE KEY uk_id_number`（存量重复需先清洗）；`save()` 前查重并抛业务异常，不要让 `DuplicateKeyException` 冒泡成 500；补 18 位格式与校验位校验 |

### 安全探测结论（正面）

- **SQL 注入防护有效**：`' or '1'='1`、`' or 1=1 -- ` 均返回"账号不存在"，MyBatis `#{}` 预编译生效。
- **用户名尾部空格未 trim**：`'admin '` 可登录为 admin（MySQL PAD SPACE 排序规则下 `'admin ' = 'admin'` 成立），可绕过用户名唯一性约束，判中危。密码不受影响。

---

## 已知限制

诚实说明这个框架**现在做不到**什么：

- **未接入 CI**。被测后端跑在本机 `localhost:8080`，云端没有这个服务，`base_url` 打空。要真接 CI 得先用 docker-compose 把被测系统 + MySQL + Redis 一起起起来。
- **写后落库目前只覆盖"管理端新增员工"**。下单业务链路（`orders` / `order_detail` 多表联动 + 跨端 token 切换）尚未覆盖，其脏数据清理也更复杂。
- **数据隔离用"唯一标记 + 造删对称"，不是独立测试库**。写用例与业务库同库，靠 fixture 按主键精确清理兜底。更彻底的方案是独立测试库，本项目无独立环境——这是已知的工程权衡，不是疏漏。
- **未做接口依赖串联**。目前用例彼此独立，没有"下单 → 查订单"这类业务链路。
- **环境依赖本地服务**，换机器要改 `config.yaml`。

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
