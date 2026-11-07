#!/usr/bin/env python3
"""Bounded live ES7 / active SG ES8 metadata recheck; no source content.

Exactly fourteen size=0 queries plus eight explicit document metadata reads.
Old connection is SHA-checked against the actual Shenzhen configuration over SSH.
Target providers are loaded from the currently running 8012 reader configuration.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import warnings

sys.path.insert(0, str(Path(__file__).resolve().parent))
from compare_legacy_search_http import now, read_json, write_json
from kdb.es.client_router import IndexClientRouter

spec = importlib.util.spec_from_file_location("legacy_metadata_reader", "/tmp/kdb_key5_freshness_metadata_20261004.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
INDICES = ["mercado", "mercado_local", "wayfair", "payoneer", "payoneer_olive",
           "mercado_local_mercado_local_admin", "wayfair_wayfair_test2"]
FIELDS = ["insert_time", "update_time", "del_flag"]
IDS = {"mercado": ["e16966b70a800288d4ee16e31fbb47e7", "f71a7c1c1641740c57fc3c4bdc5bf60a", "bbc2ea86384aa78914ffa35f068c77bc"],
       "payoneer_olive": ["32599c4c3eb6bf6faa62d77bc9490293"]}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def fingerprint(config):
    return {"host_sha256": digest(config.get("hosts") or config.get("host")),
            "auth_sha256": digest({"username": config.get("username"), "password": config.get("password"), "api_key": config.get("api_key")})}


def verify_source_remote(local):
    meta = {"started_at_utc": now(), "ssh_alias": "shenzhen-120",
            "remote_actual_config": "/root/dify/knowledge_database_builder/config/config_es_engine.json"}
    code = """import json,hashlib
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
d=json.load(open('/root/dify/knowledge_database_builder/config/config_es_engine.json'))
print(json.dumps({'host_sha256':digest(d.get('hosts') or d.get('host')),'auth_sha256':digest({'username':d.get('username'),'password':d.get('password'),'api_key':d.get('api_key')})}))
"""
    result = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "shenzhen-120", "python3", "-"],
                            input=code, capture_output=True, text=True, timeout=30)
    meta.update(finished_at_utc=now(), exit_code=result.returncode)
    if result.returncode:
        meta.update(verified=False, stderr_sha256=hashlib.sha256(result.stderr.encode()).hexdigest())
        return meta
    remote = json.loads(result.stdout)
    wanted = fingerprint(local)
    meta.update(host_sha_match=remote["host_sha256"] == wanted["host_sha256"],
                auth_sha_match=remote["auth_sha256"] == wanted["auth_sha256"])
    meta["verified"] = meta["host_sha_match"] and meta["auth_sha_match"]
    return meta


def active_target():
    pid = int(subprocess.run(["systemctl", "show", "kdb-forge-retrieval.service", "--property", "MainPID", "--value"],
                             check=True, capture_output=True, text=True).stdout.strip())
    if pid <= 0:
        raise RuntimeError("retrieval_service_no_active_mainpid")
    env = dict(item.split("=", 1) for item in Path(f"/proc/{pid}/environ").read_bytes().decode().split("\0") if "=" in item)
    reader = Path(env.get("KDB_FORGE_CONFIG", "config/config_search_runtime.local.json")).resolve()
    reader_raw = reader.read_bytes()
    engine = Path(json.loads(reader_raw)["engine_config_path"]).resolve()
    engine_raw = engine.read_bytes()
    config = json.loads(engine_raw)
    if str(config.get("es_version")) != "8.17":
        raise RuntimeError("active_reader_engine_not_es817")
    binding = {"reader_mainpid": pid, "reader_config": str(reader), "engine_config": str(engine),
               "reader_config_sha256": hashlib.sha256(reader_raw).hexdigest(),
               "engine_config_sha256": hashlib.sha256(engine_raw).hexdigest()}
    shared = Path("config/config_es_runtime.local.json")
    if shared.exists():
        shared_cfg = read_json(shared)
        binding["shared_engine_config_same"] = hashlib.sha256(shared.read_bytes()).hexdigest() == binding["engine_config_sha256"]
        binding["shared_provider_connections_same"] = {name: fingerprint(value) == fingerprint(shared_cfg.get("providers", {}).get(name, {}))
                                                        for name, value in config["providers"].items()}
    return config, binding


def metadata(endpoint, index):
    payload = {"size": 0, "track_total_hits": True, "query": {"match_all": {}},
        "aggs": {"max_update_time": {"max": {"field": "update_time"}},
                 "max_insert_time": {"max": {"field": "insert_time"}},
                 "del_flag_0": {"filter": {"term": {"del_flag": 0}}},
                 "del_flag_1": {"filter": {"term": {"del_flag": 1}}},
                 "del_flag_missing": {"filter": {"bool": {"must_not": {"exists": {"field": "del_flag"}}}}},
                 "del_flag_values": {"terms": {"field": "del_flag", "size": 20}}}}
    request, body = endpoint.request("POST", f"/{index}/_search", payload)
    row = {"index": index, "request": request, "complete": False}
    if body is None:
        return row
    info = body.get("hits", {}).get("total")
    total = info.get("value") if isinstance(info, dict) else info
    relation = info.get("relation") if isinstance(info, dict) else "eq"
    shards = body.get("_shards", {})
    row.update(count=total, count_relation=relation, aggregations=body.get("aggregations", {}))
    row["complete"] = (body.get("timed_out") is False and shards.get("failed") == 0
        and shards.get("successful") == shards.get("total") and relation == "eq" and isinstance(total, int))
    return row


def doc_metadata(endpoint, index, ids):
    payload = {"docs": [{"_id": ident, "_source": FIELDS} for ident in ids]}
    request, body = endpoint.request("POST", f"/{index}/_mget", payload)
    row = {"index": index, "request": request, "requested_ids": ids, "complete": False, "documents": []}
    if body is None:
        return row
    for doc in body.get("docs", []):
        clean = {key: doc[key] for key in ("_id", "_index", "_version", "found") if key in doc}
        source = doc.get("_source", {})
        if any(field not in FIELDS for field in source):
            raise RuntimeError("mget_returned_out_of_scope_source_fields")
        clean["metadata"] = {field: source[field] for field in FIELDS if field in source}
        if doc.get("error"):
            clean["error_type"] = doc["error"].get("type", "mget_item_error")
        row["documents"].append(clean)
    actual = [doc.get("_id") for doc in row["documents"]]
    row["complete"] = len(actual) == len(ids) and set(actual) == set(ids) and all("error_type" not in doc for doc in row["documents"])
    return row


def run(args):
    source_cfg = read_json(args.source_config)
    target_cfg, binding = active_target()
    router = IndexClientRouter(config=target_cfg)
    providers = {index: router.resolve_provider(index) for index in INDICES}
    report = {"schema": "key5-live-recheck-v1", "started_at_utc": now(), "scope": INDICES,
        "read_only": True, "status": "prepared", "source_config": str(args.source_config),
        "target_config_binding": binding, "provider_by_index": providers,
        "size0_requests_expected": 14, "mget_documents_expected": 8,
        "source_fields_allowed": FIELDS, "source_target_transaction_snapshot": False,
        "full_freshness_proven": False, "continuous_synchronization_proven": False,
        "limitations": ["Separate live requests, not a cross-cluster transaction snapshot.",
            "Equal counts, date maxima and del_flag aggregates do not prove all document contents or continuous synchronization.",
            "Only four named IDs are checked; document versions are independent per cluster and are not required equal.",
            "Date values retain original ES epoch/value_as_string; naive application timestamps are not assigned a timezone.",
            "Historical October 4 observations and an unlocated handoff claim are not used as current evidence."],
        "indices": {}, "specified_ids": {}}
    write_json(args.report, report)
    if not args.execute:
        print(json.dumps({"status": "prepared", "network_requests": 0}))
        return 0
    report["source_remote_verification"] = verify_source_remote(source_cfg)
    write_json(args.report, report)
    if not report["source_remote_verification"]["verified"]:
        raise RuntimeError("remote_actual_source_config_sha_mismatch")
    old = base.Endpoint("legacy_es7", source_cfg)
    targets = {name: base.Endpoint(name, cfg) for name, cfg in target_cfg["providers"].items()}
    report["status"] = "running"
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        for index in INDICES:
            old_future = pool.submit(metadata, old, index)
            new_future = pool.submit(metadata, targets[providers[index]], index)
            a, b = old_future.result(), new_future.result()
            complete = a["complete"] and b["complete"]
            comparison = {"both_complete": complete, "source_count": a.get("count"), "target_count": b.get("count")}
            if complete:
                comparison.update(target_minus_source_count=b["count"] - a["count"],
                    count_equal=a["count"] == b["count"],
                    update_time_max_equal=a["aggregations"]["max_update_time"] == b["aggregations"]["max_update_time"],
                    insert_time_max_equal=a["aggregations"]["max_insert_time"] == b["aggregations"]["max_insert_time"],
                    del_flag_equal=all(a["aggregations"][key] == b["aggregations"][key] for key in
                        ("del_flag_0", "del_flag_1", "del_flag_missing", "del_flag_values")))
            report["indices"][index] = {"provider": providers[index], "source": a, "target": b, "comparison": comparison}
            write_json(args.report, report)
            print(json.dumps({"index": index, **comparison}), flush=True)
        for index, ids in IDS.items():
            old_future = pool.submit(doc_metadata, old, index, ids)
            new_future = pool.submit(doc_metadata, targets[providers[index]], index, ids)
            a, b = old_future.result(), new_future.result()
            aa = {doc["_id"]: doc for doc in a["documents"]}
            bb = {doc["_id"]: doc for doc in b["documents"]}
            comparisons = []
            for ident in ids:
                source, target = aa.get(ident, {}), bb.get(ident, {})
                comparisons.append({"id": ident, "source_found": source.get("found"), "target_found": target.get("found"),
                    "both_found": source.get("found") is True and target.get("found") is True,
                    "metadata_equal": source.get("found") is True and target.get("found") is True and source.get("metadata") == target.get("metadata"),
                    "del_flag_equal": source.get("found") is True and target.get("found") is True
                        and ("del_flag" in source["metadata"]) == ("del_flag" in target["metadata"])
                        and source["metadata"].get("del_flag") == target["metadata"].get("del_flag")})
            report["specified_ids"][index] = {"source": a, "target": b, "comparisons": comparisons,
                                             "both_mget_complete": a["complete"] and b["complete"]}
            write_json(args.report, report)
            print(json.dumps({"specified_index": index, "comparisons": comparisons}), flush=True)
    current_config, current_binding = active_target()
    report["target_config_unchanged_during_reads"] = current_binding["reader_mainpid"] == binding["reader_mainpid"] and current_binding["reader_config_sha256"] == binding["reader_config_sha256"] and current_binding["engine_config_sha256"] == binding["engine_config_sha256"]
    pairs = [row["comparison"] for row in report["indices"].values()]
    docs = [row for index in report["specified_ids"].values() for row in index["comparisons"]]
    report.update(status="complete", finished_at_utc=now(),
        size0_requests_actual=len(pairs) * 2, mget_documents_actual=len(docs) * 2,
        all_metadata_requests_complete=all(row["both_complete"] for row in pairs),
        all_mget_requests_complete=all(row["both_mget_complete"] for row in report["specified_ids"].values()),
        source_count_total=sum(row.get("source_count") or 0 for row in pairs),
        target_count_total=sum(row.get("target_count") or 0 for row in pairs),
        all_counts_equal=all(row.get("count_equal") for row in pairs),
        all_max_times_equal=all(row.get("update_time_max_equal") and row.get("insert_time_max_equal") for row in pairs),
        all_del_flag_aggregations_equal=all(row.get("del_flag_equal") for row in pairs),
        all_four_ids_found=all(row["both_found"] for row in docs),
        all_four_ids_metadata_equal=all(row["metadata_equal"] for row in docs),
        all_four_ids_del_flag_equal=all(row["del_flag_equal"] for row in docs))
    report["target_minus_source_count_total"] = report["target_count_total"] - report["source_count_total"]
    write_json(args.report, report)
    print(json.dumps({"report": str(args.report), **{key:report[key] for key in ("finished_at_utc", "source_count_total", "target_count_total", "target_minus_source_count_total", "all_counts_equal", "all_max_times_equal", "all_del_flag_aggregations_equal", "all_four_ids_found", "all_four_ids_metadata_equal", "all_four_ids_del_flag_equal")}}), flush=True)
    return 0 if report["all_metadata_requests_complete"] and report["all_mget_requests_complete"] and report["target_config_unchanged_during_reads"] else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--source-config", type=Path, default=Path("/root/knowledge_database_builder/config/config_es_engine.json"))
    parser.add_argument("--report", type=Path, default=Path("artifacts/key5_live_recheck_20261005.json"))
    args = parser.parse_args()
    warnings.filterwarnings("ignore")
    try:
        return run(args)
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
