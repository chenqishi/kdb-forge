"""真实 ES 只读探测（不创建、不写入、不删除任何索引/文档）。
只做 GET /（version）、_cat/indices、indices.exists 等只读调用。
"""
import json

def main():
    cfg = json.load(open("/root/kdb-forge/config/config_es_runtime.local.json"))
    from elasticsearch import Elasticsearch

    def probe(name, provider_cfg, extra_indices=()):
        hosts = provider_cfg["hosts"]
        es = Elasticsearch(
            hosts=hosts,
            request_timeout=provider_cfg.get("request_timeout", 30),
            verify_certs=provider_cfg.get("verify_certs", True),
            basic_auth=(provider_cfg["username"], provider_cfg["password"]),
        )
        try:
            info = es.info()
            version = info["version"]["number"]
        except Exception as e:
            print(f"[{name}] info FAILED: {type(e).__name__}: {str(e)[:120]}")
            return
        try:
            cat = es.cat.indices(format="json")
            names = sorted(i["index"] for i in cat if "index" in i)
        except Exception as e:
            print(f"[{name}] cat.indices FAILED: {type(e).__name__}: {str(e)[:120]}")
            names = None
        line = f"[{name}] version={version} indices={len(names) if names is not None else 'N/A'}"
        if names is not None:
            business = [n for n in names if not n.startswith((".", "_", "test"))]
            line += f" business_indexes={len(business)}"
        print(line)
        for idx in extra_indices:
            try:
                print(f"  exists({idx}) =", es.indices.exists(index=idx))
            except Exception as e:
                print(f"  exists({idx}) FAILED: {type(e).__name__}")
        try:
            es.close()
        except Exception:
            pass

    probe("serverless (new)", cfg["providers"]["serverless"], ("test_case",))
    probe("paas (new)", cfg["providers"]["paas"], ("test_case",))

    # 旧 ES7 serverless（旧配置），只读探测版本
    try:
        old = json.load(open("config/config_es_engine.json"))
        probe("old-serverless (ES7)", old, ())
    except Exception as e:
        print("old config probe skipped:", e)

if __name__ == "__main__":
    main()
