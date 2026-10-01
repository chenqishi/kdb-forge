#!/usr/bin/env python3
"""Fill mapping/settings metadata for an existing local ES7 dump.

This helper never scrolls documents and never opens ES8. It is useful for dumps
created by an older exporter that recorded only file checksums; after enrichment
the normal local importer can create ES8 mappings without querying ES7.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from migrate_es7_to_es8 import ESHttp, load_inventory, source_mapping, source_settings, source_watermark


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic(path: Path, value: Dict[str, Any]) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Enrich local dump checkpoints without scrolling documents")
    parser.add_argument("--source-config", required=True)
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--dump-dir", required=True)
    args = parser.parse_args()
    source = ESHttp(json.loads(Path(args.source_config).read_text(encoding="utf-8")))
    dump_dir = Path(args.dump_dir)
    states = dump_dir / "states"
    changed = failed = 0
    version = source.cluster_version() if hasattr(source, "cluster_version") else source.json("GET", "/").get("version", {}).get("number")
    for item in load_inventory(Path(args.inventory)):
        index = item["index"]
        path = states / (hashlib.sha256(index.encode()).hexdigest()[:16] + ".json")
        if not path.exists():
            continue
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("status") != "done":
            continue
        try:
            dump = Path(state["file"])
            if not dump.exists():
                raise RuntimeError(f"dump missing: {dump}")
            mappings, mapping_hash = source_mapping(source, index)
            state.update({
                "source_version": version,
                "source_mapping": mappings,
                "source_mapping_sha256": mapping_hash,
                "source_settings": source_settings(source, index),
                "source_watermark": source_watermark(source, index),
                "metadata_enriched_at": now(),
            })
            atomic(path, state)
            changed += 1
            print(json.dumps({"index": index, "status": "enriched"}, ensure_ascii=False), flush=True)
        except Exception as exc:
            failed += 1
            print(json.dumps({"index": index, "status": "failed", "error": str(exc)[:500]}, ensure_ascii=False), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
