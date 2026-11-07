"""Bounded localhost verification after the expressly authorized local restart."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/from_type_count_live_20261008.py')
import hashlib
import json
import os
import time
from pathlib import Path

import requests

from es817_independent_query_compare_20261005 import HISTORY, make_clients, read_es
from knowledge_interface_tools.es_count_utils import complete_count

ROOT = Path(__legacy_source_file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8003"
OUTPUT = ROOT / "docs/reviews/from_type_count_local_activation_20261008/live_running_http.json"


def run():
    evidence = {"captured_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "mode": "real running localhost HTTP, not ASGI", "base_url": BASE_URL,
                "count_cases": [], "controls": [], "retrieval_smoke": [],
                "es_writes": 0, "implementation_sha256": {}}
    for name in ("knowledge_database_search_service/src/knowledge_database_search_es.py",
                 "knowledge_interface_tools/search_index_data_interface.py",
                 "knowledge_interface_tools/es_search_interface.py",
                 "knowledge_interface_tools/es8_search_interface.py",
                 "knowledge_interface_tools/es_count_utils.py"):
        evidence["implementation_sha256"][name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    clients = {}
    session = requests.Session()
    try:
        response = session.get(BASE_URL + "/openapi.json", timeout=15)
        response.raise_for_status()
        paths = response.json()["paths"]
        evidence["openapi"] = {"http_status": response.status_code,
                               "count_route_loaded": "post" in paths.get("/get_from_type_count", {}),
                               "original_routes_present": all(name in paths for name in ("/search", "/web_search", "/insert", "/delete"))}
        clients = make_clients()
        parameters = [({}, "default"), ({"from_type": "chat_auto"}, "explicit"),
                      ({"from_type": "document"}, "document"),
                      ({"from_type": "__count_readonly_absent_20261008__"}, "unmatched"),
                      ({"start": "2026-09-01 00:00:00", "end": "2026-10-08 23:59:59"}, "window"),
                      ({"start": "2026-09-01 00:00:00"}, "single_bound")]
        for index, provider in (("mercado_local", "serverless"), ("payoneer_olive", "paas")):
            read_es(clients[provider], "HEAD", "/" + index)
            for params, label in parameters:
                payload = dict(params, index_name=index)
                if label == "window":
                    payload["indexName"] = payload.pop("index_name")
                filters = [{"term": {"quality_level": "high"}},
                           {"term": {"from_type": params.get("from_type", "chat_auto")}}]
                if params.get("start") and params.get("end"):
                    filters.append({"range": {"insert_time": {"gte": params["start"], "lte": params["end"]}}})
                native = complete_count(read_es(clients[provider], "POST", "/" + index + "/_count",
                                                {"query": {"bool": {"filter": filters}}}))
                reply = session.post(BASE_URL + "/get_from_type_count", json=payload, timeout=60)
                result = reply.json()
                evidence["count_cases"].append({"index": index, "provider": provider, "case": label,
                    "request": payload, "http_status": reply.status_code, "response": result,
                    "native_reference": native, "passed": reply.status_code == 200 and
                    result == {"success": True, "count": native, "message": ""}})
                time.sleep(0.15)
            for endpoint, payload in (("/web_search", {"text": "", "index_names": index,
                    "page_size": 1, "page_num": 1, "score_threshold": 0}),
                    ("/search", {"text": HISTORY[index][0][0], "index_names": index,
                    "search_type": "qa", "top_k": 2, "score_threshold": -1, "use_synonyms": True,
                    "condition_dicts": [{"audit_result": [1, 2], "data_type": "qa"}]})):
                reply = session.post(BASE_URL + endpoint, json=payload, timeout=90)
                result = reply.json()
                hits = result.get("results", [])
                ids = [hit.get("id") or hit.get("_id") for hit in hits]
                passed = reply.status_code == 200 and bool(hits) and all(ids) and not result.get("error")
                evidence["retrieval_smoke"].append({"index": index, "endpoint": endpoint,
                    "http_status": reply.status_code, "returned": len(hits), "ids": ids,
                    "scores": [hit.get("score") for hit in hits], "total_count": result.get("total_count"),
                    "passed": passed, "proof_scope": "existing entry and nonempty identity smoke; not ranking equivalence"})
        for payload in ({}, {"index_name": ""}, {"index_name": None}):
            reply = session.post(BASE_URL + "/get_from_type_count", json=payload, timeout=15)
            evidence["controls"].append({"request": payload, "http_status": reply.status_code,
                "passed": reply.status_code == 200 and reply.json() == {"success": True, "count": 0, "message": ""}})
        for payload in ({"index_name": "mercado_local", "from_type": None},
                        {"index_name": "mercado_local", "start": "2026-09-01"},
                        {"index_name": "mercado_local", "indexName": "payoneer_olive"}):
            reply = session.post(BASE_URL + "/get_from_type_count", json=payload, timeout=15)
            evidence["controls"].append({"request": payload, "http_status": reply.status_code,
                                         "passed": reply.status_code == 422})
        evidence["all_passed"] = (all(evidence["openapi"].values()) and
            all(row["passed"] for group in ("count_cases", "controls", "retrieval_smoke") for row in evidence[group]))
    except Exception as exc:
        evidence["error_type"] = type(exc).__name__
        evidence["all_passed"] = False
    finally:
        session.close()
        for client in clients.values():
            client.session.close()
    return evidence


def main():
    if OUTPUT.exists():
        raise FileExistsError("Refusing to overwrite previous live evidence")
    evidence = run()
    with OUTPUT.open("x") as stream:
        json.dump(evidence, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    os.chmod(OUTPUT, 0o600)
    print(json.dumps({"passed": evidence["all_passed"], "count_cases": len(evidence["count_cases"]),
        "controls": len(evidence["controls"]), "retrieval_smoke": len(evidence["retrieval_smoke"]),
        "evidence": str(OUTPUT)}, ensure_ascii=False))
    if not evidence["all_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
