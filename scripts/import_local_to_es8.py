#!/usr/bin/env python3
"""Import local ES7 gzip-NDJSON dumps into ES8 staging indices.

This is the second half of the migration.  It only reads ``manifest.json`` and
its per-index checkpoints plus local ``*.ndjson.gz`` files.  It intentionally
accepts no source configuration, so an import run cannot issue a request to the
old ES7 cluster.  It creates physical ``__v817_<run-id>`` indices only; aliases
and online routes are not touched.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from migrate_es7_to_es8 import ESHttp, MAX_BULK_BYTES, RETRY_STATUSES, MAX_BULK_ATTEMPTS, total_hits

BATCH_DOCS = 500


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def staged_name(index: str, run_id: str) -> str:
    return f"{index}__v817_{run_id}".lower()[:240]


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


def create_target(target: ESHttp, target_index: str, mappings: Mapping[str, Any], settings: Mapping[str, Any]) -> None:
    exists = target.request("HEAD", f"/{target_index}")
    if exists.status_code == 200:
        ensure_target_mapping(target, target_index)
        return
    if exists.status_code != 404:
        raise RuntimeError(f"检查目标索引失败 {target_index}: HTTP {exists.status_code}")
    body = {
        "settings": {
            "number_of_shards": int(settings.get("shards", 3)),
            "number_of_replicas": 0,
            "refresh_interval": "-1",
        },
        "mappings": mappings,
    }
    response = target.request("PUT", f"/{target_index}", json=body)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"创建目标索引失败 {target_index}: HTTP {response.status_code}: {response.text[:800]}")
    ensure_target_mapping(target, target_index)


def bulk_batch(target: ESHttp, target_index: str, records: List[Mapping[str, Any]]) -> Tuple[int, int]:
    pending = list(records)
    sent_bytes = 0
    last_error = ""
    for attempt in range(MAX_BULK_ATTEMPTS):
        lines: List[str] = []
        ids: List[str] = []
        for record in pending:
            doc_id = str(record["_id"])
            ids.append(doc_id)
            lines.append(json.dumps({"index": {"_index": target_index, "_id": doc_id}}, ensure_ascii=False, separators=(",", ":")))
            lines.append(json.dumps(record.get("_source") or {}, ensure_ascii=False, separators=(",", ":")))
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        sent_bytes += len(payload)
        response = target.request("POST", "/_bulk", data=payload, headers={"Content-Type": "application/x-ndjson"})
        if response.status_code in RETRY_STATUSES:
            last_error = f"HTTP {response.status_code}"
            time.sleep(min(30, 2**attempt))
            continue
        if response.status_code != 200:
            raise RuntimeError(f"bulk 请求失败: HTTP {response.status_code}: {response.text[:600]}")
        body = response.json()
        items = body.get("items", [])
        if len(items) != len(pending):
            last_error = f"bulk 返回 item 数量不一致 expected={len(pending)} actual={len(items)}"
            time.sleep(min(30, 2**attempt))
            continue
        failed: List[Mapping[str, Any]] = []
        statuses: List[int] = []
        details: List[str] = []
        for record, doc_id, item in zip(pending, ids, items):
            op = item.get("index") or item.get("create") or {}
            status = int(op.get("status", 500))
            if status >= 300:
                failed.append(record)
                statuses.append(status)
                error = op.get("error") or {}
                details.append(f"{doc_id}:{error.get('type', 'unknown')}:{error.get('reason', '')[:160]}")
        if not failed:
            return len(records), sent_bytes
        pending = failed
        last_error = f"bulk item failures={len(failed)}; {' | '.join(details[:5])}"
        if any(status not in RETRY_STATUSES for status in statuses):
            break
        time.sleep(min(30, 2**attempt))
    raise RuntimeError(f"bulk 重试耗尽: {last_error}; ids={[str(x['_id']) for x in pending[:5]]}")


def iter_batches(path: Path) -> Iterable[List[Mapping[str, Any]]]:
    batch: List[Mapping[str, Any]] = []
    batch_bytes = 0
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"导出文件 JSON 错误 {path}:{line_number}: {exc}") from exc
            if not isinstance(record, dict) or "_id" not in record or "_source" not in record:
                raise RuntimeError(f"导出文件记录格式错误 {path}:{line_number}")
            size = len(line.encode("utf-8"))
            if batch and (len(batch) >= BATCH_DOCS or batch_bytes + size > MAX_BULK_BYTES):
                yield batch
                batch = []
                batch_bytes = 0
            batch.append(record)
            batch_bytes += size
        if batch:
            yield batch


def import_one(target: ESHttp, state_path: Path, state: Dict[str, Any], target_index: str) -> Dict[str, Any]:
    dump = Path(state["file"])
    if not dump.exists():
        raise RuntimeError(f"本地 dump 不存在: {dump}")
    expected_sha = state.get("sha256")
    actual_sha = sha256_file(dump)
    if expected_sha and actual_sha != expected_sha:
        raise RuntimeError(f"本地 dump sha256 不匹配: {dump}")
    mappings = state.get("source_mapping")
    settings = state.get("source_settings")
    if not isinstance(mappings, dict) or not isinstance(settings, dict):
        raise RuntimeError(f"{state.get('source_index')} 缺少导出阶段 mapping/settings")
    state.update({"target_index": target_index, "import_status": "running", "import_started_at": utc_now(), "docs_imported": 0, "bulk_batches": 0, "bulk_bytes": 0})
    atomic_json(state_path, state)
    try:
        create_target(target, target_index, mappings, settings)
        for batch in iter_batches(dump):
            sent, byte_count = bulk_batch(target, target_index, list(batch))
            state["docs_imported"] += sent
            state["bulk_batches"] += 1
            state["bulk_bytes"] += byte_count
            state["last_import_id"] = str(batch[-1]["_id"])
            atomic_json(state_path, state)
        target.json("POST", f"/{target_index}/_refresh")
        target_count = total_hits(target.json("POST", f"/{target_index}/_search", json={"size": 0, "track_total_hits": True, "query": {"match_all": {}}}))
        state["target_count"] = target_count
        if target_count != int(state.get("docs_exported", -1)):
            raise RuntimeError(f"数量不一致 exported={state.get('docs_exported')} target={target_count}")
        del_body = target.json("POST", f"/{target_index}/_search", json={"size": 0, "track_total_hits": False, "aggs": {"del": {"terms": {"field": "del_flag", "size": 10}}}})
        state["target_del_flag"] = del_body.get("aggregations", {}).get("del", {}).get("buckets", [])
        settings_response = target.request("PUT", f"/{target_index}/_settings", json={"index": {"refresh_interval": "30s", "number_of_replicas": int(settings.get("replicas", 1))}})
        state["replicas_update_status"] = settings_response.status_code
        state.update({"import_status": "done", "status": "import_done", "import_finished_at": utc_now()})
        atomic_json(state_path, state)
        return state
    except Exception as exc:
        state.update({"import_status": "failed", "status": "import_failed", "import_finished_at": utc_now(), "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})
        atomic_json(state_path, state)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description="Import local ES7 gzip-NDJSON dumps to ES8 staging")
    parser.add_argument("--target-config", required=True)
    parser.add_argument("--dump-dir", required=True, help="与 export_es7_to_local.py 相同的目录")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--provider", choices=["paas", "serverless", "all"], default="all")
    args = parser.parse_args()
    dump_dir = Path(args.dump_dir)
    states_dir = dump_dir / "states"
    if not states_dir.exists():
        raise SystemExit(f"找不到导出 checkpoint: {states_dir}")
    target_cfg = json.loads(Path(args.target_config).read_text(encoding="utf-8"))
    targets = {name: ESHttp(cfg) for name, cfg in target_cfg["providers"].items()}
    paths = sorted(states_dir.glob("*.json"))
    states = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    # Export checkpoints use status=done; after this phase the same checkpoint
    # is status=import_done.  Keep both forms resumable without touching ES7.
    states = [x for x in states if x.get("status") == "done" or x.get("import_status") == "done"]
    if args.provider == "all":
        manifest_path = dump_dir / "manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            selected_names = {
                str(item.get("source_index"))
                for item in manifest.get("indices", [])
                if item.get("source_index")
            }
            if selected_names:
                # The dump directory can contain checkpoints from an older
                # canary/replay run.  Only the current export manifest is
                # authoritative for this import phase.
                states = [x for x in states if x.get("source_index") in selected_names]
            expected = int(manifest.get("selected_count", len(states)))
            if len(states) != expected:
                raise SystemExit(
                    f"本地导出尚未完成：checkpoint={len(states)} expected={expected}；"
                    "先完成 export/enrich，再执行 import"
                )
    if args.provider != "all":
        states = [x for x in states if ("payoneer" in x.get("source_index", "").lower()) == (args.provider == "paas")]
    manifest_path = dump_dir / "import_manifest.json"
    manifest: Dict[str, Any] = {"run_id": args.run_id, "phase": "import", "import_started_at": utc_now(), "selected_count": len(states), "indices": []}
    atomic_json(manifest_path, manifest)
    done = failed = 0
    for state in states:
        index = state["source_index"]
        provider = "paas" if "payoneer" in index.lower() else "serverless"
        target_index = staged_name(index, args.run_id)
        state_path = states_dir / (hashlib.sha256(index.encode()).hexdigest()[:16] + ".json")
        # A completed import is idempotently skipped after its checkpoint is retained.
        if state.get("import_status") == "done" and state.get("target_index") == target_index:
            done += 1
            manifest["indices"].append(state)
            print(json.dumps({"index": index, "status": "already_done", "target": target_index}, ensure_ascii=False), flush=True)
            continue
        print(json.dumps({"index": index, "provider": provider, "status": "start", "target": target_index}, ensure_ascii=False), flush=True)
        try:
            result = import_one(targets[provider], state_path, state, target_index)
            done += 1
            manifest["indices"].append(result)
            print(json.dumps({"index": index, "status": "done", "source_count": result.get("docs_exported"), "target_count": result.get("target_count")}, ensure_ascii=False), flush=True)
        except Exception as exc:
            failed += 1
            manifest["indices"].append({"source_index": index, "target_index": target_index, "status": "failed", "error": str(exc)[:1000]})
            print(json.dumps({"index": index, "status": "failed", "error": str(exc)[:1000]}, ensure_ascii=False), flush=True)
    manifest.update({"import_finished_at": utc_now(), "done_count": done, "failed_count": failed})
    atomic_json(manifest_path, manifest)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
