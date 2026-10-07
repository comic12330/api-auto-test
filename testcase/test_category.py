# -*- coding: utf-8 -*-
"""test_category.py —— 管理端分类接口用例。"""
import allure
import pytest

from api.category_api import (
    add_category,
    build_category_payload,
    delete_category,
    delete_category_by_id,
    edit_category_by_id,
    get_category_page,
    select_category_by_name,
    set_category_status,
)
from api.shopping_api import list_category
from common.assert_util import AssertUtil


@allure.feature("分类管理")
@allure.story("新增分类写后落库")
@allure.title("新增分类后直查库：字段一致 + 默认禁用")
def test_category_created_in_db(created_category):
    """新增分类 → 直查库确认真的写进去了、写得对。

    数据由 created_category fixture 造，用例跑完自动清理，
    所以这里可以放心断言"库里现在应该有这条"。
    """
    _category_id, payload, row = created_category

    AssertUtil.equals(row["name"], payload["name"], "落库 name 与请求一致")
    AssertUtil.equals(row["type"], payload["type"], "落库 type 与请求一致")
    AssertUtil.equals(row["sort"], payload["sort"], "落库 sort 与请求一致")
    # 这条断言的价值：status 是后端默认填的，接口响应里根本不返回，只有查库才知道。
    # 实测结论：新分类默认是**禁用 0**（CategoryServiceImpl.save 里写死
    # setStatus(StatusConstant.DISABLE)），跟新增员工默认启用(1)正好相反。
    # 教训：别拿另一个接口的经验做类比，要么查源码要么实测。
    AssertUtil.equals(row["status"], 0, "新分类默认禁用 status=0")


@allure.feature("分类管理")
@allure.story("删除分类的业务规则")
@allure.title("分类下挂了菜品/套餐时，删除必须被拒绝且数据不能少")
@pytest.mark.parametrize(
    "category_id, keyword",
    [(11, "菜品"), (13, "套餐")],
    ids=["被菜品关联", "被套餐关联"],
)
def test_delete_related_category_should_be_rejected(admin_client, db, category_id, keyword):
    """业务规则：分类下关联了菜品或套餐时禁止删除。

    用的是**存量数据**（id=11 挂 2 个菜品、id=13 挂 1 个套餐），只读不写，
    所以不需要造数、不需要清理 —— 这正是"读对账"和"写后落库"的分界：
    只有要写库的用例才需要 yield 造删对称。
    """
    body = delete_category(admin_client, category_id).json()

    AssertUtil.not_equals(body.get("code"), 1, f"挂了{keyword}的分类不该删除成功")
    assert keyword in (body.get("msg") or ""), (
        f"提示应说明被{keyword}关联，实际 msg={body.get('msg')}"
    )

    # 光看接口返回还不够：必须确认库里数据还在。
    # 否则"拒绝"可能只是接口嘴上说说，实际已经删了。
    row = db.query_one("SELECT id FROM category WHERE id=%s", (category_id,))
    assert row is not None, f"接口说不能删，但 id={category_id} 已经从库里消失了"


@allure.feature("分类管理")
@allure.story("分类分页查询")
@allure.title("分页查询：name 过滤真的在过滤，pageSize 真的在切页")
def test_category_page_filter_and_paging(admin_client, created_category):
    """分页查询的两个回归点，都是 2026-09-26 修过的真实 bug：

    ① `name` 没放进 `params` —— 形参是死的，调用方以为在过滤，实际全量返回；
    ② 分页大小参数名写成 `page_size`（后端 DTO 字段是 `pageSize`）——
       Spring 绑定不上时**不报错**，静默取默认值，表现为"分页参数好像没生效"。

    这两个 bug 的共同特征是**静默失败**：接口照样返回 HTTP 200 + code=1，
    不真的去断言"过滤后的条数"，根本抓不到。所以这条用例断言的是**数量**，
    不是"接口没报错"。
    """
    _category_id, payload, _row = created_category

    # ① name 过滤必须真的下到 SQL。
    #    用唯一 name 过滤却返回多条 = 过滤条件没生效（等价于全表返回）。
    data = get_category_page(
        admin_client, page=1, page_size=10, name=payload["name"]
    ).json()["data"]
    AssertUtil.equals(data["total"], 1,
                      f"按唯一 name 过滤应恰好 1 条，实际 total={data['total']}"
                      f"（返回全量说明 name 没下到 SQL）")
    AssertUtil.equals(len(data["records"]), 1, "records 条数应与 total 一致")
    AssertUtil.equals(data["records"][0]["name"], payload["name"], "命中的应是刚造的那条")

    # ② pageSize 与 total 的语义。
    #    total 是「过滤后的总条数」，不是「本页条数」—— 这是最容易搞反的一点。
    #    本环境库存分类 12 条，所以 total 必然 >= 2，下面能真正验证"切页"。
    p1 = get_category_page(admin_client, page=1, page_size=1).json()["data"]
    p2 = get_category_page(admin_client, page=1, page_size=2).json()["data"]
    assert p1["total"] >= 2, f"本环境库存分类应 >= 2 条，实际 total={p1['total']}"
    AssertUtil.equals(len(p1["records"]), 1, "pageSize=1 时本页应恰好 1 条")
    AssertUtil.equals(len(p2["records"]), 2, "pageSize=2 时本页应恰好 2 条")
    # 这一条专门打"把 total 当成本页条数"的误解：换 pageSize，total 不该动。
    AssertUtil.equals(p1["total"], p2["total"], "total 是过滤后总条数，不应随 pageSize 变化")

    # 关于 page 是否真的切页：**不在本用例里断言**。
    #
    # 原本这里写的是「第 2 页的 id 不应等于第 1 页」。实测发现这句是**脆弱断言**：
    # 它默认了「排序稳定」这个前提，而这个前提在后端不成立 ——
    # pageQuare 的 SQL 是 `order by sort`，没有唯一键兜底，sort 并列时
    # MySQL 的行顺序不保证，所以第 1 页 / 第 2 页返回什么本身就不可预测。
    # 依赖它的断言会时红时绿，属于典型的 flaky test。
    #
    # 正确做法是把「分页不变量」单独拎出来当缺陷门禁：
    # 见下面的 test_category_page_no_duplicate_or_missing。


@allure.feature("分类管理")
@allure.story("修改分类")
@allure.title("只改 name 时，type / sort / status 不能被连带清空")
def test_edit_category_only_updates_given_fields(admin_client, db, created_category):
    """修改分类：只传 name 时，其余字段必须保持原值。

    依据是 `CategoryMapper.xml` 里那条 `<update>`：

        <set>
            <if test="type != null">type=#{type},</if>
            <if test="name != null">name=#{name},</if>
            <if test="sort != null">sort=#{sort},</if>
            <if test="status != null">status=#{status},</if>
        </set>
        where id=#{id}

    即**部分更新**：只更新传了的字段，没传的保持原值（不是置 null）。
    这是 MyBatis 动态 SQL 的常见约定，但它是个隐式契约 —— 一旦有人把它
    改成全字段覆盖，没传的字段就会被写成 null，而接口**依然返回 code=1**。
    这条用例的价值就是把"部分更新"这个契约固化成门禁。

    注意：只改 name 而不动 type/sort，正好也绕开了"改了 type 会不会影响
    已关联菜品"这类业务副作用，是个干净的边界。
    """
    category_id, payload, row = created_category

    # name 派生自唯一 name（auto_+运行标识+序号），加后缀后仍全局唯一，
    # 不会撞 category.name 的唯一索引；长度也远小于 varchar(32)。
    new_name = payload["name"] + "_edit"
    body = edit_category_by_id(
        admin_client, {"id": category_id, "name": new_name}
    ).json()
    AssertUtil.code_ok(body, 1, "修改分类业务码")

    fresh = db.query_one(
        "SELECT id, name, type, sort, status FROM category WHERE id=%s", (category_id,)
    )
    assert fresh is not None, f"修改后应仍能查到 id={category_id}（是否被误删？）"

    AssertUtil.equals(fresh["name"], new_name, "name 应被更新为新值")
    AssertUtil.equals(fresh["type"], row["type"], "只改了 name，type 不应被清空")
    AssertUtil.equals(fresh["sort"], row["sort"], "只改了 name，sort 不应被清空")
    AssertUtil.equals(fresh["status"], row["status"], "只改了 name，status 不应被改动")


@allure.feature("分类管理")
@allure.story("启用禁用分类")
@allure.title("启停用只改 status，且用户端可见性随之变化")
def test_category_status_toggle_affects_user_visibility(
        admin_client, user_client, db, created_category):
    """启用 / 禁用分类，三个考点：

    ① **跨接口复用同一个 Mapper 方法的副作用。** `startOrStop` 和「修改分类」
       走的是同一个 `categoryMapper.update()`，但它只 set 了 status 和 id，
       动态 SQL 下**只会更新 status 一列**。如果哪天这条 SQL 被改成全字段覆盖，
       name / type / sort 会在"点一下启停用"时被悄悄清空 —— 线上事故级的问题，
       而接口照样返回成功。
    ② **新分类默认是禁用(0)**（源码 `save()` 里写死 `setStatus(DISABLE)`），
       所以"先启用"是必要前提，不能假设它一出生就是可见的。
    ③ **跨端联动**：`GET /user/category/list` 的 SQL 写死 `where status = 1`，
       所以管理端点一下启用，用户端才看得到；一禁用，立刻消失。
       这比只断言 status 字段更有业务含义 —— 它验证的是"启停用真的有业务效果"。
    """
    category_id, payload, row = created_category
    AssertUtil.equals(row["status"], 0, "前置：新建分类默认应为禁用 0")

    def user_visible_ids():
        """用户端当前可见的分类 id 列表（按分类类型查）。"""
        data = list_category(user_client, category_type=payload["type"]).json()["data"]
        return [c["id"] for c in data]

    # ① 启用 → status=1，且用户端立刻可见
    body = set_category_status(admin_client, category_id, 1).json()
    AssertUtil.code_ok(body, 1, "启用分类业务码")

    fresh = db.query_one(
        "SELECT name, type, sort, status FROM category WHERE id=%s", (category_id,)
    )
    AssertUtil.equals(fresh["status"], 1, "启用后 status 应为 1")
    AssertUtil.equals(fresh["name"], row["name"], "启停用不应连带改动 name")
    AssertUtil.equals(fresh["type"], row["type"], "启停用不应连带改动 type")
    AssertUtil.equals(fresh["sort"], row["sort"], "启停用不应连带改动 sort")
    assert category_id in user_visible_ids(), (
        f"启用后分类 id={category_id} 应出现在用户端列表，"
        f"实际可见={user_visible_ids()}"
    )

    # ② 禁用 → status=0，且用户端立刻不可见
    body = set_category_status(admin_client, category_id, 0).json()
    AssertUtil.code_ok(body, 1, "禁用分类业务码")

    fresh = db.query_one("SELECT status FROM category WHERE id=%s", (category_id,))
    AssertUtil.equals(fresh["status"], 0, "禁用后 status 应回到 0")
    assert category_id not in user_visible_ids(), (
        f"禁用后分类 id={category_id} 不应出现在用户端列表"
    )


@allure.feature("分类管理")
@allure.story("分类分页查询")
@allure.title("[已知缺陷] 翻页不应重复或遗漏记录")
@allure.severity(allure.severity_level.NORMAL)
@pytest.mark.xfail(
    reason="缺陷④：CategoryMapper.xml 的 pageQuare 只写了 `order by sort`，没有唯一键做 "
           "tie-breaker。sort 值重复时（业务上完全正常：管理端新增/修改分类时 sort 可任意填，"
           "本环境 id=13 与 id=97 就是并列的 sort=1），MySQL 对并列行的返回顺序不作保证，"
           "实测翻页出现「同一条记录被返回两次、另一条记录任何一页都取不到」。"
           "修复：改成 `order by sort, id`（定级 P2/中）。修复后本用例 XPASS，"
           "strict=True 会让构建变红，提醒删掉标记转成回归用例。",
    strict=True,
)
def test_category_page_no_duplicate_or_missing(admin_client, db):
    """分页的本质语义：**翻完所有页拼起来，必须恰好等于全量记录**——不重不漏。

    这才是「page 参数生效」应该被验证的方式。原先写的「第 2 页 ≠ 第 1 页」是错的：
    它把「排序必须稳定」当成了前提，而排序稳定是**被测系统的义务**，不是测试的假设。
    后端排序一旦不稳，那种断言只是碰巧变红，说不清问题；而这条不变量断言
    在任何顺序抖动下都会红，并且直接指出症状（重复了哪几条 / 漏了哪几条）。

    触发条件必须**主动构造**，不能依赖库存数据「恰好并列」——
    否则哪天有人把并列数据清掉，门禁会静默变成假绿（XPASS 报错）。
    """
    created_id = None
    try:
        # 造一条 sort 与库中最小 sort 相同的分类 → 稳定制造「排序键并列」。
        min_sort = db.query_one("SELECT MIN(sort) AS s FROM category")["s"]
        payload = build_category_payload(sort=min_sort)
        AssertUtil.code_ok(add_category(admin_client, payload).json(), 1, "造并列分类")

        row = select_category_by_name(db, payload["name"])
        assert row is not None, f"造数未落库：name={payload['name']}"
        created_id = row["id"]

        # pageSize=1 逐页翻：页越小，并列行被拆到相邻页的概率越高，缺陷越容易暴露。
        total = get_category_page(admin_client, page=1, page_size=1).json()["data"]["total"]

        collected = []
        for p in range(1, total + 1):
            recs = get_category_page(
                admin_client, page=p, page_size=1
            ).json()["data"]["records"]
            collected += [r["id"] for r in recs]

        # ① 翻满 total 页，条数必须正好是 total。
        AssertUtil.equals(len(collected), total, "翻完所有页的条数应等于 total")

        # ② 不许有重复 —— 缺陷的直接症状。
        dups = sorted({i for i in collected if collected.count(i) > 1})
        AssertUtil.equals(
            len(set(collected)), total,
            f"翻页出现重复：{len(collected)} 条里有 {len(collected) - len(set(collected))} 条重复"
            f"（重复的 id={dups}）",
        )

        # ③ 与库中全量对账：接口翻页能取到的 id 集合，必须等于库里的 id 集合。
        #    「漏了谁」只有跟 DB 比才看得出来。
        db_ids = {r["id"] for r in db.query("SELECT id FROM category")}
        AssertUtil.equals(sorted(set(collected)), sorted(db_ids),
                          "翻页取到的 id 集合应与库中全量一致（差集就是被漏掉的记录）")
    finally:
        if created_id is not None:
            delete_category_by_id(db, created_id)
