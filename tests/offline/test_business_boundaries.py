"""Keep the business dependency pyramid and executable entrypoints enforceable."""
import ast
from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
CHECKS = runpy.run_path(str(ROOT / 'scripts/testing/architecture.py'))


def test_business_import_directions_and_cycles():
    modules, edges = CHECKS['inspect_imports'](ROOT / 'src')
    assert CHECKS['boundary_errors'](edges) == []
    assert CHECKS['import_cycles'](modules, edges) == []


def test_launchers_and_task_commands_resolve_to_executable_modules():
    preflight = runpy.run_path(str(ROOT / 'scripts/services/preflight.py'))
    modules = set(preflight['ENTRYPOINTS'].values())
    for rel in ['src/kdb/mining/tasks/processes.py', 'src/kdb/mining/tasks/submission/local_batch.py']:
        tree = ast.parse((ROOT / rel).read_text())
        modules.update(n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                       and isinstance(n.value, str) and n.value.startswith('kdb.entrypoints.cli.'))
    assert set(preflight['ENTRYPOINTS']) == {'retrieval', 'off_task', 'files', 'multilingual'}
    assert len(modules) >= 9
    for module in modules:
        path = ROOT / 'src' / (module.replace('.', '/') + '.py')
        assert path.is_file(), module
        tree = ast.parse(path.read_text())
        assert any(isinstance(n, ast.If) and '__name__' in ast.unparse(n.test) for n in tree.body), module


def test_task_components_share_one_state_owner():
    from kdb.mining.tasks import processes
    from kdb.mining.tasks import queue
    from kdb.mining.tasks import records
    from kdb.mining.tasks import resources
    from kdb.mining.tasks import state
    assert processes.runtime_state is state
    assert queue.runtime_state is state
    assert records.runtime_state is state
    assert resources.runtime_state is state
