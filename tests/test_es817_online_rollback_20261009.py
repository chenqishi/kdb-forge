"""Rollback must reject corrupt backups and unrelated service identities."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/test_es817_online_rollback_20261009.py')
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock
import pytest


def load_tool():
    path = Path(__legacy_source_file__).resolve().parents[1] / 'scripts/ops/es817_online_rollback_20261009.py'
    spec = importlib.util.spec_from_file_location('rollback_actual', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('fault', [None, 'backup', 'legacy'])
def test_backup_integrity(tmp_path, fault):
    module = load_tool()
    config = tmp_path / 'config'
    config.mkdir()
    legacy = tmp_path / 'shared.json'
    legacy.write_bytes(b'{"index_name":"mix"}')
    business = config / 'config_for_search_index.json'
    business.write_text(json.dumps({'search_engine_config_path': str(legacy)}))
    (config / 'actual_legacy_engine.json').write_bytes(legacy.read_bytes())
    before = {'config_files': [{'backup': str(business), 'path': str(tmp_path / 'online.json'),
                               'sha256': hashlib.sha256(business.read_bytes()).hexdigest()}]}
    if fault == 'backup': business.write_text('{}')
    if fault == 'legacy': legacy.write_text('{}')
    if fault:
        with pytest.raises(RuntimeError): module.validate_backup(tmp_path, before)
    else:
        assert module.validate_backup(tmp_path, before) == [(tmp_path / 'online.json', business.read_bytes())]


@pytest.mark.parametrize('fault', [None, 'time', 'cwd', 'command', 'python'])
def test_service_identity(monkeypatch, fault):
    module = load_tool()
    activation = {'services': {}}
    processes = []
    for n, (name, script) in enumerate(module.SCRIPTS.items()):
        entry = {'pid': 20 + n, 'create_time': 100.0, 'cmdline': ['python', script], 'python': '/expected/python'}
        activation['services'][name] = entry
        process = Mock()
        process.create_time.return_value = 99.0 if fault == 'time' else 100.0
        process.cwd.return_value = '/elsewhere' if fault == 'cwd' else str(module.ROOT)
        process.cmdline.return_value = ['python', 'unrelated.py'] if fault == 'command' else entry['cmdline']
        process.exe.return_value = '/different/python' if fault == 'python' else entry['python']
        process.children.return_value = []
        processes.append(process)
    monkeypatch.setattr(module.psutil, 'Process', Mock(side_effect=processes))
    if fault:
        with pytest.raises(RuntimeError): module.validate_services(activation)
    else:
        assert module.validate_services(activation) == (processes, [])
    assert all(not p.terminate.called for p in processes)


def test_no_activation_never_stops_services(tmp_path, monkeypatch, capsys):
    module = load_tool()
    monkeypatch.setattr('sys.argv', ['rollback', '--backup', str(tmp_path), '--execute'])
    boundary = Mock(side_effect=AssertionError('no process inspection permitted'))
    monkeypatch.setattr(module.psutil, 'Process', boundary)
    monkeypatch.setattr(module.subprocess, 'Popen', boundary)
    module.main()
    assert json.loads(capsys.readouterr().out)['status'] == 'not_activated'
    assert not boundary.called
