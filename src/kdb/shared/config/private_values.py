"""Private replacements for inherited literal credentials; no online lookup."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _private_defaults():
    path = Path(__file__).resolve().parents[4] / "private/runtime_config/hardcoded_defaults.json"
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def private_value(key: str) -> str:
    """Return the preserved effective value at its original evaluation point."""
    return _private_defaults()[key]
