"""Paths for mechanically moved modules and their original public entrypoints."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def legacy_source_path(relative: str) -> str:
    """Keep original project-relative __file__ calculations within this checkout."""
    return str(PROJECT_ROOT / relative)


def legacy_package_path(relative: str) -> str:
    """Keep Flask templates/static roots at their original project-relative path."""
    return str((PROJECT_ROOT / relative).parent)
