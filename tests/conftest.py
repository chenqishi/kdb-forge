"""Apply the same mandatory offline boundary to every current pytest entry."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
TESTING = str(ROOT / 'scripts/testing')
if TESTING not in sys.path:
    sys.path.insert(0, TESTING)
from offline_guard import install
from offline_guard import prepare_paths
install(ROOT)
prepare_paths(ROOT)

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    process_items = [item for item in items if 'requires_process' in item.keywords]
    if process_items:
        for item in process_items:
            print('[offline] explicitly deselected (requires real subprocess): ' + item.nodeid, flush=True)
        config.hook.pytest_deselected(items=process_items)
        items[:] = [item for item in items if 'requires_process' not in item.keywords]
    skip_llm = pytest.mark.skip(reason='Remote LLM execution is unavailable in the offline suite')
    for item in items:
        if 'llm' in item.keywords:
            item.add_marker(skip_llm)
