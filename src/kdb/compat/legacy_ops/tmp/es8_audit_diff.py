"""审计用差分复现脚本（只读，不修改实现）。
用 fake client 分别驱动旧 EsSearchInterfaceOri 与新 EsSearchInterfaceES8，
对比关键方法的请求形态与返回结构。运行:
  /root/kdb-forge/.venv-es817/bin/python tmp/es8_audit_diff.py
"""
from kdb.shared.config.private_values import private_value as _private_value
import json
import sys
import types

# ---------------- 旧引擎 fake（复刻 ES7 body= 风格接口） ----------------
class FakeIndicesOld:
    def __init__(self):
        self.existing = set()
    def exists(self, index=None, **kw):
        return index in self.existing
    def get_mapping(self, index=None, **kw):
        return {index: {"mappings": {"properties": {}}}}
    def create(self, index=None, **kw):
        self.existing.add(index)
        return {"acknowledged": True}
    def put_mapping(self, index=None, **kw):
        return {"acknowledged": True}
    def refresh(self, index=None, **kw):
        return {}

class FakeESOld:
    def __init__(self, responses=None):
        self.indices = FakeIndicesOld()
        self.calls = []
        self.responses = responses or {}
    def info(self):
        return {"version": {"number": "7.10.0"}}
    def _push(self, name, kwargs):
        self.calls.append((name, kwargs))
    def _resp(self, name):
        r = self.responses.get(name)
        if isinstance(r, list):
            return r.pop(0) if r else None
        return r
    def search(self, **kwargs):
        self._push("search", kwargs)
        r = self._resp("search")
        if r is not None:
            return r
        size = kwargs.get("body", {}).get("size", 10)
        return {"hits": {"total": {"value": 10000}, "max_score": 1.0,
                         "hits": [{"_id": "x", "_score": 1.0, "_source": {}}] * size}}
    def msearch(self, body=None, **kw):
        self._push("msearch", {"body": body})
        return self._resp("msearch")
    def update(self, **kwargs):
        self._push("update", kwargs)
        return self._resp("update") or {"result": "updated"}
    def delete(self, **kwargs):
        self._push("delete", kwargs)
        return self._resp("delete") or {"result": "deleted"}
    def count(self, **kwargs):
        self._push("count", kwargs)
        return self._resp("count") or {"count": 1}
    def update_by_query(self, **kwargs):
        self._push("update_by_query", kwargs)
        return self._resp("update_by_query") or {"updated": 0, "total": 0, "version_conflicts": 0, "failures": []}
    def scroll(self, **kwargs):
        self._push("scroll", kwargs)
        return self._resp("scroll")
    def clear_scroll(self, **kwargs):
        self._push("clear_scroll", kwargs)
        return {}
    def get(self, **kwargs):
        self._push("get", kwargs)
        return self._resp("get")
    def index(self, **kwargs):
        self._push("index", kwargs)
        return self._resp("index") or {"result": "created"}


def make_old_engine(fake):
    import knowledge_interface_tools.es_search_interface as mod
    mod.Elasticsearch = lambda *a, **kw: fake
    eng = mod.EsSearchInterfaceOri(
        hosts=["http://fake:9200"], index_name="qa_default",
        vector_fields={"indexes_embedding": 3},)
    return eng


# ---------------- 新引擎 fake（ES8 named-params 风格） ----------------
class FakeClient8:
    def __init__(self, name):
        self.name = name
        self.calls = []
        self.seq = {}
        self.indices = types.SimpleNamespace(exists=lambda **kw: False)
    def _resp(self, name):
        r = self.seq.get(name)
        if isinstance(r, list):
            return r.pop(0) if r else None
        return r
    def search(self, **kwargs):
        self.calls.append(("search", kwargs))
        return self._resp("search")
    def scroll(self, **kwargs):
        self.calls.append(("scroll", kwargs))
        return self._resp("scroll")
    def clear_scroll(self, **kwargs):
        self.calls.append(("clear_scroll", kwargs))
        return {}
    def update(self, **kwargs):
        self.calls.append(("update", kwargs))
        return self._resp("update") or {"result": "updated"}
    def delete(self, **kwargs):
        self.calls.append(("delete", kwargs))
        return self._resp("delete") or {"result": "deleted"}
    def get(self, **kwargs):
        self.calls.append(("get", kwargs))
        return self._resp("get")
    def count(self, **kwargs):
        self.calls.append(("count", kwargs))
        return self._resp("count") or {"count": 1, "_shards": {"failed": 0}}
    def update_by_query(self, **kwargs):
        self.calls.append(("update_by_query", kwargs))
        return self._resp("update_by_query") or {"updated": 0, "total": 0, "version_conflicts": 0, "failures": []}


def make_new_engine(client_by_index=None):
    from knowledge_interface_tools.es8_client_router import IndexClientRouter
    from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
    clients = client_by_index or {}
    router = IndexClientRouter(
        config={
            "default_provider": "serverless",
            "providers": {"serverless": {"hosts": ["s"]}, "paas": {"hosts": ["p"]}},
            "index_routes": {},
        },
        client_factory=lambda cfg: clients.setdefault(
            cfg["hosts"][0], FakeClient8(cfg["hosts"][0])),
    )
    eng = EsSearchInterfaceES8(
        router=router, index_name="qa_default",
        vector_fields={"indexes_embedding": 3}, ensure_index=False,
    )
    return eng, clients


def hits_for(total, index="qa_one", n=2, source=None):
    return {
        "_shards": {"total": 1, "successful": 1, "failed": 0},
        "hits": {"total": {"value": total}, "hits": [
            {"_index": index, "_id": "%s_%d" % (index, i), "_score": 1.0,
             "_source": source or {"title": "t%d" % i}}
            for i in range(n)]},
    }


def main():
    print("=" * 72)
    print("A. agg_terms 返回结构差异（上层 list_file_names 消费 sub.by_type）")
    print("=" * 72)
    bucket_raw = {
        "key": "a.docx", "doc_count": 5,
        "by_type": {"doc_count_error_upper_bound": 0, "sum_other_doc_count": 0,
                    "buckets": [{"key": "qa", "doc_count": 3}, {"key": "doc", "doc_count": 2}]},
    }
    agg_resp = {"aggregations": {"grp": {"buckets": [bucket_raw]}}, "hits": {"total": 1, "hits": []}}
    q = {"bool": {"must": [{"term": {"del_flag": 0}}]}}

    fake_old = FakeESOld({"search": agg_resp})
    old = make_old_engine(fake_old)
    old_out = old.agg_terms("qa_default", q, "ext_info.from_file_name.keyword",
                            sub_aggs={"by_type": {"terms": {"field": "data_type"}}})
    print("old agg_terms ->", json.dumps(old_out, ensure_ascii=False))

    eng, clients = make_new_engine()
    clients["s"].seq["search"] = [dict(agg_resp)]
    new_out = eng.agg_terms("qa_default", q, "ext_info.from_file_name.keyword",
                            sub_aggs={"by_type": {"terms": {"field": "data_type"}}})
    print("new agg_terms ->", json.dumps(new_out, ensure_ascii=False))
    type_count = [{"value": b["key"], "type_count": (b.get("sub") or {}).get("by_type", {})}
                  for b in new_out]
    print("list_file_names 消费 new 结果 ->", json.dumps(type_count, ensure_ascii=False))

    print()
    print("=" * 72)
    print("B. search_after：新引擎是否产出文档")
    print("=" * 72)
    fake_old2 = FakeESOld()
    fake_old2.responses["search"] = [
        {"hits": {"total": {"value": 2}, "hits": [
            {"_id": "1", "_score": 1.0, "sort": [1], "_source": {"title": "a"}},
            {"_id": "2", "_score": 1.0, "sort": [2], "_source": {"title": "b"}}]}},
        {"hits": {"total": {"value": 2}, "hits": []}},
    ]
    old2 = make_old_engine(fake_old2)
    old_after = list(old2.search_after({"query": "x"}, batch_size=2, index_names="qa_default"))
    print("old search_after 文档数:", len(old_after))

    eng2, clients2 = make_new_engine()
    clients2["s"].seq["search"] = [
        {"_shards": {"total": 1, "successful": 1, "failed": 0},
         "hits": {"total": {"value": 2}, "hits": [
             {"_id": "1", "_score": 1.0, "sort": [1], "_source": {"title": "a"}},
             {"_id": "2", "_score": 1.0, "sort": [2], "_source": {"title": "b"}}]}},
        {"_shards": {"total": 1, "successful": 1, "failed": 0},
         "hits": {"total": {"value": 2}, "hits": []}},
    ]
    new_after = list(eng2.search_after({"query": "x"}, batch_size=2, index_names="qa_default"))
    print("new search_after 文档数:", len(new_after))
    print("new search_after 发出的 search 次数:", len([c for c in clients2['s'].calls if c[0]=='search']))

    print()
    print("=" * 72)
    print("C. search_multi_by_page / _search_with_shard_check 大 size 处理")
    print("=" * 72)
    fake_old3 = FakeESOld()
    old3 = make_old_engine(fake_old3)
    old3._search_with_shard_check("qa_default", {"query": {"match_all": {}}, "size": 10000})
    old_sizes = [c[1]["body"]["size"] for c in fake_old3.calls if c[0] == "search"]
    print("old 拆批请求 sizes:", old_sizes[:8], "… 共", len(old_sizes), "批")

    eng3, clients3 = make_new_engine()
    fake_old3.responses = {}
    clients3["s"].seq["search"] = [
        {"_shards": {"total": 1, "successful": 1, "failed": 0},
         "hits": {"total": {"value": 0}, "hits": []}},
    ]
    eng3.search_multi_by_page({}, index_names="qa_default", size=10000)
    new_sizes = [c[1]["size"] for c in clients3["s"].calls if c[0] == "search"]
    print("new 单请求 sizes:", new_sizes)

    print()
    print("=" * 72)
    print("D. 持续分片失败时的异常语义（search / search_multi）")
    print("=" * 72)
    import time as _t
    import knowledge_interface_tools.es8_search_interface as es8mod
    _orig_sleep = es8mod.time.sleep
    es8mod.time.sleep = lambda *a: None

    fake_old4 = FakeESOld()
    old4 = make_old_engine(fake_old4)
    fake_old4.responses["search"] = {"hits": {"total": {"value": 0}, "hits": []}}
    print("old search(异常路径) -> 抛错? (fake 抛错):", end=" ")
    class Boom(Exception): pass
    def boom_search(**kw): raise Boom("es down")
    fake_old4.search = boom_search
    try:
        r = old4.search({"query": "x"})
        print("返回", r)
    except Exception as e:
        print("抛出", type(e).__name__)

    eng4, clients4 = make_new_engine()
    clients4["s"].seq["search"] = [{"_shards": {"total": 1, "successful": 0, "failed": 1,
                                     "failures": [{"reason": {"type": 'task_cancelled_exception'}}]}}] * 3
    try:
        r = eng4.search({"query": "x"}, index_names="qa_default")
        print("new search(分片失败x3) -> 返回", r)
    except Exception as e:
        print("new search(分片失败x3) -> 抛出", type(e).__name__, str(e)[:60])

    clients4["s"].seq["search"] = [{"_shards": {"total": 1, "successful": 0, "failed": 1}}] * 3
    try:
        r = eng4.search_multi({"query": "x"}, index_names="qa_default")
        print("new search_multi(分片失败x3) -> 返回", r)
    except Exception as e:
        print("new search_multi(分片失败x3) -> 抛出", type(e).__name__)
    es8mod.time.sleep = _orig_sleep

    print()
    print("=" * 72)
    print("E. CRUD 结果判定差异（noop / not_found）")
    print("=" * 72)
    fake_old5 = FakeESOld({"update": {"result": "noop"}, "delete": {"result": "not_found"}})
    old5 = make_old_engine(fake_old5)
    print("old insert(noop)->", old5.insert({"_id": "d1", "title": "x"}, index_names="qa_default"),
          "| old update(noop)->", old5.update("d1", {"title": "y"}),
          "| old delete(not_found)->", old5.delete("d1"))

    eng5, clients5 = make_new_engine()
    clients5["s"].seq["update"] = [{"result": "noop"}, {"result": "noop"}]
    clients5["s"].seq["delete"] = [{"result": "not_found"}]
    print("new insert(noop)->", eng5.insert({"_id": "d1", "title": "x"}, index_names="qa_default"),
          "| new update(noop)->", eng5.update("d1", {"title": "y"}),
          "| new delete(not_found)->", eng5.delete("d1", index_names="qa_default"))

    print()
    print("=" * 72)
    print("F. scroll 带 vector 查询：旧引擎带 script_score，新引擎静默丢弃向量")
    print("=" * 72)
    fake_old6 = FakeESOld()
    fake_old6.responses["search"] = {"_scroll_id": "s1", "hits": {"total": {"value": 0}, "hits": []}}
    old6 = make_old_engine(fake_old6)
    list(old6.scroll_search({"query": "x", "vector": {"value": [1, 0, 0]}}, batch_size=2, index_names="qa_default"))
    old_body = [c[1]["body"] for c in fake_old6.calls if c[0] == "search"][0]
    print("old scroll body 含 script_score:", "script_score" in json.dumps(old_body))

    eng6, clients6 = make_new_engine()
    clients6["s"].seq["search"] = [
        {"_shards": {"total": 1, "successful": 1, "failed": 0}, "_scroll_id": "s1",
         "hits": {"total": {"value": 0}, "hits": []}},
    ]
    list(eng6.scroll_search({"query": "x", "vector": {"value": [1, 0, 0]}}, batch_size=2, index_names="qa_default"))
    new_query = [c[1]["query"] for c in clients6["s"].calls if c[0] == "search"][0]
    print("new scroll query 含 knn:", "knn" in json.dumps(new_query))

    print()
    print("=" * 72)
    print("G. 多索引 dual 检索 total 语义")
    print("=" * 72)
    # 旧: 每个子请求 total 取 max（4 个子请求）
    msearch_resp = {"responses": [
        hits_for(40, "qa"), hits_for(20, "qa"),   # qa bm25 / qa vector
        hits_for(10, "qb"), hits_for(30, "qb"),   # qb bm25 / qb vector
    ]}
    fake_old7 = FakeESOld({"msearch": msearch_resp})
    old7 = make_old_engine(fake_old7)
    docs7, total7 = old7.search_multi({"query": "x", "vector": {"value": [1, 0, 0]}},
                                      index_names=["qa", "qb"], size=10)
    print("old 多索引 dual total:", total7, "文档数:", len(docs7))

    eng7, clients7 = make_new_engine()
    clients7["s"].seq["search"] = [
        hits_for(40, "qa"), hits_for(20, "qa"),
        hits_for(10, "qb"), hits_for(30, "qb"),
    ]
    docs7n, total7n = eng7.search_multi({"query": "x", "vector": {"value": [1, 0, 0]}},
                                        index_names=["qa", "qb"], size=10)
    print("new 多索引 dual total:", total7n, "文档数:", len(docs7n))

    print()
    print("=" * 72)
    print("H. search size>10 时向量路候选上限（旧=全量 script_score，新= k=10）")
    print("=" * 72)
    fake_old8 = FakeESOld()
    old8 = make_old_engine(fake_old8)
    fake_old8.responses["search"] = hits_for(5, "qa_default", n=0)
    old8.search({"query": "x", "vector": {"value": [1, 0, 0]}}, size=20)
    old8_body = fake_old8.calls[-1][1]["body"]
    print("old search body 含 script_score:", "script_score" in json.dumps(old8_body))

    eng8, clients8 = make_new_engine()
    clients8["s"].seq["search"] = [
        {"_shards": {"total": 1, "successful": 1, "failed": 0}, "hits": {"total": {"value": 0}, "hits": []}},
    ]
    eng8.search({"query": "x", "vector": {"value": [1, 0, 0]}}, size=20, index_names="qa_default")
    knn_clause = clients8["s"].calls[-1][1]["query"]["bool"]["should"][-1]
    print("new search knn 子句:", json.dumps(knn_clause, ensure_ascii=False))


if __name__ == "__main__":
    main()
