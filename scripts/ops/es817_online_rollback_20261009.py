"""Legacy import and CLI path; implementation lives in kdb.compat.legacy_ops.scripts.ops.es817_online_rollback_20261009."""
import pathlib as _pathlib
import sys as _sys
_root = _pathlib.Path(__file__).resolve().parents[2]
for _path in (str(_root / "src"), str(_root)):
    if _path not in _sys.path:
        _sys.path.insert(0, _path)
from kdb.compat.entrypoints import legacy_entry as _legacy_entry
_legacy_entry(__name__, 'kdb.compat.legacy_ops.scripts.ops.es817_online_rollback_20261009', globals())
