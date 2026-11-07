"""Original startup code, with only server/external/thread boundaries substituted."""
import asyncio
import importlib
import importlib.util
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType, SimpleNamespace
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
    return runpy.run_module(module, run_name='__main__', alter_sys=False)


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
    report = module.check('csat', ['--mysql-config', str(missing), '--auth-config', str(missing)])
    assert not report['ok'] and 'missing_file:csat_auth' in report['errors']
    report = module.check('multilingual', ['--model_path', str(missing)])
    assert not report['ok'] and 'missing_or_empty_fasttext_model' in report['errors']
    assert not missing.exists()


def test_preflight_preserves_original_config_fallbacks(monkeypatch, tmp_path):
    module = load_preflight()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, 'probe_module', lambda name: {'module': name, 'available': True})
    fastgpt = module.check('fastgpt_proxy', [])
    assert fastgpt['ok'] and any('fallback is active' in warning for warning in fastgpt['warnings'])
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
    service = importlib.import_module('kdb.services.retrieval.app')
    es_calls, dify_calls, serve = [], [], []
    def fake_engine(**kwargs):
        es_calls.append(kwargs)
        return SimpleNamespace(index_name='test_index')
    monkeypatch.setattr(application, 'EsSearchInterface', fake_engine)
    monkeypatch.setattr(modifier, 'DifyWorkFlowRequest', lambda **kwargs: dify_calls.append(set(kwargs)) or SimpleNamespace())
    monkeypatch.setattr(service, 'SEARCH_DATA_INTERFACE', None)
    monkeypatch.setattr(service, 'MODIFY_KNOWLEDGE_HANDLE', None)
    embedding = write_json(tmp_path / 'embedding.json', {'DASHSCOPE_API_KEY': 'synthetic-only'})
    engine = write_json(tmp_path / 'engine.json', {'es_version': '8.17'})
    config = write_json(tmp_path / 'search.json', {'search_engine_config_path': engine, 'embedding_config_path': embedding, 'simility_config_path': ''})
    import uvicorn
    def fake_uvicorn(target, **kwargs):
        serve.append((target, kwargs))
        loaded = importlib.import_module(target.split(':')[0])
        assert any(route.path == '/search' for route in loaded.app.routes)
        async def worker_lifecycle():
            async with loaded.lifespan(loaded.app):
                assert loaded.SEARCH_DATA_INTERFACE is not None
            async with loaded.lifespan(loaded.app):
                assert loaded.SEARCH_DATA_INTERFACE is not None
        asyncio.run(worker_lifecycle())
    monkeypatch.setattr(uvicorn, 'run', fake_uvicorn)
    monkeypatch.setenv('SEARCH_SERVICE_WORKERS', '2')
    namespace = run_service(monkeypatch, tmp_path, 'kdb.services.retrieval.app', [config])
    assert namespace['SEARCH_DATA_INTERFACE'] is not None
    assert len(es_calls) == 2  # Parent __main__ + one modeled worker import/lifespan.
    assert len(dify_calls) == 4  # Recall + modify constructor per initialized interface.
    assert serve == [('kdb.services.retrieval.app:app', {'host': '0.0.0.0', 'port': 8003, 'reload': False, 'workers': 2})]


def test_off_task_module_main_registers_workers_without_running_them(monkeypatch, tmp_path):
    connector = importlib.import_module('kdb.shared.clients.mysql_connector')
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
    namespace = run_service(monkeypatch, tmp_path, 'kdb.services.off_task.app', ['--script-dir', str(script_dir), '--port', '19000', '--host', '127.0.0.1', '--max-concurrency', '3'])
    assert len(pools) == 1 and sorted(threads) == ['monitor_tasks', 'task_worker']
    assert namespace['task_queue'].qsize() == 0 and namespace['task_pid_mapping'] == {}
    assert serve[0][2] == {'host': '127.0.0.1', 'port': 19000, 'debug': False, 'threaded': True}
    assert namespace['max_total_concurrency'] == 10  # Original missing resource config resets to default.


def test_files_module_main_loads_cli_config_before_serve(monkeypatch, tmp_path):
    serve = record_flask(monkeypatch)
    path = write_json(tmp_path / 'minio.json', {'endpoint_url': 'http://synthetic.invalid', 'access_key': 'synthetic', 'secret_key': 'synthetic'})
    namespace = run_service(monkeypatch, tmp_path, 'kdb.services.files.app', ['--config', path, '--host', '127.0.0.1', '--port', '19001'])
    assert namespace['CONFIG_PATH'] == Path(path)
    assert serve[0][2] == {'host': '127.0.0.1', 'port': 19001, 'debug': False, 'threaded': True}
    assert any(rule.rule == '/upload' for rule in serve[0][0].url_map.iter_rules())


def test_csat_module_main_reads_auth_and_constructs_sql_pool(monkeypatch, tmp_path):
    connector = importlib.import_module('kdb.shared.clients.mysql_connector')
    pools = []
    class Pool:
        def __init__(self, **kwargs):
            pools.append(set(kwargs))
        def _remove_connections(self):
            pass
    monkeypatch.setattr(connector, 'MySQLConnectionPool', Pool)
    monkeypatch.setattr(connector, 'atexit', SimpleNamespace(register=lambda callback: None))
    serve = record_flask(monkeypatch)
    mysql = write_json(tmp_path / 'mysql.json', {'host': 'synthetic', 'database': 'synthetic', 'user': 'synthetic', 'password': 'synthetic'})
    auth = write_json(tmp_path / 'auth.json', {'synthetic': 'synthetic-only'})
    namespace = run_service(monkeypatch, tmp_path, 'kdb.services.csat.app', ['--mysql-config', mysql, '--auth-config', auth, '--port', '19002'])
    assert len(pools) == 1 and namespace['client_secrets'] == {'synthetic': 'synthetic-only'}
    assert serve[0][2] == {'host': '0.0.0.0', 'port': 19002}


def test_multilingual_module_main_loads_model_dependency_then_serve(monkeypatch, tmp_path):
    calls = []
    fasttext = ModuleType('fasttext')
    fasttext.FastText = SimpleNamespace(eprint=None)
    fasttext.load_model = lambda path: calls.append(path) or SimpleNamespace(predict=Mock())
    monkeypatch.setitem(sys.modules, 'fasttext', fasttext)
    serve = record_flask(monkeypatch)
    model = tmp_path / 'synthetic-model.ftz'
    model.write_bytes(b'synthetic model fixture, not a real fasttext model')
    namespace = run_service(monkeypatch, tmp_path, 'kdb.services.multilingual.app', ['--model_path', str(model), '--host', '127.0.0.1', '--port', '19003'])
    assert calls == [str(model)] and namespace['model'] is not None
    assert serve[0][2] == {'host': '127.0.0.1', 'port': 19003, 'debug': False}


def test_multilingual_module_main_missing_model_fails_without_serve(monkeypatch, tmp_path):
    dependency = ModuleType('fasttext')
    monkeypatch.setitem(sys.modules, 'fasttext', dependency)
    serve = record_flask(monkeypatch)
    with pytest.raises(SystemExit) as caught:
        run_service(monkeypatch, tmp_path, 'kdb.services.multilingual.app', ['--model_path', str(tmp_path / 'absent.ftz')])
    assert caught.value.code == 1 and serve == []


def test_crawler_module_main_constructs_processor_and_serves(monkeypatch, tmp_path):
    serve = record_flask(monkeypatch)
    namespace = run_service(monkeypatch, tmp_path, 'kdb.services.crawler.app', [])
    processor = namespace['logic_processer']
    assert processor.atom_parser is not None and processor.dataset_builder is not None
    assert serve[0][2] == {'host': '0.0.0.0', 'port': 6001, 'debug': True}


def test_fastgpt_module_main_keeps_uvicorn_contract(monkeypatch, tmp_path):
    import uvicorn
    calls = []
    def fake_uvicorn(target, **kwargs):
        loaded = importlib.import_module(target.split(':')[0])
        assert any(route.path == '/search' for route in loaded.app.routes)
        calls.append((target, kwargs))
    monkeypatch.setattr(uvicorn, 'run', fake_uvicorn)
    run_service(monkeypatch, tmp_path, 'kdb.services.fastgpt_proxy.app', [])
    assert calls == [('kdb.services.fastgpt_proxy.app:app', {'host': '0.0.0.0', 'port': 8000, 'reload': True})]
