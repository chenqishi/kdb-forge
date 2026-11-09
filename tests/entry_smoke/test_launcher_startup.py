import kdb.shared.storage.runtime_state as file_runtime
import kdb.multilingual.runtime as language_runtime
import kdb.retrieval.application.runtime as retrieval_runtime
import kdb.retrieval.engines.bootstrap as engine_bootstrap
import kdb.retrieval.application.runtime as _retrieval_application_runtime
"""Original startup code, with only server/external/thread boundaries substituted."""
import asyncio
import importlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_preflight():
    spec = importlib.util.spec_from_file_location('candidate_service_preflight', ROOT / 'scripts/services/preflight.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return str(path)


def run_service(monkeypatch, tmp_path, module, args):
    """Exercise the public module entry point with external serving replaced."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, 'argv', [module, *args])
    # Only the entry module is isolated; shared business/runtime state stays intact.
    parent_name, _, attribute = module.rpartition('.')
    parent = importlib.import_module(parent_name)
    missing = object()
    cached_module = sys.modules.pop(module, missing)
    cached_attribute = getattr(parent, attribute, missing)
    if cached_attribute is not missing:
        delattr(parent, attribute)
    try:
        return runpy.run_module(module, run_name='__main__', alter_sys=False)
    finally:
        sys.modules.pop(module, None)
        if cached_module is not missing:
            sys.modules[module] = cached_module
        if cached_attribute is not missing:
            setattr(parent, attribute, cached_attribute)
        elif hasattr(parent, attribute):
            delattr(parent, attribute)


def record_flask(monkeypatch):
    import flask
    calls = []
    monkeypatch.setattr(flask.Flask, 'run', lambda self, *args, **kwargs: calls.append((self, args, kwargs)))
    return calls


def test_preflight_rejects_wrong_sdk_without_execution(monkeypatch, tmp_path, capsys):
    module = load_preflight()
    monkeypatch.setattr(module, 'probe_module', lambda name: {'module': name, 'available': True, 'version': [9, 4, 1]} if name == 'elasticsearch' else {'module': name, 'available': True})
    config = write_json(tmp_path / 'search.json', {'search_engine_config_path': 'missing-engine.json', 'embedding_config_path': 'missing-embedding.json', 'password': 'NEVER_PRINT_THIS'})
    monkeypatch.setattr(module.os, 'execv', Mock(side_effect=AssertionError('must not exec')))
    assert module.main(['retrieval', config]) == 78
    report = json.loads(capsys.readouterr().out)
    assert 'elasticsearch_8_17_required' in report['errors']
    assert 'NEVER_PRINT_THIS' not in json.dumps(report)
    module.os.execv.assert_not_called()


def test_preflight_preserves_exact_argv_and_cwd(monkeypatch, tmp_path):
    module = load_preflight()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, 'check', lambda service, argv: {'ok': True, 'service': service})
    calls = []
    class Executed(Exception):
        pass
    def fake_exec(interpreter, argv):
        calls.append((interpreter, argv, Path.cwd()))
        raise Executed()
    monkeypatch.setattr(module.os, 'execv', fake_exec)
    args = ['--port', '19000', '--host=127.0.0.1', '--config', 'path with spaces.json']
    with pytest.raises(Executed):
        module.main(['files', *args])
    assert calls == [(sys.executable, [sys.executable, '-m', module.ENTRYPOINTS['files'], *args], tmp_path)]


def test_preflight_check_only_never_executes(monkeypatch, capsys):
    module = load_preflight()
    checked = []
    monkeypatch.setattr(module, 'check', lambda service, argv: checked.append((service, argv)) or {'ok': True})
    execute = Mock(side_effect=AssertionError('check-only must not start'))
    monkeypatch.setattr(module.os, 'execv', execute)
    assert module.main(['files', '--check', '--config', 'local.json']) == 0
    assert checked == [('files', ['--config', 'local.json'])]
    assert json.loads(capsys.readouterr().out)['ok'] is True
    execute.assert_not_called()


def test_preflight_missing_auth_and_model_are_not_created(monkeypatch, tmp_path):
    module = load_preflight()
    monkeypatch.setattr(module, 'probe_module', lambda name: {'module': name, 'available': True})
    missing = tmp_path / 'absent'
    report = module.check('multilingual', ['--model_path', str(missing)])
    assert not report['ok'] and 'missing_or_empty_fasttext_model' in report['errors']
    assert not missing.exists()


def test_preflight_preserves_original_config_fallbacks(monkeypatch, tmp_path):
    module = load_preflight()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, 'probe_module', lambda name: {'module': name, 'available': True})
    empty_minio = write_json(tmp_path / 'minio.json', {})
    files = module.check('files', ['--config', empty_minio])
    assert files['ok'] and any('MinioTools default fields' in warning for warning in files['warnings'])
    missing = module.check('files', ['--config', str(tmp_path / 'absent.json')])
    assert not missing['ok'] and 'missing_file:minio_config' in missing['errors']


def test_shell_launchers_require_explicit_interpreter():
    for script in (ROOT / 'scripts/services').glob('*.sh'):
        text = script.read_text()
        assert '${KDB_PYTHON:-python}' not in text
        assert 'exit 64' in text
        assert 'exec "$KDB_PYTHON"' in text
        assert script.stem + ' "$@"' in text


def test_retrieval_module_main_initializes_then_worker_lifespan_once(monkeypatch, tmp_path):
    application = importlib.import_module('kdb.retrieval.application.search_index_data_interface')
    modifier = importlib.import_module('kdb.retrieval.modification.modify_knowledge')
    service = importlib.import_module('kdb.entrypoints.http.retrieval.app')
    es_calls, dify_calls, serve = [], [], []
    def fake_engine(**kwargs):
        es_calls.append(kwargs)
        return SimpleNamespace(index_name='test_index')
    monkeypatch.setattr(engine_bootstrap, 'EsSearchInterface', fake_engine)
    monkeypatch.setattr(modifier, 'DifyWorkFlowRequest', lambda **kwargs: dify_calls.append(set(kwargs)) or SimpleNamespace())
    monkeypatch.setattr(retrieval_runtime, 'SEARCH_DATA_INTERFACE', None)
    monkeypatch.setattr(retrieval_runtime, 'MODIFY_KNOWLEDGE_HANDLE', None)
    embedding = write_json(tmp_path / 'embedding.json', {'DASHSCOPE_API_KEY': 'synthetic-only'})
    engine = write_json(tmp_path / 'engine.json', {'es_version': '8.17'})
    config = write_json(tmp_path / 'search.json', {'search_engine_config_path': engine, 'embedding_config_path': embedding, 'simility_config_path': ''})
    import uvicorn
    def fake_uvicorn(target, **kwargs):
        serve.append((target, kwargs))
        loaded = importlib.import_module(target.split(':')[0])
        assert any(route.path == '/search' for route in loaded.app.routes)
        retrieval_runtime.SEARCH_DATA_INTERFACE = None
        retrieval_runtime.MODIFY_KNOWLEDGE_HANDLE = None
        async def worker_lifecycle():
            async with loaded.lifespan(loaded.app):
                assert retrieval_runtime.SEARCH_DATA_INTERFACE is not None
            async with loaded.lifespan(loaded.app):
                assert retrieval_runtime.SEARCH_DATA_INTERFACE is not None
        asyncio.run(worker_lifecycle())
    monkeypatch.setattr(uvicorn, 'run', fake_uvicorn)
    monkeypatch.setenv('SEARCH_SERVICE_WORKERS', '2')
    namespace = run_service(monkeypatch, tmp_path, 'kdb.entrypoints.http.retrieval.app', [config])
    assert namespace['runtime_state'].SEARCH_DATA_INTERFACE is not None
    assert importlib.import_module('kdb.entrypoints.http.retrieval.app') is service
    assert len(es_calls) == 2  # Parent __main__ + one modeled worker import/lifespan.
    assert len(dify_calls) == 4  # Recall + modify constructor per initialized interface.
    assert serve == [('kdb.entrypoints.http.retrieval.app:app', {'host': '0.0.0.0', 'port': 8003, 'reload': False, 'workers': 2})]


def test_off_task_module_main_registers_workers_without_running_them(monkeypatch, tmp_path):
    connector = importlib.import_module('kdb.shared.database.mysql')
    pools, threads = [], []
    class Pool:
        def __init__(self, **kwargs):
            pools.append(set(kwargs))
        def _remove_connections(self):
            pass
    class Thread:
        def __init__(self, target, daemon):
            self.target = target
            self.daemon = daemon
        def start(self):
            threads.append(self.target.__name__)
    monkeypatch.setattr(connector, 'MySQLConnectionPool', Pool)
    monkeypatch.setattr(connector, 'atexit', SimpleNamespace(register=lambda callback: None))
    import threading
    monkeypatch.setattr(threading, 'Thread', Thread)
    serve = record_flask(monkeypatch)
    script_dir = tmp_path / 'workspace'
    script_dir.mkdir(parents=True)
    write_json(script_dir / 'config/mysql_conn_config.json', {'host': 'synthetic', 'database': 'synthetic', 'user': 'synthetic', 'password': 'synthetic'})
    preflight = load_preflight()
    monkeypatch.setattr(preflight, 'probe_module', lambda name: {'available': True})
    # Runtime config lives elsewhere; source checks must still use the migrated project.
    for service in preflight.ENTRYPOINTS:
        report = preflight.check(service, ['--script-dir', str(script_dir)])
        assert Path(report['entrypoint_source']).is_file()
        if service == 'off_task':
            assert report['ok'], report['errors']
    namespace = run_service(monkeypatch, tmp_path, 'kdb.entrypoints.http.tasks.app', ['--script-dir', str(script_dir), '--port', '19000', '--host', '127.0.0.1', '--max-concurrency', '3'])
    assert len(pools) == 1 and sorted(threads) == ['monitor_tasks', 'task_worker']
    assert namespace['runtime_state'].task_queue.qsize() == 0 and namespace['runtime_state'].task_pid_mapping == {}
    assert serve[0][2] == {'host': '127.0.0.1', 'port': 19000, 'debug': False, 'threaded': True}
    assert namespace['runtime_state'].max_total_concurrency == 10  # Original missing resource config resets to default.


def test_files_module_main_loads_cli_config_before_serve(monkeypatch, tmp_path):
    serve = record_flask(monkeypatch)
    path = write_json(tmp_path / 'minio.json', {'endpoint_url': 'http://synthetic.invalid', 'access_key': 'synthetic', 'secret_key': 'synthetic'})
    namespace = run_service(monkeypatch, tmp_path, 'kdb.entrypoints.http.files.app', ['--config', path, '--host', '127.0.0.1', '--port', '19001'])
    assert file_runtime.CONFIG_PATH == Path(path)
    assert serve[0][2] == {'host': '127.0.0.1', 'port': 19001, 'debug': False, 'threaded': True}
    assert any(rule.rule == '/upload' for rule in serve[0][0].url_map.iter_rules())




def test_multilingual_module_main_loads_model_dependency_then_serve(monkeypatch, tmp_path):
    calls = []
    fasttext = ModuleType('fasttext')
    fasttext.FastText = SimpleNamespace(eprint=None)
    fasttext.load_model = lambda path: calls.append(path) or SimpleNamespace(predict=Mock())
    monkeypatch.setitem(sys.modules, 'fasttext', fasttext)
    serve = record_flask(monkeypatch)
    model = tmp_path / 'synthetic-model.ftz'
    model.write_bytes(b'synthetic model fixture, not a real fasttext model')
    namespace = run_service(monkeypatch, tmp_path, 'kdb.entrypoints.http.multilingual.app', ['--model_path', str(model), '--host', '127.0.0.1', '--port', '19003'])
    assert calls == [str(model)] and language_runtime.model is not None
    assert serve[0][2] == {'host': '127.0.0.1', 'port': 19003, 'debug': False}


def test_multilingual_module_main_missing_model_fails_without_serve(monkeypatch, tmp_path):
    dependency = ModuleType('fasttext')
    monkeypatch.setitem(sys.modules, 'fasttext', dependency)
    serve = record_flask(monkeypatch)
    with pytest.raises(SystemExit) as caught:
        run_service(monkeypatch, tmp_path, 'kdb.entrypoints.http.multilingual.app', ['--model_path', str(tmp_path / 'absent.ftz')])
    assert caught.value.code == 1 and serve == []
