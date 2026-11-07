"""Reuse existing pure-Python Fire in a diagnostic process; no env installs."""
import importlib.util
import json
import sys
from pathlib import Path

import elasticsearch
import pytest

DEPENDENCIES = Path('/root/miniconda3/envs/py310/lib/python3.10/site-packages')


def load_pure_dependency(name):
    paths = {'six':'six.py','termcolor':'termcolor/__init__.py','fire':'fire/__init__.py'}
    if name not in paths:
        raise ValueError('outside pure dependency reuse scope')
    if name in sys.modules:
        return
    path = DEPENDENCIES/paths[name]
    spec = importlib.util.spec_from_file_location(name,path,
        submodule_search_locations=[str(path.parent)] if path.name=='__init__.py' else None)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)


def main():
    assert elasticsearch.__versionstr__.startswith('8.17.')
    for name in ('six','termcolor','fire'):
        load_pure_dependency(name)
    print(json.dumps({'diagnostic_python':sys.executable,'es_client':elasticsearch.__versionstr__,
        'fire_version':sys.modules['fire'].__version__,'pure_dependency_source':str(DEPENDENCIES),
        'environment_installations':0}))
    result = pytest.main(['-q','-rx','tests/test_off_task_es817_20261008.py',
        'tests/test_es8_interface.py','tests/test_insert_check_duplicate_arg.py',
        'tests/test_insert_ext_info_20261005.py','-p','no:cacheprovider'])
    assert elasticsearch.__versionstr__.startswith('8.17.')
    raise SystemExit(result)


if __name__=='__main__':
    main()
