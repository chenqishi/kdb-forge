#!/usr/bin/env python3
"""Build a reviewable per-index shard plan from the local ES7 dump manifest.

This script only reads local inventory/checkpoint files.  It does not contact
either Elasticsearch cluster and does not delete or modify any index.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, Iterable


DEFAULT_EXCLUDED = {
    "test",
    "test_case",
    "test_kg",
    "test_knowledge",
    "test_oceanpayment",
    "test_oceanpayment_two",
    "test_pay",
    "test_product",
    "paynooer",
    "seller",
    "rufit",
    "rufit_customer_service",
    "rufit_demo",
    "rufit_demo_marsmind_front",
    "rufit_fit",
    "mix",
    "mercado_all_kg",
}


def parse_size(value: Any) -> int:
    text = str(value).strip().lower()
    units = (("gb", 1024**3), ("mb", 1024**2), ("kb", 1024), ("b", 1))
    for suffix, multiplier in units:
        if text.endswith(suffix):
            return int(float(text[: -len(suffix)]) * multiplier)
    return int(float(text))


def load_states(states_dir: Path) -> Dict[str, Dict[str, Any]]:
    result: Dict[str, Dict[str, Any]] = {}
    for path in states_dir.glob("*.json"):
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("source_index"):
            result[str(state["source_index"])] = state
    return result


def build_plan(
    manifest: Dict[str, Any],
    inventory: Dict[str, Any],
    states: Dict[str, Dict[str, Any]],
    threshold_bytes: int,
    excluded: Iterable[str],
) -> Dict[str, Any]:
    excluded_set = {name.lower() for name in excluded}
    inventory_by_name = {str(row["index"]): row for row in inventory["indices"]}
    selected = []
    skipped = []
    for item in manifest.get("indices", []):
        name = str(item["source_index"])
        if name.lower() in excluded_set:
            skipped.append({"source_index": name, "reason": "explicitly_excluded"})
            continue
        state = states.get(name)
        row = inventory_by_name.get(name, {})
        if not state or not state.get("file"):
            raise SystemExit(f"缺少本地 dump checkpoint: {name}")
        primary_bytes = parse_size(row.get("pri.store.size", 0))
        provider = "paas" if "payoneer" in name.lower() else "serverless"
        # PaaS keeps the source topology for this migration.  Serverless uses
        # the explicit size policy; replicas remain a separate target policy.
        target_shards = int(state.get("source_settings", {}).get("shards", 3))
        rule = "source_topology"
        if provider == "serverless":
            target_shards = 1 if primary_bytes <= threshold_bytes else 3
            rule = "serverless_size_threshold"
        selected.append(
            {
                "source_index": name,
                "provider": provider,
                "docs_exported": int(item.get("docs_exported", 0)),
                "primary_store_size_bytes": primary_bytes,
                "primary_store_size_mib": round(primary_bytes / 1024**2, 3),
                "threshold_bytes": threshold_bytes if provider == "serverless" else None,
                "target_shards": target_shards,
                "target_replicas_requested": 0,
                "rule": rule,
                "dump_file": state["file"],
            }
        )
    selected.sort(key=lambda row: (row["provider"], row["source_index"].lower()))
    return {
        "plan_version": 1,
        "source_manifest": "data/manifest.json",
        "source_inventory": "artifacts/es7_formal_inventory.json",
        "threshold_unit": "MiB",
        "serverless_threshold_bytes": threshold_bytes,
        "serverless_threshold_mib": round(threshold_bytes / 1024**2, 3),
        "excluded_indices": sorted(excluded_set),
        "selected_count": len(selected),
        "excluded_count": len(skipped),
        "selected": selected,
        "excluded": sorted(skipped, key=lambda row: row["source_index"].lower()),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dump-dir", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--threshold-mib", type=float, default=1024.0)
    args = parser.parse_args()
    manifest = json.loads((args.dump_dir / "manifest.json").read_text(encoding="utf-8"))
    inventory = json.loads(args.inventory.read_text(encoding="utf-8"))
    states = load_states(args.dump_dir / "states")
    plan = build_plan(
        manifest,
        inventory,
        states,
        int(args.threshold_mib * 1024**2),
        DEFAULT_EXCLUDED,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "selected_count": plan["selected_count"],
        "excluded_count": plan["excluded_count"],
        "providers": {
            provider: sum(row["provider"] == provider for row in plan["selected"])
            for provider in ("paas", "serverless")
        },
        "serverless_shards": {
            "one_primary": sum(row["provider"] == "serverless" and row["target_shards"] == 1 for row in plan["selected"]),
            "three_primary": sum(row["provider"] == "serverless" and row["target_shards"] == 3 for row in plan["selected"]),
        },
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
