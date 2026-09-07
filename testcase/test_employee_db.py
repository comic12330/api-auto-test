# -*- coding: utf-8 -*-
"""写后落库用例：接口写操作 → 直查数据库确认真的落了。

与 test_dish_db.py（读对账）的区别：
    - 读对账：接口说"返回了什么" vs 库里"实际有什么" → 验证接口诚实
    - 写后落库：接口说"新增成功" vs 库里"真的多了一条" → 验证接口没骗人

写操作会污染数据库，所以每一条造出来的数据都必须有对应的清理动作：
    - 第一条由 conftest.created_employee 的 yield teardown 清理
    - 第二条（重复身份证用例自己造的）由用例内 finally 清理
"""
import allure
import pytest

from api.employee_api import (
    add_employee,
    build_employee_payload,
    delete_employee_by_id,
    select_employee_by_username,
)
from common.assert_util import AssertUtil
from common.report_util import attach_response

# MD5("123456") —— 苍穹外卖新增员工的默认密码。后端在 EmployeeServiceImpl.save()
# 里用 DigestUtils.md5DigestAsHex 加密后落库，所以库里不该出现明文
MD5_123456 = "e10adc3949ba59abbe56e057f20f883e"


@allure.epic("苍穹外卖接口自动化")
@allure.feature("双层校验")
@allure.story("新增员工写后落库")
@allure.title("新增员工后，数据库应存在该记录且字段正确")
@allure.severity(allure.severity_level.CRITICAL)
def test_employee_created_in_db(created_employee):
    """写后落库：接口返回成功 ≠ 数据真的进库了，必须直查库确认。

    断言分三层，逐层加深：
      1. 记录存在（fixture 里已保证，查不到直接 fail 并给出 username + 响应体）
      2. 业务字段正确：username / id_number 与请求一致、status 默认启用
      3. 安全维度：密码是 MD5 密文而非明文 —— 这条是很多功能测试想不到的
    """
    emp_id, payload, row = created_employee

    # ① 字段一致性：请求体传进去的值，必须原样落在库里
    AssertUtil.equals(row["username"], payload["username"], "落库 username 应与请求一致")
    AssertUtil.equals(row["id_number"], payload["idNumber"], "落库 id_number 应与请求一致")

    # ② 业务默认值：新员工默认启用（后端 StatusConstant.ENABLE）
    AssertUtil.equals(row["status"], 1, "新员工默认状态应为启用 status=1")

    # ③ 安全维度：密码必须加密落库。若这里等于 "123456"，说明后端明文存密码
    AssertUtil.equals(row["password"], MD5_123456, "密码应加密落库（MD5），不得明文")
    AssertUtil.not_equals(row["password"], "123456", "密码不得以明文形式落库")


@allure.epic("苍穹外卖接口自动化")
@allure.feature("双层校验")
@allure.story("数据完整性")
@allure.title("[已知缺陷] 重复身份证号新增员工应被拒绝")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.xfail(
    reason="缺陷③：employee.id_number 无唯一约束，且 EmployeeServiceImpl.save() 未做查重，"
           "相同身份证号可重复新增成功（定级 P2/中）。修复后本用例 XPASS 会提醒删除标记",
    strict=True,
)
def test_id_number_duplicate_should_be_rejected(created_employee, admin_client, db):
    """已知缺陷③：身份证号重复时应拒绝新增。

    依据（不是"我觉得身份证应该唯一"）：
      - 同表 username 建了唯一索引 → 开发者有"业务唯一字段加约束"的意识
      - id_number 业务上同样是自然人唯一标识却没有约束 → 是遗漏，不是设计选择
      - 存量实证：21 行员工数据里已有 2 组重复身份证（id 82/83、12/13）

    ⚠️ 为什么挂 xfail 而不是硬断言：这是**设计缺陷**，产品可能判定不修。
    硬断言会让用例长期红、污染 CI；xfail 让它在 CI 里保持绿，
    等后端修好后 XPASS → strict=True 让构建变红，提醒删标记转回归用例。
    """
    _, first_payload, _ = created_employee

    # 用**完全相同**的身份证号、不同的 username 再新增一次
    dup_payload = build_employee_payload(id_number=first_payload["idNumber"])
    resp = add_employee(admin_client, dup_payload)
    attach_response(resp)
    body = resp.json()

    dup_row = select_employee_by_username(db, dup_payload["username"])
    try:
        # 期望：业务上应拒绝（code != 1）。当前实际 code == 1 → 断言失败 → xfail
        AssertUtil.not_equals(body.get("code"), 1, "重复身份证号的新增应被拒绝")
        # 期望：库里不应出现第二条
        AssertUtil.equals(dup_row, None, "重复身份证号的员工不应落库")
    finally:
        # 第二条是本用例自己造的，fixture 只清理第一条，这条必须自己收尾。
        # 放在 finally：xfail 时断言已失败，清理照样执行。
        if dup_row:
            delete_employee_by_id(db, dup_row["id"])
