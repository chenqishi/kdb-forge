"""Validate native count responses without changing legacy count consumers."""
from collections.abc import Mapping


def complete_count(response: Mapping) -> int:
    """Return an exact count only when all shards completed successfully."""
    count = response.get("count")
    shards = response.get("_shards")
    if type(count) is not int or count < 0 or not isinstance(shards, Mapping):
        raise RuntimeError("Malformed native count response")
    total, successful, failed = (shards.get(key) for key in ("total", "successful", "failed"))
    if (any(type(value) is not int or value < 0 for value in (total, successful, failed))
            or total == 0 or failed != 0 or successful != total
            or any(flag in response and response[flag] is not False for flag in ("timed_out", "terminated_early"))
            or shards.get("failures") or response.get("error") or response.get("failures")):
        raise RuntimeError("Incomplete native count response")
    return count
