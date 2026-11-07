"""Explicit locations for this project, its source and retained resources."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[4]
SOURCE_ROOT = PROJECT_ROOT / "src"
RESOURCES_ROOT = PROJECT_ROOT / "resources"


def project_path(*parts):
    """Join project-relative configuration, data or output components."""
    return PROJECT_ROOT.joinpath(*parts)


def source_path(*parts):
    """Join canonical source components beneath this project's src directory."""
    return SOURCE_ROOT.joinpath(*parts)


def resource_path(*parts):
    """Join retained non-code resource components."""
    return RESOURCES_ROOT.joinpath(*parts)


def subprocess_env(base=None):
    """Pass the current environment and this project's source to child modules."""
    env = dict(os.environ if base is None else base)
    inherited = env.get("PYTHONPATH", "")
    paths = [str(SOURCE_ROOT), *[value for value in inherited.split(os.pathsep)
                                if value and value != str(SOURCE_ROOT)]]
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env
