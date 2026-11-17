"""Stable ontology error codes and the existing flat response envelope."""

ONTOLOGY_BAD_REQUEST = "ONTOLOGY_BAD_REQUEST"
ONTOLOGY_NOT_FOUND = "ONTOLOGY_NOT_FOUND"
ONTOLOGY_NAME_CONFLICT = "ONTOLOGY_NAME_CONFLICT"
ONTOLOGY_REVISION_CONFLICT = "ONTOLOGY_REVISION_CONFLICT"
ONTOLOGY_SCOPE_IMMUTABLE = "ONTOLOGY_SCOPE_IMMUTABLE"
ONTOLOGY_PAYLOAD_TOO_LARGE = "ONTOLOGY_PAYLOAD_TOO_LARGE"
ONTOLOGY_VALIDATION_FAILED = "ONTOLOGY_VALIDATION_FAILED"
ONTOLOGY_RESERVED_FIELD = "ONTOLOGY_RESERVED_FIELD"
ONTOLOGY_SCHEMA_VERSION_UNSUPPORTED = "ONTOLOGY_SCHEMA_VERSION_UNSUPPORTED"
ONTOLOGY_DB_UNAVAILABLE = "ONTOLOGY_DB_UNAVAILABLE"
ONTOLOGY_INTERNAL_ERROR = "ONTOLOGY_INTERNAL_ERROR"


class OntologyError(Exception):
    def __init__(self, code: str, http_status: int, message: str, details=None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.message = message
        self.details = list(details or [])

    def to_body(self) -> dict:
        return {"success": False, "code": self.code, "message": self.message,
                "details": self.details}
