"""Restore the two authorized 120 services; default is read-only checking."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import psutil

ROOT = Path('/root/knowledge_database_builder')
SCRIPTS = {
    'retrieval': 'knowledge_database_search_service/src/knowledge_database_search_es.py',
    'off_task': 'control_service/off_task_control_service.py',
}


def validate_backup(backup, before):
    payloads = []
    for entry in before['config_files']:
        content = Path(entry['backup']).read_bytes()
        if hashlib.sha256(content).hexdigest() != entry['sha256']:
            raise RuntimeError('configuration backup SHA mismatch')
        payloads.append((Path(entry['path']), content))
    legacy = json.loads((backup / 'config/config_for_search_index.json').read_text())
    if Path(legacy['search_engine_config_path']).read_bytes() != (backup / 'config/actual_legacy_engine.json').read_bytes():
        raise RuntimeError('shared legacy configuration changed; inspect before rollback')
    return payloads


def validate_services(activation):
    parents, children = [], []
    if set(activation['services']) != set(SCRIPTS):
        raise RuntimeError('activation must record exactly the two authorized services')
    for name, entry in activation['services'].items():
        process = psutil.Process(entry['pid'])
        if (process.create_time() != entry['create_time'] or process.cwd() != str(ROOT)
                or process.cmdline() != entry['cmdline']
                or os.path.realpath(process.exe()) != os.path.realpath(entry['python'])
                or SCRIPTS[name] not in process.cmdline()):
            raise RuntimeError('service identity changed; no signal sent')
        parents.append(process)
        children.extend(process.children(recursive=True))
    return parents, children


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', type=Path, default=ROOT / 'backup/es817_release_20261009')
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    backup = args.backup
    activation_path = backup / 'activated.json'
    if not activation_path.exists():
        print(json.dumps({'status': 'not_activated', 'services_stopped': 0}))
        return
    rollback_path = backup / 'rollback_state.json'
    if rollback_path.exists():
        prior = json.loads(rollback_path.read_text())
        if prior.get('phase') == 'healthy':
            print(json.dumps({'status': 'already_rolled_back', 'services_stopped': 0}))
            return
        raise RuntimeError('prior rollback unfinished; inspect recorded phase/PIDs, do not restart twice')
    before = json.loads((backup / 'before.json').read_text())
    activation = json.loads(activation_path.read_text())
    payloads = validate_backup(backup, before)
    for entry in activation['config_files']:
        if hashlib.sha256(Path(entry['path']).read_bytes()).hexdigest() != entry['sha256']:
            raise RuntimeError('active configuration changed since cutover')
    parents, children = validate_services(activation)
    with urllib.request.urlopen('http://127.0.0.1:6000/health', timeout=5) as response:
        health = json.load(response)
    if health.get('code') != 0 or any(health.get('data', {}).get(k) != 0 for k in ('active_tasks', 'queue_size')):
        raise RuntimeError('mining active/queued tasks: defer restart to protect work')
    if not args.execute:
        print(json.dumps({'status': 'ready', 'services_stopped': 0, 'configuration_files': len(payloads)}))
        return
    state = {'phase': 'stopping', 'new_services': {}}
    rollback_path.write_text(json.dumps(state, indent=2) + '\n')
    rollback_path.chmod(0o600)
    for process in parents:
        process.terminate()
    _, alive = psutil.wait_procs(parents + children, timeout=60)
    if any(p.is_running() and p.status() != psutil.STATUS_ZOMBIE for p in alive):
        raise RuntimeError('graceful shutdown incomplete; no force kill or duplicate start')
    for path, content in payloads:
        temporary = path.with_name(path.name + '.rollback_20261009.tmp')
        with temporary.open('xb') as handle:
            handle.write(content)
        temporary.chmod(0o600)
        os.replace(temporary, path)
    state['phase'] = 'starting'
    rollback_path.write_text(json.dumps(state, indent=2) + '\n')
    original = before['original_services']
    python = original['old_python']
    env = dict(os.environ)
    env['PATH'] = str(Path(python).parent) + ':' + env.get('PATH', '')
    env['PYTHONPATH'] = str(ROOT) + ':' + env.get('PYTHONPATH', '')
    env['CONDA_PREFIX'] = str(Path(python).parent.parent)
    env['CONDA_DEFAULT_ENV'] = 'py38'
    for name in SCRIPTS:
        log = ROOT / 'log' / (name + '.rollback_20261009.' + str(time.time_ns()) + '.log')
        with log.open('xb') as output:
            process = subprocess.Popen([python] + original[name + '_args'], cwd=ROOT, env=env,
                                       stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT,
                                       start_new_session=True)
        state['new_services'][name] = {'pid': process.pid, 'log': str(log)}
        rollback_path.write_text(json.dumps(state, indent=2) + '\n')
    for name, port, path in [('retrieval', 8003, '/openapi.json'), ('off_task', 6000, '/health')]:
        for attempt in range(30):
            if not psutil.pid_exists(state['new_services'][name]['pid']):
                raise RuntimeError('legacy service exited; inspect recorded log')
            try:
                with urllib.request.urlopen('http://127.0.0.1:' + str(port) + path, timeout=2) as response:
                    data = json.load(response)
                if (name == 'retrieval' and data.get('paths')) or (name == 'off_task' and data.get('code') == 0):
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError('legacy health not ready; inspect recorded log')
    state['phase'] = 'healthy'
    rollback_path.write_text(json.dumps(state, indent=2) + '\n')
    print(json.dumps({'status': 'rolled_back', 'services': state['new_services'], 'ES_writes': 0}))


if __name__ == '__main__':
    main()
