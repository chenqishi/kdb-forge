#!/usr/bin/env python3
"""Stream ES7 business indexes into staged ES8.17 indexes.

The command performs one initial scroll -> bulk pass per index. It keeps no document
export on local disk; only metadata/checkpoints are written under --run-dir.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

import requests

VECTOR_PATHS = (
    "title_embedding",
    "content_embedding",
    "indexes.embedding",
    "image_indexes.embedding",
)
BATCH_DOCS = 500
SCROLL_KEEPALIVE = "30m"
MAX_BULK_BYTES = 15 * 1024 * 1024
RETRY_STATUSES = {429, 500, 502, 503, 504}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def total_hits(body: Mapping[str, Any]) -> int:
    value = body.get("hits", {}).get("total", 0)
    return int(value.get("value", 0) if isinstance(value, Mapping) else value or 0)


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256_json(value: Any) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


class ESHttp:
    def __init__(self, config: Mapping[str, Any], timeout: int = 120) -> None:
        hosts = config.get("hosts") or config.get("host")
        if isinstance(hosts, str):
            hosts = [hosts]
        if not hosts:
            raise ValueError("ES 配置缺少 hosts")
        self.host = str(hosts[0]).rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.auth = (config["username"], config["password"])
        self.session.verify = bool(config.get("verify_certs", False))

    def request(self, method: str, path: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", self.timeout)
        return self.session.request(method, self.host + path, **kwargs)

    def json(self, method: str, path: str, **kwargs: Any) -> Dict[str, Any]:
        response = self.request(method, path, **kwargs)
        if not response.ok:
            raise RuntimeError(f"HTTP {response.status_code} {method} {path}: {response.text[:600]}")
        return response.json()


def index_provider(index: str) -> str:
    return "paas" if "payoneer" in index.lower() else "serverless"


def staged_name(index: str, run_id: str) -> str:
    # All current non-empty source names are valid lowercase ES index names.
    name = f"{index}__v817_{run_id}".lower()
    if len(name) > 240:
        name = name[:240]
    return name


def vector_mapping() -> Dict[str, Any]:
    return {
        "type": "dense_vector",
        "dims": 1024,
        "index": True,
        "similarity": "cosine",
        "index_options": {"type": "hnsw"},
    }


def source_mapping(source: ESHttp, index: str) -> Tuple[Dict[str, Any], str]:
    body = source.json("GET", f"/{index}/_mapping")
    entry = body.get(index) or next(iter(body.values()))
    mappings = copy.deepcopy(entry.get("mappings") or {})
    mappings.pop("_default_", None)
    properties = mappings.setdefault("properties", {})
    for root in ("title_embedding", "content_embedding"):
        properties[root] = vector_mapping()
    for parent in ("indexes", "image_indexes"):
        nested = properties.get(parent)
        if not isinstance(nested, dict):
            nested = {"properties": {}}
            properties[parent] = nested
        # Some ES7 indexes mapped image_indexes as object. Promote it to nested
        # in the ES8 target so every embedding path remains independently KNN-searchable.
        nested["type"] = "nested"
        nested.setdefault("properties", {})["embedding"] = vector_mapping()
    return mappings, sha256_json(mappings)


def source_settings(source: ESHttp, index: str) -> Dict[str, int]:
    body = source.json("GET", f"/{index}/_settings", params={"flat_settings": "true"})
    settings = (body.get(index) or next(iter(body.values()))).get("settings", {})
    shards = int(settings.get("index.number_of_shards", 3))
    replicas = int(settings.get("index.number_of_replicas", 1))
    return {"shards": max(1, min(shards, 3)), "replicas": max(0, min(replicas, 1))}


def source_watermark(source: ESHttp, index: str) -> Optional[str]:
    body = source.json(
        "POST",
        f"/{index}/_search",
        json={
            "size": 1,
            "_source": ["update_time"],
            "sort": [{"update_time": {"order": "desc", "unmapped_type": "date"}}],
            "query": {"exists": {"field": "update_time"}},
        },
    )
    hits = body.get("hits", {}).get("hits", [])
    return ((hits[0].get("_source") or {}).get("update_time") if hits else None)


def ensure_target_mapping(target: ESHttp, index: str) -> None:
    body = target.json("GET", f"/{index}/_mapping")
    entry = body.get(index) or next(iter(body.values()))
    props = entry.get("mappings", {}).get("properties", {})
    checks = {
        "title_embedding": props.get("title_embedding", {}),
        "content_embedding": props.get("content_embedding", {}),
        "indexes.embedding": props.get("indexes", {}).get("properties", {}).get("embedding", {}),
        "image_indexes.embedding": props.get("image_indexes", {}).get("properties", {}).get("embedding", {}),
    }
    bad = [
        field for field, mapping in checks.items()
        if mapping.get("type") != "dense_vector"
        or mapping.get("dims") != 1024
        or mapping.get("index") is not True
        or mapping.get("similarity") != "cosine"
        or mapping.get("index_options", {}).get("type") != "hnsw"
    ]
    if bad:
        raise RuntimeError(f"目标 {index} 向量 mapping 不合格: {', '.join(bad)}")


def create_target(
    target: ESHttp,
    target_index: str,
    mappings: Dict[str, Any],
    settings: Dict[str, int],
) -> bool:
    exists = target.request("HEAD", f"/{target_index}")
    if exists.status_code == 200:
        ensure_target_mapping(target, target_index)
        return False
    if exists.status_code != 404:
        raise RuntimeError(f"检查目标索引失败 {target_index}: HTTP {exists.status_code}")
    body = {
        "settings": {
            "number_of_shards": settings["shards"],
            "number_of_replicas": 0,
            "refresh_interval": "-1",
        },
        "mappings": mappings,
    }
    response = target.request("PUT", f"/{target_index}", json=body)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"创建目标索引失败 {target_index}: HTTP {response.status_code}: {response.text[:800]}")
    ensure_target_mapping(target, target_index)
    return True


def bulk_batch(target: ESHttp, target_index: str, hits: List[Mapping[str, Any]]) -> Tuple[int, List[str], int]:
    lines: List[str] = []
    ids: List[str] = []
    for hit in hits:
        doc_id = str(hit["_id"])
        ids.append(doc_id)
        lines.append(json.dumps({"index": {"_index": target_index, "_id": doc_id}}, ensure_ascii=False, separators=(",", ":")))
        lines.append(json.dumps(hit.get("_source") or {}, ensure_ascii=False, separators=(",", ":")))
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    last_error = ""
    for attempt in range(5):
        response = target.request("POST", "/_bulk", data=payload, headers={"Content-Type": "application/x-ndjson"})
        if response.status_code in RETRY_STATUSES:
            last_error = f"HTTP {response.status_code}"
            time.sleep(min(30, 2 ** attempt))
            continue
        if response.status_code != 200:
            raise RuntimeError(f"bulk 请求失败: HTTP {response.status_code}: {response.text[:600]}")
        body = response.json()
        failed: List[str] = []
        for doc_id, item in zip(ids, body.get("items", [])):
            op = item.get("index") or item.get("create") or {}
            if int(op.get("status", 500)) >= 300:
                failed.append(doc_id)
        if not failed:
            return len(hits), [], len(payload)
        last_error = f"bulk item failures={len(failed)}"
        time.sleep(min(30, 2 ** attempt))
    raise RuntimeError(f"bulk 重试耗尽: {last_error}; ids={ids[:5]}")


def migrate_index(
    source: ESHttp,
    target: ESHttp,
    index: str,
    target_index: str,
    state_path: Path,
) -> Dict[str, Any]:
    state: Dict[str, Any] = {
        "source_index": index,
        "target_index": target_index,
        "provider": index_provider(index),
        "status": "running",
        "started_at": utc_now(),
        "docs_sent": 0,
        "bulk_batches": 0,
        "bulk_bytes": 0,
        "failed_ids": [],
    }
    atomic_json(state_path, state)
    try:
        mappings, mapping_hash = source_mapping(source, index)
        source_cfg = source_settings(source, index)
        state.update({
            "source_mapping_sha256": mapping_hash,
            "source_shards": source_cfg["shards"],
            "source_replicas": source_cfg["replicas"],
            "source_watermark": source_watermark(source, index),
        })
        atomic_json(state_path, state)
        create_target(target, target_index, mappings, source_cfg)
        scroll_id: Optional[str] = None
        try:
            body = source.json(
                "POST",
                f"/{index}/_search?scroll={SCROLL_KEEPALIVE}",
                json={"size": BATCH_DOCS, "sort": ["_doc"], "track_total_hits": True, "query": {"match_all": {}}},
            )
            scroll_id = body.get("_scroll_id")
            state["source_count_at_start"] = total_hits(body)
            while True:
                hits = body.get("hits", {}).get("hits", [])
                if not hits:
                    break
                # Keep requests bounded by both document count and bytes.
                chunks: List[List[Mapping[str, Any]]] = []
                chunk: List[Mapping[str, Any]] = []
                chunk_bytes = 0
                for hit in hits:
                    one = json.dumps(hit.get("_source") or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
                    if chunk and chunk_bytes + len(one) > MAX_BULK_BYTES:
                        chunks.append(chunk); chunk = []; chunk_bytes = 0
                    chunk.append(hit); chunk_bytes += len(one)
                if chunk:
                    chunks.append(chunk)
                for part in chunks:
                    sent, failed, payload_bytes = bulk_batch(target, target_index, part)
                    state["docs_sent"] += sent
                    state["bulk_batches"] += 1
                    state["bulk_bytes"] += payload_bytes
                    state["last_id"] = str(part[-1]["_id"])
                    atomic_json(state_path, state)
                if not scroll_id:
                    break
                body = source.json("POST", "/_search/scroll", json={"scroll": SCROLL_KEEPALIVE, "scroll_id": scroll_id})
                scroll_id = body.get("_scroll_id", scroll_id)
        finally:
            if scroll_id:
                try:
                    source.request("DELETE", "/_search/scroll", json={"scroll_id": [scroll_id]})
                except Exception:
                    pass
        target.json("POST", f"/{target_index}/_refresh")
        target_count = total_hits(target.json("POST", f"/{target_index}/_search", json={"size": 0, "track_total_hits": True, "query": {"match_all": {}}}))
        del_body = target.json("POST", f"/{target_index}/_search", json={"size": 0, "track_total_hits": False, "aggs": {"del": {"terms": {"field": "del_flag", "size": 10}}}})
        state["target_count"] = target_count
        state["target_del_flag"] = del_body.get("aggregations", {}).get("del", {}).get("buckets", [])
        if target_count != state.get("source_count_at_start"):
            raise RuntimeError(f"数量不一致 source={state.get('source_count_at_start')} target={target_count}")
        settings_response = target.request("PUT", f"/{target_index}/_settings", json={"index": {"refresh_interval": "30s", "number_of_replicas": source_cfg["replicas"]}})
        state["replicas_update_status"] = settings_response.status_code
        state["finished_at"] = utc_now()
        state["status"] = "done"
        atomic_json(state_path, state)
        return state
    except Exception as exc:
        state["status"] = "failed"
        state["error"] = f"{type(exc).__name__}: {str(exc)[:1000]}"
        state["finished_at"] = utc_now()
        atomic_json(state_path, state)
        raise


def load_inventory(path: Path) -> List[Dict[str, Any]]:
    body = json.loads(path.read_text(encoding="utf-8"))
    return [
        item for item in body["indices"]
        if item.get("classification") == "business_candidate"
        and int(item.get("root_count", {}).get("count", 0)) > 0
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--target-config", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--provider", choices=["paas", "serverless", "all"], default="all")
    args = parser.parse_args()
    source_config = json.loads(Path(args.source_config).read_text(encoding="utf-8"))
    target_config = json.loads(Path(args.target_config).read_text(encoding="utf-8"))
    source = ESHttp(source_config)
    targets = {name: ESHttp(cfg) for name, cfg in target_config["providers"].items()}
    inventory = load_inventory(Path(args.inventory))
    if args.provider != "all":
        inventory = [x for x in inventory if index_provider(x["index"]) == args.provider]
    run_dir = Path(args.run_dir)
    states_dir = run_dir / "states"
    run_dir.mkdir(parents=True, exist_ok=True)
    summary: Dict[str, Any] = {
        "run_id": args.run_id,
        "source_version": "7.10.0",
        "run_started_at": utc_now(),
        "provider_filter": args.provider,
        "selected_count": len(inventory),
        "indices": [],
    }
    atomic_json(run_dir / "run.json", summary)
    for item in inventory:
        index = item["index"]
        provider = index_provider(index)
        target_index = staged_name(index, args.run_id)
        state_path = states_dir / (hashlib.sha256(index.encode()).hexdigest()[:16] + ".json")
        if state_path.exists():
            existing = json.loads(state_path.read_text(encoding="utf-8"))
            if existing.get("status") == "done":
                summary["indices"].append(existing)
                print(json.dumps({"index": index, "status": "already_done", "target": target_index}, ensure_ascii=False), flush=True)
                continue
        print(json.dumps({"index": index, "provider": provider, "target": target_index, "status": "start"}, ensure_ascii=False), flush=True)
        try:
            result = migrate_index(source, targets[provider], index, target_index, state_path)
            summary["indices"].append(result)
            print(json.dumps({"index": index, "status": "done", "source_count": result.get("source_count_at_start"), "target_count": result.get("target_count")}, ensure_ascii=False), flush=True)
        except Exception as exc:
            summary["indices"].append({"source_index": index, "target_index": target_index, "provider": provider, "status": "failed", "error": str(exc)[:1000]})
            print(json.dumps({"index": index, "status": "failed", "error": str(exc)[:1000]}, ensure_ascii=False), flush=True)
    summary["run_finished_at"] = utc_now()
    summary["done_count"] = sum(1 for x in summary["indices"] if x.get("status") == "done")
    summary["failed_count"] = sum(1 for x in summary["indices"] if x.get("status") == "failed")
    atomic_json(run_dir / "run.json", summary)
    return 1 if summary["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
