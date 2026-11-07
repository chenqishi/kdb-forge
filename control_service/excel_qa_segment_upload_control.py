"""Legacy import and CLI path; implementation lives in kdb.mining.pipelines.excel_qa_segment_upload."""
import pathlib as _pathlib
import sys as _sys
_root = _pathlib.Path(__file__).resolve().parents[1]
for _path in (str(_root / "src"), str(_root)):
    if _path not in _sys.path:
        _sys.path.insert(0, _path)
from kdb.compat.entrypoints import legacy_entry as _legacy_entry
_legacy_entry(__name__, 'kdb.mining.pipelines.excel_qa_segment_upload', globals())
