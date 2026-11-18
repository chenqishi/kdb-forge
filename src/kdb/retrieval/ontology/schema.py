"""Ontology constants and deterministic Pydantic JSON Schema artifact."""
import argparse
import json
from pathlib import Path

from .models import CARDINALITIES, DATA_TYPES, ITEM_TYPES, SEVERITIES, OntologyDocument

SCHEMA_VERSION = "1.0"
TABLE_NAME = "dops_ontology"
MAX_DOCUMENT_BYTES = 1024 * 1024
WARN_DOCUMENT_BYTES = 200 * 1024
MAX_ERRORS = 50
DEFAULT_PAGE_SIZE = 100
MAX_PAGE_SIZE = 100
STATUS_VALUES = ("active", "inactive")
REVIEW_STATUS_VALUES = ("pending", "approved", "rejected")
DEFAULT_STATUS = "active"
DEFAULT_REVIEW_STATUS = "pending"
SCOPE_VALUES = ("client_product", "client", "industry", "global", "none")
RESERVED_FIELD_ORDER = ("id", "ontology_id", "status", "review_status", "revision", "create_time",
                        "update_time", "del_flag")
RESERVED_FIELDS = frozenset(RESERVED_FIELD_ORDER)
RESERVED_SCAN_SKIP = frozenset({"extensions"})
SCHEMA_PATH = Path(__file__).with_name("ontology.schema.json")


def schema_text() -> str:
    schema = OntologyDocument.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "https://kdb.marsmind.internal/schemas/ontology/1.0.json"
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = schema_text()
    if args.write:
        SCHEMA_PATH.write_text(expected, encoding="utf-8")
        return 0
    if not SCHEMA_PATH.exists() or SCHEMA_PATH.read_text(encoding="utf-8") != expected:
        print("ontology.schema.json differs; run python -m kdb.retrieval.ontology.schema --write")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
