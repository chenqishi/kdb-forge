"""Bounded new-only source and inner-hit diagnostic; never fixes engine code."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/main_es817_response_diagnose_20261008.py')
import copy
import hashlib
import json
from pathlib import Path

from commons.es_http_client import EsHttpClient
from es817_independent_query_compare_20261005 import read_es
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8

ROOT = Path(__legacy_source_file__).resolve().parents[1]
OUT = ROOT / "docs/reviews/main_es817_expanded_20261008_run2"


def qualify_inner_sources(query):
    result = copy.deepcopy(query)
    pending = [result]
    while pending:
        node = pending.pop()
        if isinstance(node, dict):
            nested = node.get("nested")
            if isinstance(nested, dict) and nested.get("inner_hits"):
                source = nested["inner_hits"]["_source"]
                source["includes"] = [nested["path"] + "." + field for field in source["includes"]]
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return result


def main():
    path = OUT / "response_diagnosis.json"
    if path.exists():
        raise ValueError("preserve existing diagnostic evidence")
    evidence = json.loads((OUT / "evidence.json").read_text())
    selected = [r for r in evidence["rows"] if r["stage"] == 1 and r["source_counts"].get("missing_synonym_rerank_input")]
    ids_by_index = {}
    for row in selected:
        for identifier in row["candidate_ids"]:
            index, docid = identifier.split(":", 1)
            ids_by_index.setdefault(index, set()).add(docid)
    olive = next(r for r in evidence["rows"] if r["stage"] == 1 and r["platform"] == "payoneer_olive" and r["candidates"])
    index, identifier = olive["candidate_ids"][0].split(":", 1)
    ids_by_index[index] = {identifier}
    assert len(ids_by_index) <= 3 and all(len(ids) <= 40 for ids in ids_by_index.values())
    config = json.loads((ROOT / "config/config_es_engine_es817.old.local.json").read_text())
    clients = {provider: EsHttpClient(cfg["hosts"],cfg.get("username"),cfg.get("password"),timeout=15)
               for provider,cfg in config["providers"].items()}
    result = {"new_only": True, "location": "sg", "not_included_in_main_latency": True,
              "reads": 0, "documents_checked": 0, "missing_synonym_documents": [], "inner_hits_ab": []}
    sample = {}
    try:
        for provider, client in clients.items():
            version = read_es(client,"GET","/")["version"]["number"]
            result["reads"] += 1
            assert version.startswith("8.17.")
        for index, ids in ids_by_index.items():
            provider = "serverless" if index.startswith("mercado_local") else "paas"
            response = read_es(clients[provider],"POST","/"+index+"/_mget",{"ids":sorted(ids)})
            result["reads"] += 1
            for doc in response["docs"]:
                assert doc.get("found") and not doc.get("error")
                result["documents_checked"] += 1
                source = doc["_source"]
                entries = source.get("indexes") or []
                wanted = set(source.get("synonyms_title") or [])
                matching = [entry for entry in entries if entry.get("text") in wanted and len(entry.get("embedding") or [])==1024]
                if wanted and not matching:
                    result["missing_synonym_documents"].append({"index":index,"id":doc["_id"],
                        "synonym_count":len(wanted),"indexes_count":len(entries),
                        "text_overlap":sum(entry.get("text") in wanted for entry in entries),
                        "index_vectors": [len(entry.get("embedding") or []) for entry in entries],
                        "root_title_dims":len(source.get("title_embedding") or []),
                        "root_content_dims":len(source.get("content_embedding") or []),
                        "synonym_sha256": sorted(hashlib.sha256(text.encode()).hexdigest() for text in wanted),
                        "index_text_sha256": [hashlib.sha256((entry.get("text") or "").encode()).hexdigest() for entry in entries]})
                if provider not in sample and entries and len(entries[0].get("embedding") or [])==1024:
                    sample[provider] = (index,entries[0]["embedding"])
        builder = EsSearchInterfaceES8.__new__(EsSearchInterfaceES8)
        builder.vector_fields = {"indexes_embedding":1024}
        for provider, (index, vector) in sample.items():
            query = builder._build_search_query({"vector":{"value":vector},"attribute":[{"data_type":"qa"}]},
                include_text=False,include_vector=True,vector_k=5,with_inner_hits=True)
            for label, dsl in (("actual_relative",query),("diagnostic_qualified",qualify_inner_sources(query))):
                response = read_es(clients[provider],"POST","/"+index+"/_search",{"query":dsl,"size":5})
                result["reads"] += 1
                inner = [hit for doc in response["hits"]["hits"] for section in (doc.get("inner_hits") or {}).values()
                         for hit in section.get("hits",{}).get("hits",[])]
                result["inner_hits_ab"].append({"provider":provider,"index":index,"variant":label,
                    "shards":response.get("_shards"),"hits":len(response["hits"]["hits"]),"inner_hits":len(inner),
                    "empty_sources":sum(not hit.get("_source") for hit in inner),
                    "dimensions":[len((hit.get("_source") or {}).get("embedding") or []) for hit in inner],
                    "keys":[sorted((hit.get("_source") or {}).keys()) for hit in inner]})
    finally:
        for client in clients.values():
            client.session.close()
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n")
    path.chmod(0o600)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__ == "__main__":
    main()
