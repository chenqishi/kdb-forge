"""Pure validation and query construction for source-type counts.

LEARNING-COUNT-API-20261008. Importing this module performs no external I/O.
"""

from datetime import datetime
import re
from typing import Any, Dict, Optional


def validate_count_index(value: Optional[str]) -> Optional[str]:
    """Accept an empty name or one literal index, preserving the supplied name."""
    if value is None or value == "":
        return value
    if not isinstance(value, str):
        raise ValueError("index_name must be a string or null")
    if (
        value in {"_all", ".", ".."}
        or value.startswith(("-", "+", "_"))
        or any(char.isspace() or char in '\\/*?"<>|,#:[]' for char in value)
        or len(value.encode("utf-8")) > 255
    ):
        raise ValueError("index_name must be one literal index name")
    return value


def validate_count_from_type(value: str) -> str:
    """Require a nonempty source string without converting or normalizing it."""
    if not isinstance(value, str) or not value:
        raise ValueError("from_type must be a nonempty string")
    return value


def validate_count_time(value: Optional[str]) -> Optional[str]:
    """Validate a local calendar time without assigning or changing a timezone."""
    if value is None:
        return value
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value
    ):
        raise ValueError("time must use yyyy-MM-dd HH:mm:ss")
    try:
        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        raise ValueError("time must be a valid calendar date and time") from None
    return value


def build_from_type_count_query(
    from_type: str = "chat_auto",
    start: Optional[str] = None,
    end: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the original business filters, with an inclusive two-ended range."""
    validate_count_from_type(from_type)
    validate_count_time(start)
    validate_count_time(end)
    clauses = [
        {"term": {"quality_level": "high"}},
        {"term": {"from_type": from_type}},
    ]
    if start is not None and end is not None:
        clauses.append({"range": {"insert_time": {"gte": start, "lte": end}}})
    return {"bool": {"filter": clauses}}
