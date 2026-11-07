"""Explicit legacy manual-tool entry; importing can perform original side effects."""
from pathlib import Path as _Path
_source = _Path(__file__).resolve().parent / 'archive/incident_tools/drain_bol.py'
exec(compile(_source.read_bytes(), str(_source), "exec"), globals())
