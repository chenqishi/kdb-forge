"""离线差分测试基座（零 ES / 零 DashScope）。

思路（对应审计报告第八节建议 1）：
- `FakeEmbedding`：文本 → 确定性向量（md5 种子）；新旧共享同一实例，消除向量分叉。
- `FakeEngine`：录制所有引擎调用入参（索引名按旧 `_get_index_name` 口径**解析后**录制，
  屏蔽"新 Repository 先填默认索引 / 旧接口传 None 由引擎兜底"的等价差异），回放注入文档集。
- 旧 `SearchDataInterface` 用 `__new__` 绕过构造器注入 fakes（不读 config、不连 ES）。
- 新 `KnowledgeService` 注入 `KnowledgeRepository(engine=FakeEngine)` + 同一 FakeEmbedding。

同一输入分别驱动新旧两套接口，断言引擎收到的请求、返回加工结果完全一致。
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('archive/forge_pre_refactor/tests_unit/conftest.py')

import copy
import hashlib
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__legacy_source_file__))
_ROOT = os.path.dirname(_HERE)
_SRC = os.path.join(_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

# 旧项目根探测（与 tests/conftest.py 同口径；kdb.legacy_bridge 也会自行探测）
if not os.environ.get("KDB_LEGACY_ROOT"):
    for _cand in (
        "/root/knowledge_database_builder",
        "/root/developer_tools/chenqishi/cursor/knowledge_database_builder",
        "/Users/chenqishi/stone_fish/knowledge_database_builder",
    ):
        if os.path.isdir(os.path.join(_cand, "knowledge_interface_tools")):
            os.environ["KDB_LEGACY_ROOT"] = _cand
            break

EMB_DIM = 8
DEFAULT_INDEX = "test_case"

# 与旧 `SearchDataInterface.__init__` 中 doc_schema_field 字面量一致（旧库 @fd8572c 冻结）。
# 刻意不复用 kdb.crud.models.SCHEMA_FIELDS——差分测试的两边不能共享同一份常量，否则漂移不可见。
#
# 2026-09-07 同步更新：`tags` 已在**旧库**
# （knowledge_interface_tools/search_index_data_interface.py:76）与新 SCHEMA_FIELDS 中同步补齐，
# 故此冻结基线一并加入 `tags`——两侧仍是各自独立的字面量，差分能力不变。
# 背景见 docs/CRUD_Legacy_Difference_Issues.md 第 7 条。
LEGACY_DOC_SCHEMA_FIELD = {
    "title", "synonyms_title", "content", "data_type", "platform",
    "audit_result", "quality_level", "keywords", "tags", "indexes",
    "insert_time", "update_time", "from_type", "ext_info", "_id",
    "title_embedding", "content_embedding", "image_indexes", "del_flag",
    "from_type_norm", "category_infos", "client", "primary_category",
    "dataset", "task_id", "multimodal_contents", "index_name",
}


def normalize(obj):
    """np.ndarray → list，递归处理，便于新旧录制内容做 == 比较。"""
    import numpy as np

    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, dict):
        return {k: normalize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        t = type(obj)
        return t(normalize(v) for v in obj)
    return obj


class FakeEmbedding:
    """确定性 embedding：md5(text) 前 EMB_DIM 字节归一化到 [0,1]。"""

    def __init__(self, dim: int = EMB_DIM):
        self.dim = dim
        self.calls = []
        self.fail = False

    def text2embedding(self, text):
        import numpy as np

        if self.fail:
            raise Exception("获取 embedding 失败: fake embedding down")
        self.calls.append(text)
        digest = hashlib.md5(str(text).encode("utf-8")).digest()
        return np.array([b / 255.0 for b in digest[: self.dim]])


class FakeEngine:
    """录制/回放引擎（旧 EsSearchInterface 的离线替身）。

    - `docs`/`total`：search_multi / search_multi_by_page 的回放内容（deepcopy 返回）。
    - `search_docs`：search（find_duplicates 用）的回放内容。
    - `calls`：[(method, {入参，索引名已按旧 _get_index_name 口径解析}), ...]。
    - `raise_on_multi_list_query=True` 时，search_multi 收到 query 为 list（多 query 主路径）
      即抛错——用于驱动多 query 的多线程回退分支。
    """

    def __init__(self, index_name=DEFAULT_INDEX, docs=None, total=None, search_docs=None):
        self.index_name = index_name
        self.docs = docs or []
        self.total = total if total is not None else len(self.docs)
        self.search_docs = search_docs if search_docs is not None else []
        self.calls = []
        self.insert_ok = True
        self.update_ok = True
        self.raise_on_multi_list_query = False

    # --- 旧 _get_index_name 的解析口径（es_search_interface.py:403-424，去掉 ensure_index 副作用） ---
    def _resolve(self, index_names):
        if not index_names:
            final = self.index_name
        elif isinstance(index_names, list):
            final = ",".join(index_names)
        else:
            final = index_names
        return final.lower()

    def _record(self, method, **kwargs):
        kwargs["index"] = self._resolve(kwargs.pop("index_names", None))
        self.calls.append((method, normalize(copy.deepcopy(kwargs))))

    def calls_of(self, method):
        return [kw for m, kw in self.calls if m == method]

    # --- 检索 ---
    def search_multi(self, query, index_names=None, size=10, page_num=1):
        self._record("search_multi", query=query, index_names=index_names, size=size, page_num=page_num)
        if self.raise_on_multi_list_query and isinstance(query.get("query"), list):
            raise ValueError("fake: multi-list-query not supported")
        return copy.deepcopy(self.docs), self.total

    def search_multi_by_page(self, query, index_names=None, size=10, page_num=1, score_threshold=None):
        self._record(
            "search_multi_by_page", query=query, index_names=index_names,
            size=size, page_num=page_num, score_threshold=score_threshold,
        )
        return copy.deepcopy(self.docs), self.total

    def search(self, query, size=10, index_names=None):
        self._record("search", query=query, size=size, index_names=index_names)
        return copy.deepcopy(self.search_docs)

    def get(self, data_id, index_names=None):
        self._record("get", data_id=data_id, index_names=index_names)
        for d in self.docs:
            if d.get("_id") == data_id:
                return copy.deepcopy(d)
        return None

    # --- 写 ---
    def insert(self, data, index_names=None, refresh_imm=False):
        self._record("insert", data=data, index_names=index_names, refresh_imm=refresh_imm)
        return self.insert_ok

    def update(self, data_id, data, index_names=None):
        self._record("update", data_id=data_id, data=data, index_names=index_names)
        return self.update_ok

    def update_value(self, index_name, update_value_dict, conditions):
        # 旧引擎该方法参数名就是 index_name（str）
        self._record(
            "update_value", update_value_dict=update_value_dict,
            conditions=conditions, index_names=index_name,
        )
        return True

    def delete(self, data_id, index_names=None, refresh=False):
        self._record("delete", data_id=data_id, index_names=index_names, refresh=refresh)
        return True

    # --- 其余包装能力（Repository 委托断言用） ---
    def get_unique_values(self, index_name, field_name, size=10000, include_doc_count=False, extra_query=None):
        self._record(
            "get_unique_values", field_name=field_name, size=size,
            include_doc_count=include_doc_count, extra_query=extra_query, index_names=index_name,
        )
        return ["v1"]

    def scroll_search(self, query, batch_size=1000, scroll_timeout="5m", index_names=None):
        self._record(
            "scroll_search", query=query, batch_size=batch_size,
            scroll_timeout=scroll_timeout, index_names=index_names,
        )
        return iter(copy.deepcopy(self.docs))

    def search_after(self, query, batch_size=1000, sort_field="_id", index_names=None):
        self._record(
            "search_after", query=query, batch_size=batch_size,
            sort_field=sort_field, index_names=index_names,
        )
        return iter(copy.deepcopy(self.docs))

    def get_field_statistics(self, index_name, field_name, extra_query=None):
        self._record(
            "get_field_statistics", field_name=field_name,
            extra_query=extra_query, index_names=index_name,
        )
        return {"field_name": field_name, "unique_count": 1}

    def update_index_map(self, index_name, new_mapping):
        self._record("update_index_map", new_mapping=new_mapping, index_names=index_name)
        return True

    def insert_with_vectors(self, data, vectors):
        self._record("insert_with_vectors", data=data, vectors=vectors, index_names=None)
        return True

    def search_by_vector(self, query_vector, vector_field, size=10, min_score=0.0,
                         return_score=False, extra_query=None, index_names=None):
        self._record(
            "search_by_vector", query_vector=query_vector, vector_field=vector_field,
            size=size, min_score=min_score, return_score=return_score,
            extra_query=extra_query, index_names=index_names,
        )
        return copy.deepcopy(self.search_docs)


def make_legacy_interface(engine, embedding, multimodal_prefix="", check_duplicate=True,
                          is_need_llm=False):
    """`SearchDataInterface.__new__` 绕过构造器注入 fakes（不读 config、不连 ES）。"""
    from commons.simility_tools import SimilityTools
    from knowledge_interface_tools.search_index_data_interface import SearchDataInterface

    legacy = SearchDataInterface.__new__(SearchDataInterface)
    legacy.engine = engine
    legacy.embedding_tools = embedding
    legacy.simility_tools = SimilityTools(None)  # 无 LLM 的纯阈值实例
    legacy.is_need_llm = is_need_llm
    legacy.check_duplicate = check_duplicate
    legacy.all_client_category_dict = {}
    legacy.category_service_url = ""
    legacy.category_update_time_interval = 36000
    legacy.category_update_time_dict = {}
    legacy.doc_schema_field = set(LEGACY_DOC_SCHEMA_FIELD)
    legacy.multimodal_prefix = multimodal_prefix
    return legacy


def make_new_service(engine, embedding, multimodal_prefix="", **kwargs):
    """新 KnowledgeService：注入 FakeEngine 的 Repository + FakeEmbedding。"""
    from kdb.crud.repository import KnowledgeRepository
    from kdb.crud.service import KnowledgeService

    repo = KnowledgeRepository(engine=engine)
    return KnowledgeService(repo, embedding, multimodal_prefix=multimodal_prefix, **kwargs)


def build_corpus(emb):
    """回放文档集：覆盖有/无 title、synonyms、image_indexes、multimodal 占位符。"""
    def e(t):
        return emb.text2embedding(t).tolist()

    return [
        {
            "_id": "d1", "score": 3.2, "title": "如何退货", "content": "联系客服申请退货",
            "title_embedding": e("如何退货"), "content_embedding": e("联系客服申请退货"),
            "synonyms_title": ["怎么退货"], "data_type": "qa",
            "indexes": [
                {"text": "如何退货", "embedding": e("如何退货")},
                {"text": "怎么退货", "embedding": e("怎么退货")},
            ],
        },
        {
            # 无 title：qa 相似度走 content 分支；content 含多模态占位符
            "_id": "d2", "score": 2.1,
            "content": "运费说明 [multimodal_prefix]img/a.png",
            "content_embedding": e("运费说明"), "data_type": "qa",
        },
        {
            "_id": "d3", "score": 1.5, "title": "发票", "content": "发票开具流程",
            "title_embedding": e("发票"), "content_embedding": e("发票开具流程"),
            "data_type": "qa",
            "image_indexes": [{"text": "发票截图", "embedding": e("发票截图")}],
        },
    ]


@pytest.fixture()
def emb():
    return FakeEmbedding()


@pytest.fixture()
def pair(emb):
    """(legacy, new_service, old_engine, new_engine)：同一语料、同一 embedding、同一前缀。"""
    corpus_src = FakeEmbedding()
    corpus = build_corpus(corpus_src)
    old_engine = FakeEngine(docs=corpus, total=7)
    new_engine = FakeEngine(docs=copy.deepcopy(corpus), total=7)
    prefix = "https://file.example.com/"
    legacy = make_legacy_interface(old_engine, emb, multimodal_prefix=prefix)
    svc = make_new_service(new_engine, emb, multimodal_prefix=prefix)
    return legacy, svc, old_engine, new_engine
