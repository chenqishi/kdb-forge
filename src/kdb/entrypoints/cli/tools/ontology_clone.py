"""Clone an approved industry ontology into a customer scope, active and pending review by default."""
import argparse
from copy import deepcopy
import json
import re
import sys

from kdb.retrieval.ontology.errors import (OntologyError, ONTOLOGY_BAD_REQUEST, ONTOLOGY_DB_UNAVAILABLE,
                                         ONTOLOGY_NAME_CONFLICT, ONTOLOGY_NOT_FOUND)
from kdb.retrieval.ontology.repository import OntologyRepository
from kdb.retrieval.ontology.service import OntologyService
from kdb.retrieval.ontology.schema import DEFAULT_AUDIT_STATUS, DEFAULT_STATUS, AUDIT_STATUS_VALUES, STATUS_VALUES
from kdb.retrieval.ontology.validation import validate_document


def main(argv=None, service=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-client", required=True)
    parser.add_argument("--source-product", required=True)
    parser.add_argument("--target-client", required=True)
    parser.add_argument("--target-product")
    parser.add_argument("--status", default=DEFAULT_STATUS, choices=STATUS_VALUES)
    parser.add_argument("--audit-status", default=DEFAULT_AUDIT_STATUS, choices=AUDIT_STATUS_VALUES)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        for field in ("source_client", "source_product", "target_client", "target_product"):
            raw = getattr(args, field)
            if raw is None:
                continue
            value = raw.strip()
            if (field == "target_client" and not value) or not re.fullmatch(r"([a-z0-9][a-z0-9_.-]{0,63})?", value):
                raise OntologyError(ONTOLOGY_BAD_REQUEST, 400, "作用域编码不合法",
                                    [{"path": field, "reason": "invalid_pattern", "message": "客户编码必须为非空小写编码"}])
            setattr(args, field, value)
        service = service or OntologyService(OntologyRepository())
        source = service.select_ontology(args.source_client, args.source_product, None, True)
        if source["ontology"] is None:
            raise OntologyError(ONTOLOGY_NOT_FOUND, 404, "源本体不存在")
        document = deepcopy(validate_document(source["ontology"]["data_json"]).document)
        document["client"] = args.target_client
        document["product"] = args.target_product if args.target_product is not None else args.source_product
        validated = validate_document(document)
        if args.dry_run:
            result = {"success": True, "message": "dry run", "client": validated.client,
                      "product": validated.product, "name": validated.name, "status": args.status,
                      "audit_status": args.audit_status,
                      "object_types": len(validated.document["object_types"]), "document_bytes": validated.document_bytes}
        else:
            result = service.insert_ontology({"data_json": validated.document, "status": args.status,
                                              "audit_status": args.audit_status})
        print(json.dumps(result, ensure_ascii=False))
        return 0
    except OntologyError as exc:
        print(json.dumps(exc.to_body(), ensure_ascii=False), file=sys.stderr)
        return {ONTOLOGY_NOT_FOUND: 2, ONTOLOGY_NAME_CONFLICT: 3, ONTOLOGY_DB_UNAVAILABLE: 5}.get(exc.code, 4)


if __name__ == "__main__":
    raise SystemExit(main())
