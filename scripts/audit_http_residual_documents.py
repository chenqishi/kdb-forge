#!/usr/bin/env python3
"""Compare HTTP result residual IDs to new ES and local dumps, without old reads."""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
from typing import Any

from compare_es7_es8_online import compare_values, read_root_vector_values, sha256_json, without_vectors
from compare_legacy_search_http import now, write_json
from migrate_es7_to_es8 import ESHttp, index_provider


def comparison(left: Any, right: Any) -> dict:
    paths: list[str] = []
    equal, delta = compare_values(left, right, mismatches=paths)
    return {"equal": equal, "max_numeric_diff": delta, "mismatch_paths": paths[:20],
            "dump_sha256": sha256_json(left), "new_sha256": sha256_json(right)}


def find_records(path: Path, ids: set[str]) -> tuple[dict, int]:
    # Inspect bytes before decoding JSON. Only selected records are parsed, so
    # vector arrays in all other records never become Python objects.
    needles = {docid: docid.encode("ascii") for docid in ids}
    found = {}
    scanned = 0
    with gzip.open(path, "rb") as handle:
        for line in handle:
            scanned += 1
            if not any(needle in line for needle in needles.values()):
                continue
            record = json.loads(line)
            docid = str(record.get("_id"))
            if docid in ids:
                found[docid] = record["_source"]
                needles.pop(docid, None)
                if not needles:
                    break
    return found, scanned


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--new-config", type=Path, default=Path("config/config_es_runtime.local.json"))
    parser.add_argument("--dump-dir", type=Path, default=Path("migration_runs/local_dump_20261001/data"))
    args = parser.parse_args()
    cached = json.loads(args.comparison_report.read_text())
    groups: dict[str, dict[str, list]] = {}
    for case in cached["cases"]:
        for kind in ("old_only_ids", "new_only_ids"):
            for index, docid in case["comparison"][kind]:
                groups.setdefault(index, {}).setdefault(docid, []).append({"case": case["name"], "kind": kind})
    states = {state["source_index"]: state for path in (args.dump_dir / "states").glob("*.json")
              if (state := json.loads(path.read_text())).get("source_index")}
    config = json.loads(args.new_config.read_text())
    report = {"started_at": now(), "reads_old_es": False, "read_only": True,
              "comparison_report": str(args.comparison_report), "indices": {}}
    write_json(args.report, report)
    for index, ids in groups.items():
        client = ESHttp(config["providers"][index_provider(index)])
        docs = {str(d["_id"]): d for d in client.json("POST", f"/{index}/_mget", json={"ids": sorted(ids)})["docs"]}
        roots = read_root_vector_values(client, index, sorted(ids))
        entry = {"new_found": {docid: bool(docs[docid].get("found")) for docid in ids}, "docs": {}}
        report["indices"][index] = entry
        write_json(args.report, report)
        local, scanned = find_records(Path(states[index]["file"]), set(ids))
        entry["dump_records_scanned"] = scanned
        for docid, memberships in ids.items():
            item = {"memberships": memberships, "new_found": bool(docs[docid].get("found")), "dump_found": docid in local}
            entry["docs"][docid] = item
            if not item["new_found"] or not item["dump_found"]:
                continue
            old = local[docid]
            new = docs[docid]["_source"]
            item["non_vector_source"] = comparison(without_vectors(old), without_vectors(new))
            item["title_content"] = comparison({k: old.get(k) for k in ("title", "content")},
                                                {k: new.get(k) for k in ("title", "content")})
            owner_keys = sorted(k for k in set(old) | set(new) if "owner" in k.lower())
            item["owner_fields"] = {"keys": owner_keys, **comparison({k: old.get(k) for k in owner_keys},
                                                                       {k: new.get(k) for k in owner_keys})}
            item["root_vectors"] = {}
            for field in ("title_embedding", "content_embedding"):
                a, b = old.get(field), roots.get(docid, {}).get(field)
                item["root_vectors"][field] = {"dump_dims": len(a) if isinstance(a, list) else 0,
                                               "new_dims": len(b) if isinstance(b, list) else 0,
                                               **comparison(a, b)}
            item["nested_vectors"] = {}
            for parent in ("indexes", "image_indexes"):
                a = [v.get("embedding") for v in old.get(parent, []) if isinstance(v, dict)]
                b = [v.get("embedding") for v in new.get(parent, []) if isinstance(v, dict)]
                item["nested_vectors"][parent] = {"dump_items": len(a), "new_items": len(b), **comparison(a, b)}
        write_json(args.report, report)
        print(json.dumps({"index": index, "residual_ids": len(ids), "new_found": sum(entry["new_found"].values()),
                          "dump_found": len(local), "dump_records_scanned": scanned}), flush=True)
    report["finished_at"] = now()
    write_json(args.report, report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
