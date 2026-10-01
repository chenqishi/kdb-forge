#!/usr/bin/env python3
"""Export ES7 business documents to local gzip NDJSON without touching ES8."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

from migrate_es7_to_es8 import (
    ESHttp,
    SCROLL_KEEPALIVE,
    load_inventory,
    sha256_json,
    source_mapping,
    source_settings,
    source_watermark,
    total_hits,
)

EXPORT_BATCH = 500


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


def file_name(index: str) -> str:
    safe = re.sub(r"[^a-z0-9_.-]+", "_", index.lower())[:160]
    digest = hashlib.sha256(index.encode()).hexdigest()[:16]
    return f"{digest}__{safe}.ndjson.gz"


def export_index(source: ESHttp, index: str, dump_dir: Path, state_path: Path) -> Dict[str, Any]:
    output = dump_dir / file_name(index)
    temp_output = output.with_suffix(output.suffix + f".{os.getpid()}.part")
    state: Dict[str, Any] = {
        "source_index": index,
        "status": "running",
        "started_at": utc_now(),
        "file": str(output),
        "docs_exported": 0,
        "bytes_uncompressed": 0,
    }
    atomic_json(state_path, state)
    scroll_id: Optional[str] = None
    try:
        mappings, mapping_hash = source_mapping(source, index)
        settings = source_settings(source, index)
        watermark = source_watermark(source, index)
        state.update({
            "source_mapping_sha256": mapping_hash,
            # Keep the transformed ES8 mapping in the checkpoint.  Import must
            # be able to create the target without querying ES7 again.
            "source_mapping": mappings,
            "source_settings": settings,
            "source_watermark": watermark,
        })
        atomic_json(state_path, state)
        search = source.json(
            "POST",
            f"/{index}/_search?scroll={SCROLL_KEEPALIVE}",
            json={"size": EXPORT_BATCH, "sort": ["_doc"], "track_total_hits": True, "query": {"match_all": {}}},
        )
        scroll_id = search.get("_scroll_id")
        state["source_count_at_start"] = total_hits(search)
        dump_dir.mkdir(parents=True, exist_ok=True)
        ndjson_digest = hashlib.sha256()
        with gzip.open(temp_output, "wt", encoding="utf-8", newline="\n") as out:
            body = search
            while True:
                hits = body.get("hits", {}).get("hits", [])
                if not hits:
                    break
                for hit in hits:
                    line = json.dumps(
                        {"_id": str(hit["_id"]), "_source": hit.get("_source") or {}},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ) + "\n"
                    out.write(line)
                    ndjson_digest.update(line.encode("utf-8"))
                    state["docs_exported"] += 1
                    state["bytes_uncompressed"] += len(line.encode("utf-8"))
                atomic_json(state_path, state)
                if not scroll_id:
                    break
                body = source.json("POST", "/_search/scroll", json={"scroll": SCROLL_KEEPALIVE, "scroll_id": scroll_id})
                scroll_id = body.get("_scroll_id", scroll_id)
        temp_output.replace(output)
        if state.get("docs_exported") != state.get("source_count_at_start"):
            raise RuntimeError(
                f"数量不一致 source={state.get('source_count_at_start')} "
                f"exported={state.get('docs_exported')}"
            )
        digest = hashlib.sha256()
        with output.open("rb") as inp:
            for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                digest.update(chunk)
        state.update({
            "compressed_bytes": output.stat().st_size,
            "sha256": digest.hexdigest(),
            "ndjson_sha256": ndjson_digest.hexdigest(),
            "finished_at": utc_now(),
            "status": "done",
        })
        atomic_json(state_path, state)
        return state
    except Exception as exc:
        try:
            temp_output.unlink(missing_ok=True)
        except Exception:
            pass
        state.update({"finished_at": utc_now(), "status": "failed", "error": f"{type(exc).__name__}: {str(exc)[:1000]}"})
        atomic_json(state_path, state)
        raise
    finally:
        if scroll_id:
            try:
                source.request("DELETE", "/_search/scroll", json={"scroll_id": [scroll_id]})
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--dump-dir", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    source_cfg = json.loads(Path(args.source_config).read_text(encoding="utf-8"))
    source = ESHttp(source_cfg)
    dump_dir = Path(args.dump_dir)
    states_dir = dump_dir / "states"
    dump_dir.mkdir(parents=True, exist_ok=True)
    version = source.json("GET", "/").get("version", {}).get("number")
    inventory = load_inventory(Path(args.inventory))
    manifest: Dict[str, Any] = {
        "run_id": args.run_id,
        "source_version": version,
        "export_started_at": utc_now(),
        "selected_count": len(inventory),
        "indices": [],
    }
    atomic_json(dump_dir / "manifest.json", manifest)
    for item in inventory:
        index = item["index"]
        state_path = states_dir / (hashlib.sha256(index.encode()).hexdigest()[:16] + ".json")
        if state_path.exists():
            existing = json.loads(state_path.read_text(encoding="utf-8"))
            if existing.get("status") == "done" and Path(existing.get("file", "")).exists():
                # A dump is importable only when its transformed mapping and
                # checksum are present.  Older exporters wrote only the hash;
                # those checkpoints are deliberately re-exported.
                if existing.get("source_mapping") and existing.get("sha256") == sha256_file(Path(existing["file"])):
                    manifest["indices"].append(existing)
                    print(json.dumps({"index": index, "status": "already_done"}, ensure_ascii=False), flush=True)
                    continue
        print(json.dumps({"index": index, "status": "start"}, ensure_ascii=False), flush=True)
        try:
            result = export_index(source, index, dump_dir, state_path)
            manifest["indices"].append(result)
            print(json.dumps({"index": index, "status": "done", "docs": result["docs_exported"]}, ensure_ascii=False), flush=True)
        except Exception as exc:
            manifest["indices"].append({"source_index": index, "status": "failed", "error": str(exc)[:1000]})
            print(json.dumps({"index": index, "status": "failed", "error": str(exc)[:1000]}, ensure_ascii=False), flush=True)
    manifest["export_finished_at"] = utc_now()
    manifest["done_count"] = sum(x.get("status") == "done" for x in manifest["indices"])
    manifest["failed_count"] = sum(x.get("status") == "failed" for x in manifest["indices"])
    atomic_json(dump_dir / "manifest.json", manifest)
    return 1 if manifest["failed_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
