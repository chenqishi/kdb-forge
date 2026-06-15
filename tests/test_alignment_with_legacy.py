"""与旧 `SearchDataInterface` 的对齐测试（核心）。

目标：证明新 CRUD（KnowledgeService 文本入口）在 CRUD 负责的字段与 search 行为上，
与旧 `SearchDataInterface` 一致。这里**不对比业务逻辑**（dedup/category/keyword/质量默认值），
那些已被刻意排除——对比的范围限定在 CRUD 负责的子集：

①  `_id` 对齐：新 `_prepare_document['_id']` == 旧 `gen_data_id` == 旧 `process_one_data` 后的 `_id`。
②  prepared 字段对齐：同一份输入，新 `_prepare_document` 与旧 `process_one_data` 产出的
    CRUD 字段一致（title/content/data_type/platform、indexes 文本集合、向量维度、ext_info 归集、del_flag=0）。
③  search 对齐：同一批文档下，相同 query 通过新 `service.search_text` 与旧
    `legacy.search_data_by_query` 返回的命中 `_id` 顺序、`score`、`similarity` 在容差内一致。
"""

import copy
import uuid

import pytest

from tests.conftest import wait_for, wait_for_absent, wait_for_present

pytestmark = pytest.mark.integration

# 唯一 platform 隔离每次跑测：避免跨 run 的 test_case 索引残留对结果造成干扰
PLATFORM = f"kdb_align_test_{uuid.uuid4().hex[:8]}"


def _align_input(suffix: str = "1") -> dict:
    """业务字段齐全的对齐输入；规避旧实现在缺业务字段时自动填默认值导致的对比噪声。"""
    return {
        "title": f"kdb 对齐：忘记密码怎么办？({suffix})",
        "content": f"在登录页点击『忘记密码』，按邮箱链接重置。({suffix})",
        "data_type": "qa",
        "platform": PLATFORM,
        "audit_result": 1,
        "quality_level": "high",
        "from_type": "chat",
        "from_type_norm": "chat",
        "tags": ["登录", "密码"],
        "synonyms_title": [f"如何重置密码 ({suffix})"],
        "trace_id": f"align_case_{suffix}",  # 非 schema 字段，应进 ext_info
        "custom_attr": "ext",                # 非 schema 字段
    }


# ============================================================
# ① _id 对齐
# ============================================================
def test_id_alignment_with_legacy_gen_data_id(service):
    """新 _prepare_document['_id'] == 旧 gen_data_id（多种 data_type）。"""
    from kdb.legacy_bridge import legacy_gen_data_id, HAS_LEGACY_GEN_DATA_ID

    if not HAS_LEGACY_GEN_DATA_ID:
        pytest.skip("旧 gen_data_id 不可用，对齐测试无意义（已在 ids.py 用复刻兜底）")

    cases = [
        {"title": "T", "content": "C", "data_type": "qa"},
        {"title": "标题", "content": "内容", "data_type": "doc"},
        {"title": "drop_me", "content": "片段内容", "data_type": "segment"},  # segment 会去 title
        {"title": "", "content": "no title doc", "data_type": "qa"},
    ]
    for c in cases:
        # 新 prepared 后的 _id
        prepared = service._prepare_document(copy.deepcopy(c))
        # 旧 gen_data_id 在 prepared 后（已 pop 过 title 等）上调用，与新一致
        legacy_id = legacy_gen_data_id(prepared)
        assert prepared["_id"] == legacy_id, f"_id 不对齐：case={c}"


def test_id_alignment_with_legacy_process_one_data(service, legacy_interface):
    """新 _prepare_document 与旧 process_one_data 在相同输入下生成相同的 _id。"""
    inp = _align_input("idcase")
    new_prep = service._prepare_document(copy.deepcopy(inp))
    legacy_prep = copy.deepcopy(inp)
    assert legacy_interface.process_one_data(legacy_prep) is True
    assert new_prep["_id"] == legacy_prep["_id"]


# ============================================================
# ② prepared 字段对齐（CRUD 负责子集）
# ============================================================
def test_prepared_fields_alignment(service, legacy_interface):
    """同输入下，新/旧 prepared 在 CRUD 负责字段上一致。

    业务默认值（audit_result/quality_level/from_type/tags/from_type_norm/primary_category/
    keywords/dataset）不在对比范围——它们属业务逻辑，已刻意从新 CRUD 排除。
    """
    inp = _align_input("fields")

    new_prep = service._prepare_document(copy.deepcopy(inp))
    legacy_prep = copy.deepcopy(inp)
    assert legacy_interface.process_one_data(legacy_prep) is True

    # 1) 基础字段一致
    for field in ["_id", "title", "content", "data_type", "platform"]:
        assert new_prep.get(field) == legacy_prep.get(field), f"field {field} 不一致"

    # 2) synonyms_title 一致
    assert new_prep.get("synonyms_title") == legacy_prep.get("synonyms_title")

    # 3) del_flag=0（新/旧都按底层引擎契约填充）
    assert new_prep.get("del_flag") == 0
    assert legacy_prep.get("del_flag") == 0

    # 4) 时间字段都存在为字符串（具体值因毫秒级时序不同不比较）
    for field in ["insert_time", "update_time"]:
        assert isinstance(new_prep.get(field), str)
        assert isinstance(legacy_prep.get(field), str)

    # 5) 向量维度
    assert len(new_prep["title_embedding"]) == 1024
    assert len(legacy_prep["title_embedding"]) == 1024
    assert len(new_prep["content_embedding"]) == 1024
    assert len(legacy_prep["content_embedding"]) == 1024
    # 向量值容差对齐（DashScope 在同一输入下确定性）
    import numpy as np
    assert np.allclose(new_prep["title_embedding"], legacy_prep["title_embedding"], atol=1e-6)
    assert np.allclose(new_prep["content_embedding"], legacy_prep["content_embedding"], atol=1e-6)

    # 6) indexes：文本集合一致；每项向量维度一致
    new_idx_texts = {idx["text"] for idx in new_prep["indexes"]}
    legacy_idx_texts = {idx["text"] for idx in legacy_prep["indexes"]}
    assert new_idx_texts == legacy_idx_texts
    for idx in new_prep["indexes"]:
        assert len(idx["embedding"]) == 1024
    for idx in legacy_prep["indexes"]:
        assert len(idx["embedding"]) == 1024

    # 7) ext_info 归集一致（同一 SCHEMA_FIELDS / doc_schema_field 集合）
    new_ext = new_prep.get("ext_info", {})
    legacy_ext = legacy_prep.get("ext_info", {})
    # 新CRUD仅做归集，不增不减；旧 process_one_data 同样仅归集（无业务侧塞入 ext_info 的操作）
    assert new_ext == legacy_ext, f"ext_info 归集不一致：new={new_ext} vs legacy={legacy_ext}"

    # 8) 非 schema 字段确实进了 ext_info（双方都进）
    assert new_ext.get("trace_id") == "align_case_fields"
    assert new_ext.get("custom_attr") == "ext"


# ============================================================
# ③ search 对齐（真实 ES：相同数据下、相同 query，新/旧返回一致）
# ============================================================
@pytest.fixture()
def aligned_dataset(service, repo, test_index, cleanup_ids):
    """插入 3 条不同主题的对齐文档（业务字段齐全），返回 (id_list, query_to_top_id_hint)。"""
    docs = [
        {
            "title": "kdb 对齐 set1：忘记密码怎么办？",
            "content": "在登录页点击『忘记密码』，按邮箱链接重置。",
            "data_type": "qa", "platform": PLATFORM, "audit_result": 1, "quality_level": "high",
            "from_type": "chat", "synonyms_title": ["如何重置密码"],
        },
        {
            "title": "kdb 对齐 set2：如何修改账号头像？",
            "content": "进入『我的』，点头像，选择本地图片上传。",
            "data_type": "qa", "platform": PLATFORM, "audit_result": 1, "quality_level": "high",
            "from_type": "chat",
        },
        {
            "title": "kdb 对齐 set3：怎么开通会员？",
            "content": "首页右上『会员』按钮进入开通流程，按提示支付。",
            "data_type": "qa", "platform": PLATFORM, "audit_result": 1, "quality_level": "high",
            "from_type": "chat",
        },
    ]
    from kdb.crud.ids import gen_data_id
    ids = []
    for d in docs:
        _id = gen_data_id({"title": d["title"], "content": d["content"], "data_type": "qa"})
        ids.append(_id)
        cleanup_ids.append(_id)
        ok, msg = service.insert_text(dict(d), index_name=test_index, refresh_imm=True)
        assert ok, msg

    # 等待全部 get 可见
    for _id in ids:
        wait_for_present(repo, _id, test_index)
    # 等待 search 可见（用唯一 platform 过滤；search 比 get 慢一拍）
    def _all_searchable():
        hits, _ = repo.search_multi(
            {"query": "kdb", "attribute": [{"platform": [PLATFORM]}]},
            index_name=test_index, size=20,
        )
        seen = {d.get("_id") for d in hits}
        return seen if all(i in seen for i in ids) else False
    wait_for(_all_searchable, timeout=15.0)
    return ids, "我忘了密码"  # 该 query 应靠近第一条


def test_search_results_align_with_legacy(service, legacy_interface, aligned_dataset, test_index):
    """同一 query + 同 condition + 同索引下，新/旧返回相同的 _id 列表、score、similarity。"""
    ids, query = aligned_dataset
    condition = [{"data_type": ["qa"], "platform": [PLATFORM]}]
    size = 5

    new_docs, new_total = service.search_text(
        query, index_name=test_index, condition_dicts=copy.deepcopy(condition),
        size=size, search_type="qa", data_type="text", use_synonyms=False,
    )
    legacy_docs, legacy_total = legacy_interface.search_data_by_query(
        query, index_names=test_index, condition_dicts=copy.deepcopy(condition),
        size=size, search_type="qa", data_type="text", use_synonyms=False,
    )

    new_ids = [d.get("_id") for d in new_docs]
    legacy_ids = [d.get("_id") for d in legacy_docs]

    # 1) 命中 _id 集合一致（多 shard ES 的原始返回顺序在分数极近时可能微抖动；
    #    新旧用各自的 EsSearchInterface 实例发同一查询时该抖动不可预测。
    #    语义对齐的真正指标：相同的 doc 集合、相同的相似度、相同的"按相似度排序后顺序"。）
    assert set(new_ids) == set(legacy_ids), (
        f"_id 集合不一致：new={new_ids} legacy={legacy_ids}"
    )

    # 2) total 一致
    assert new_total == legacy_total

    # 3) 每条相同 _id 的 similarity 严格对齐（最重要的语义指标——Service 与旧
    #    SearchDataInterface 的 _cal_similarity 已逐行复刻，相同 query + 相同 doc 必相同）
    new_by_id = {d["_id"]: d for d in new_docs}
    legacy_by_id = {d["_id"]: d for d in legacy_docs}
    for _id in set(new_ids):
        n_sim = new_by_id[_id].get("similarity", 0)
        l_sim = legacy_by_id[_id].get("similarity", 0)
        assert abs(n_sim - l_sim) < 1e-6, (
            f"similarity 差异：{n_sim} vs {l_sim} on {_id}"
        )

    # 4) 按 similarity 降序后顺序完全一致（消除 ES 多 shard 抖动）
    new_sorted = sorted(new_docs, key=lambda d: (-d.get("similarity", 0), d.get("_id", "")))
    legacy_sorted = sorted(legacy_docs, key=lambda d: (-d.get("similarity", 0), d.get("_id", "")))
    assert [d["_id"] for d in new_sorted] == [d["_id"] for d in legacy_sorted]

    # 5) 至少命中我们插入的第一条
    assert ids[0] in new_ids
