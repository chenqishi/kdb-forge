"""真实 ES8.17 集群只读验证（不写入、不删除、不建索引、不改 mapping）。
使用 EsSearchInterfaceES8 真实配置与真实 client，对已迁移的 staging 索引做只读检索验证。
"""
import json
import math
import random

CFG_PATH = "/root/kdb-forge/config/config_es_runtime.local.json"


def unit_vector(dim=1024):
    v = [random.gauss(0, 1) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def main():
    cfg = json.load(open(CFG_PATH))
    from elasticsearch import Elasticsearch
    from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8

    sl = cfg["providers"]["serverless"]
    raw = Elasticsearch(hosts=sl["hosts"], request_timeout=30,
                        verify_certs=sl.get("verify_certs", True),
                        basic_auth=(sl["username"], sl["password"]))

    target = "individual_20__v817_initial_20260930"
    print("== 1. mapping 检查 (read-only) ==")
    m = raw.indices.get_mapping(index=target)[target]["mappings"]["properties"]
    for f in ("title_embedding", "content_embedding"):
        print(f"  {f}:", json.dumps(m.get(f), ensure_ascii=False))
    for nested in ("indexes", "image_indexes"):
        emb = m.get(nested, {}).get("properties", {}).get("embedding", {})
        print(f"  {nested}.embedding:", json.dumps(emb, ensure_ascii=False))
    print("  del_flag:", json.dumps(m.get("del_flag"), ensure_ascii=False))
    print("  analyzer title:", json.dumps(m.get("title", {}).get("analyzer"), ensure_ascii=False))
    print("  _count:", raw.count(index=target)["count"])
    raw.close()

    print()
    print("== 2. ES8 引擎实例化（ensure_index=True 对已迁移索引只读守卫） ==")
    engine = EsSearchInterfaceES8(
        config_path=CFG_PATH,
        index_name=target,
        ensure_index=True,
    )
    print("  实例化 OK，recall_mode =", engine.recall_mode, "| 默认索引 =", engine.index_name)

    print()
    print("== 3. search_by_vector：native nested KNN 真实调用 ==")
    try:
        res = engine.search_by_vector(unit_vector(), "indexes_embedding", size=5,
                                      return_score=True, index_names=target)
        print("  返回条数:", len(res))
        for doc, score in res[:3]:
            print("   -", doc.get("_id"), "score=%.4f" % score, "title=", str(doc.get("title"))[:40])
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])

    print()
    print("== 4. search_multi dual（真实 BM25 + native KNN 双路） ==")
    try:
        docs, total = engine.search_multi(
            {"query": "发货", "vector": {"value": unit_vector()}},
            index_names=target, size=10)
        print("  docs=", len(docs), "total=", total)
        for d in docs[:3]:
            idx = d.get("indexes") or []
            with_emb = sum(1 for x in idx if isinstance(x, dict) and x.get("embedding"))
            print("   -", d.get("_id"), "| indexes=", len(idx), "带embedding=", with_emb,
                  "| title=", str(d.get("title"))[:40])
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])

    print()
    print("== 5. search_multi_by_page（BM25 分页，web_search 路径） ==")
    try:
        docs, total = engine.search_multi_by_page(
            {"query": "发货", "vector": {"value": unit_vector()}},
            index_names=target, size=5, page_num=1)
        print("  docs=", len(docs), "total=", total, "| 首条 title=",
              str(docs[0].get("title"))[:40] if docs else None)
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])

    print()
    print("== 6. agg_terms（子聚合真实返回结构） ==")
    try:
        out = engine.agg_terms(
            target, {"bool": {"must": [{"term": {"del_flag": 0}}]}},
            "ext_info.from_file_name.keyword", size=3,
            sub_aggs={"by_type": {"terms": {"field": "data_type", "size": 10}}})
        print("  返回条目:", json.dumps(out, ensure_ascii=False)[:600])
        print("  每条含 'sub' 键:", all("sub" in b for b in out))
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])

    print()
    print("== 7. search_after 真实行为 ==")
    try:
        docs = list(engine.search_after({"query": "发货"}, batch_size=10, index_names=target))
        print("  产出文档数:", len(docs), "（旧引擎同条件应产出非零）")
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])

    print()
    print("== 8. count_by_query / get_unique_values（只读） ==")
    try:
        q = {"bool": {"must": [{"term": {"del_flag": 0}}]}}
        print("  count(del_flag=0):", engine.count_by_query(target, q))
        vals = engine.get_unique_values(target, "data_type", size=10)
        print("  data_type unique:", vals)
    except Exception as e:
        print("  FAILED:", type(e).__name__, str(e)[:200])

    engine.close()


if __name__ == "__main__":
    main()
