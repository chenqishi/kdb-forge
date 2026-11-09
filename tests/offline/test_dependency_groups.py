"""Check dependency declarations against real entrypoint import graphs offline."""
from functools import lru_cache
from pathlib import Path
import sys
import pkgutil
import sysconfig

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
try:
    import tomllib
except ImportError:
    import tomli as tomllib

from architecture import inspect_imports

ROOT = Path(__file__).resolve().parents[2]
PROJECT = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']
MODULES, EDGES = inspect_imports(ROOT / 'src')
STDLIB_NAMES = getattr(sys, 'stdlib_module_names', None)
if STDLIB_NAMES is None:  # Python 3.9 has no sys.stdlib_module_names.
    stdlib = Path(sysconfig.get_path('stdlib'))
    STDLIB_NAMES = set(sys.builtin_module_names) | {
        module.name for module in pkgutil.iter_modules([str(stdlib), str(stdlib / 'lib-dynload')])
    }
IMPORT_DISTRIBUTIONS = {
    'PIL': 'Pillow', 'PyPDF2': 'PyPDF2', 'bs4': 'beautifulsoup4',
    'docx': 'python-docx', 'faiss': 'faiss-cpu', 'fitz': 'PyMuPDF',
    'mysql': 'mysql-connector-python',
}


@lru_cache(maxsize=None)
def declared_packages(extra):
    requirements = list(PROJECT['dependencies'])
    if extra:
        requirements += PROJECT['optional-dependencies'][extra]
    result = set()
    for text in requirements:
        requirement = Requirement(text)
        if canonicalize_name(requirement.name) == canonicalize_name(PROJECT['name']):
            assert requirement.specifier.contains(PROJECT['version'])
            for nested in requirement.extras:
                result.update(declared_packages(nested))
        else:
            result.add(canonicalize_name(requirement.name))
    return frozenset(result)


@pytest.mark.parametrize('entrypoint,extra', [
    ('kdb.entrypoints.http.retrieval.app', None),
    ('kdb.entrypoints.http.files.app', 'files'),
    ('kdb.entrypoints.http.tasks.app', 'tasks'),
    ('kdb.entrypoints.http.multilingual.app', 'multilingual'),
    ('kdb.entrypoints.cli.mining.chat_qa', 'chat'),
    ('kdb.entrypoints.cli.mining.document_qa', 'documents'),
    ('kdb.entrypoints.cli.mining.document_qa_segment', 'documents'),
    ('kdb.entrypoints.cli.mining.excel_qa_segment_upload', 'documents'),
    ('kdb.entrypoints.cli.mining.html_qa_segment', 'web'),
])
def test_service_import_dependencies_are_declared(entrypoint, extra):
    pending = [entrypoint]
    visited = set()
    required = set()
    while pending:
        module = pending.pop()
        if module in visited:
            continue
        visited.add(module)
        for edge in EDGES:
            if edge['source'] != module:
                continue
            target = edge['target']
            if target in MODULES:
                pending.append(target)
            else:
                name = target.split('.')[0]
                if name not in STDLIB_NAMES and name != 'kdb':
                    required.add(canonicalize_name(IMPORT_DISTRIBUTIONS.get(name, name)))
    assert required <= declared_packages(extra), sorted(required - declared_packages(extra))
    if extra == 'multilingual':
        numpy_ranges = [Requirement(text).specifier
                        for text in PROJECT['dependencies'] + PROJECT['optional-dependencies'][extra]
                        if canonicalize_name(Requirement(text).name) == 'numpy']
        assert all('1.26.4' in constraint for constraint in numpy_ranges)
        # fastText 0.9.x constructs an array from a probability list with copy=False.
        assert not all('2.0.0' in constraint for constraint in numpy_ranges)
        assert not all('2.5.0' in constraint for constraint in numpy_ranges)


def test_all_direct_import_dependencies_are_declared():
    required = {
        canonicalize_name(IMPORT_DISTRIBUTIONS.get(name, name))
        for edge in EDGES
        for name in [edge['target'].split('.')[0]]
        if name not in STDLIB_NAMES and name != 'kdb'
    }
    assert required <= declared_packages('all'), sorted(required - declared_packages('all'))
