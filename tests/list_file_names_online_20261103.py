"""Authorized retrieval-only rollout; default checks without changing services."""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

import psutil

ROOT = Path('/root/knowledge_database_builder')
BACKUP = ROOT / 'backup/list_file_names_20261103'
OLD_HEAD = '3aa4aadc854fd8e8fc6f31555754799882fbabd8'
CONFIGS = ['config/config_es_engine.json', 'config/config_es_engine_es817.online.json',
           'config/config_for_search_index.json', 'config/config_for_search_index_no_dup_payoneer.json']
DIRTY = ['data_preprocess/multimodal_process.py',
         'knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py',
         'knowledge_clear_tool/wordtotext.py', 'knowledge_generate/knowlege_segment_builder_by_dify.py']


def read_json(path):
    assert path.stat().st_size < 2 * 1024 ** 2, 'oversized_json'
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 ** 2), b''):
            h.update(chunk)
    return h.hexdigest()


def save(path, value):
    tmp = path.with_suffix(path.suffix + '.tmp')
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
    os.replace(tmp, path)


def api(path, payload=None):
    assert path in ('openapi.json', 'search', 'web_search', 'list_file_names')
    req = urllib.request.Request('http://127.0.0.1:8003/' + path,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'})
    start = time.monotonic()
    with urllib.request.urlopen(req, timeout=30) as response:
        raw = response.read(8 * 1024 ** 2 + 1)
        assert response.status == 200 and len(raw) <= 8 * 1024 ** 2
    return json.loads(raw), round((time.monotonic() - start) * 1000, 2), len(raw)


def probe():
    from knowledge_interface_tools.es8_client_router import IndexClientRouter
    business = read_json(ROOT / 'config/config_for_search_index.json')
    router = IndexClientRouter(config_path=str(ROOT / business['search_engine_config_path']))
    rows = []
    try:
        for index in ('payoneer_olive', 'mercado_local'):
            client = router.get_client_by_index(index).options(request_timeout=15, max_retries=0)
            assert client.indices.exists(index=index), 'missing_existing_index'
            expected = {}
            for source in (None, 'document', 'auto_learning'):
                filters = [{'term': {'del_flag': 0}}]
                if source:
                    filters.append({'term': {'from_type_norm': source}})
                raw = client.search(index=index, size=0, query={'bool': {'filter': filters}},
                    aggs={'grp': {'terms': {'field': 'ext_info.from_file_name.keyword', 'size': 5}}})
                assert not raw.get('timed_out') and raw['_shards']['failed'] == 0
                expected[source] = sorted((b['key'], b['doc_count']) for b in raw['aggregations']['grp']['buckets'])
            for label, extra, source in [
                ('omitted', {}, None), ('null', {'from_type_norm': None}, None),
                ('empty', {'from_type_norm': ''}, None), ('blank', {'from_type_norm': '  '}, None),
                ('document', {'from_type_norm': 'document'}, 'document'),
                ('auto_learning', {'from_type_norm': 'auto_learning'}, 'auto_learning')]:
                data, ms, size = api('list_file_names', dict(extra, index_name=index, size=5))
                actual = sorted((v['value'], v['doc_count']) for v in data['values'])
                assert data['success'] is True and data['total_count'] == len(actual)
                assert actual == expected[source], 'list_result_differs_from_raw_es_' + label
                rows.append({'index': index, 'endpoint': 'list_file_names', 'source': label,
                    'matched_raw_es': True, 'files': len(actual), 'doc_counts': [n for _, n in actual],
                    'result_sha256': hashlib.sha256(json.dumps(actual).encode()).hexdigest(),
                    'ms': ms, 'bytes': size})
            data, ms, size = api('web_search', {'index_names': index, 'text': '', 'page_size': 2,
                'page_num': 1, 'condition_dicts': [{'del_flag': [0], 'data_type': ['qa'],
                'audit_result': [1, 2, -1]}], 'score_threshold': -1})
            hits = data.get('results', [])
            assert hits and data.get('total_count', 0) > 0
            assert all((h.get('_id') or h.get('id')) and h.get('del_flag') == 0 for h in hits)
            rows.append({'index': index, 'endpoint': 'web_search', 'hits': len(hits),
                'total': data['total_count'], 'ms': ms, 'bytes': size})
            sample = client.search(index=index, size=1, source=['title'], query={'bool': {'filter': [
                {'term': {'del_flag': 0}}, {'term': {'data_type': 'qa'}},
                {'term': {'quality_level': 'high'}}, {'terms': {'audit_result': [1, 2, -1]}}]}})
            assert sample['_shards']['failed'] == 0 and not sample.get('timed_out')
            query = sample['hits']['hits'][0]['_source']['title']
            assert isinstance(query, str) and query.strip()
            data, ms, size = api('search', {'index_names': index, 'text': query, 'top_k': 2,
                'search_type': 'qa', 'data_type': 'text', 'use_synonyms': True, 'score_threshold': .4})
            hits = data.get('results', [])
            assert hits and all(h.get('id') and h.get('q') != '检索结果错误' for h in hits)
            rows.append({'index': index, 'endpoint': 'search', 'hits': len(hits), 'ms': ms,
                'bytes': size, 'ids_sha256': hashlib.sha256(json.dumps([h['id'] for h in hits]).encode()).hexdigest()})
    finally:
        router.close()
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    assert len(args.commit) == 40 and all(c in '0123456789abcdef' for c in args.commit)
    activation_path = ROOT / 'backup/es817_release_20261009/activated.json'
    activation = read_json(activation_path)
    spec = importlib.util.spec_from_file_location('service_guard', ROOT / 'scripts/ops/es817_online_rollback_20261009.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.validate_services(activation)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    assert head == OLD_HEAD, 'unexpected_before_head'
    tracked = subprocess.check_output(['git', 'status', '--porcelain=v1', '-uno'], cwd=ROOT, text=True)
    assert set(line[3:] for line in tracked.splitlines()) == set(DIRTY), 'unexpected_dirty_paths'
    before_hashes = {name: digest(ROOT / name) for name in CONFIGS + DIRTY}
    openapi_before, _, _ = api('openapi.json')
    assert 'from_type_norm' not in openapi_before['components']['schemas']['ListFileNamesRequest']['properties']
    retrieval_entry = activation['services']['retrieval']
    retrieval = psutil.Process(retrieval_entry['pid'])
    environment = retrieval.environ()
    old_tree = [retrieval] + retrieval.children(recursive=True)
    log = Path(retrieval_entry['log'])
    log_before = log.stat()
    assert os.readlink('/proc/%s/fd/1' % retrieval.pid) == str(log)
    if not args.execute:
        print(json.dumps({'status': 'preflight_ok', 'head': head, 'old_pid': retrieval.pid,
            'off_task_pid': activation['services']['off_task']['pid'], 'dirty_paths': sorted(DIRTY)}), flush=True)
        return
    assert not BACKUP.exists(), 'existing_deployment_record_inspect_before_retry'
    BACKUP.mkdir(mode=0o700)
    state = {'phase': 'preflight', 'before_head': head, 'commit': args.commit, 'before_hashes': before_hashes,
        'old_retrieval': retrieval_entry, 'off_task': activation['services']['off_task'],
        'started': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'es_writes': 0,
        'log': str(log), 'log_offset': log_before.st_size}
    save(BACKUP / 'state.json', state)
    save(BACKUP / 'activated.before.json', activation)
    save(BACKUP / 'retrieval.environment.json', environment)
    try:
        fetched = subprocess.run(['git', 'fetch', 'origin'], cwd=ROOT, capture_output=True, text=True)
        assert fetched.returncode == 0, 'fetch_failed'
        assert subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=ROOT, text=True).strip() == args.commit
        assert subprocess.run(['git', 'merge-base', '--is-ancestor', head, args.commit], cwd=ROOT).returncode == 0
        changes = subprocess.check_output(['git', 'diff', '--name-status', head, args.commit], cwd=ROOT, text=True)
        for line in changes.splitlines():
            status, name = line.split('\t', 1)
            assert name not in DIRTY and name not in CONFIGS
            if status == 'A':
                assert not (ROOT / name).exists() and not (ROOT / name).is_symlink(), 'untracked_collision'
        pull = subprocess.run(['git', 'pull', '--ff-only', 'origin', args.commit], cwd=ROOT, capture_output=True, text=True)
        save(BACKUP / 'git_pull.json', {'returncode': pull.returncode, 'stdout': pull.stdout, 'stderr': pull.stderr})
        assert pull.returncode == 0, 'pull_failed_services_unchanged'
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip() == args.commit
        assert before_hashes == {name: digest(ROOT / name) for name in before_hashes}
        assert tracked == subprocess.check_output(['git', 'status', '--porcelain=v1', '-uno'], cwd=ROOT, text=True)
        guard.validate_services(activation)
        state['phase'] = 'stopping_retrieval'
        save(BACKUP / 'state.json', state)
        print(json.dumps({'phase': state['phase'], 'pid': retrieval.pid}), flush=True)
        retrieval.terminate()
        deadline = time.monotonic() + 90
        while True:
            alive = [p for p in old_tree if p.is_running() and p.status() != psutil.STATUS_ZOMBIE]
            if not alive:
                break
            assert time.monotonic() < deadline, 'graceful_stop_incomplete_no_force_kill'
            psutil.wait_procs(alive, timeout=2)
        assert not any(c.status == 'LISTEN' and c.laddr.port == 8003 for c in psutil.net_connections('tcp'))
        with log.open('ab') as output:
            process = subprocess.Popen(retrieval_entry['cmdline'], cwd=ROOT, env=environment,
                stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        state.update(phase='starting_retrieval', new_retrieval_pid=process.pid)
        save(BACKUP / 'state.json', state)
        print(json.dumps({'phase': state['phase'], 'pid': process.pid}), flush=True)
        for attempt in range(45):
            assert process.poll() is None, 'new_service_exited'
            try:
                after, _, _ = api('openapi.json')
                if 'from_type_norm' in after['components']['schemas']['ListFileNamesRequest']['properties']:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        else:
            raise RuntimeError('new_service_health_timeout')
        now = psutil.Process(process.pid)
        updated = dict(activation, head=args.commit, observed_checkout_head=args.commit,
            previous_list_files_activation_saved=str(BACKUP / 'activated.before.json'))
        updated['services'] = dict(activation['services'], retrieval=dict(retrieval_entry,
            pid=process.pid, create_time=now.create_time(), cmdline=now.cmdline()))
        guard.validate_services(updated)
        save(activation_path, updated)
        assert set(after['paths']) == set(openapi_before['paths'])
        for path in after['paths']:
            if path != '/list_file_names':
                assert after['paths'][path] == openapi_before['paths'][path], 'unexpected_route_change'
        for name, model in openapi_before['components']['schemas'].items():
            if name != 'ListFileNamesRequest':
                assert after['components']['schemas'][name] == model, 'unexpected_schema_change'
        state.update(phase='checking', new_retrieval=updated['services']['retrieval'])
        save(BACKUP / 'state.json', state)
        state['acceptance'] = probe()
        guard.validate_services(updated)
        assert before_hashes == {name: digest(ROOT / name) for name in before_hashes}
        with urllib.request.urlopen('http://127.0.0.1:6000/health', timeout=8) as response:
            health = json.loads(response.read(100000))
        assert health['code'] == 0
        assert os.readlink('/proc/%s/fd/1' % process.pid) == str(log)
        assert log.stat().st_ino == log_before.st_ino
        with log.open('rb') as handle:
            handle.seek(log_before.st_size)
            recent = handle.read(1024 ** 2).decode('utf8', errors='replace')
        state.update(phase='healthy', healthy=True, off_task_unchanged=True, off_task_health_code=0,
            configurations_and_dirty_files_unchanged=True, log_bytes_added=log.stat().st_size-log_before.st_size,
            log_tracebacks=recent.count('Traceback (most recent call last)'),
            log_asgi_errors=recent.count('Exception in ASGI application'),
            new_children=[p.pid for p in now.children(recursive=True)],
            finished=datetime.datetime.now(datetime.timezone.utc).isoformat())
        save(BACKUP / 'state.json', state)
        print(json.dumps(state, ensure_ascii=False), flush=True)
    except Exception as exc:
        state.update(healthy=False, error_type=type(exc).__name__, reason=str(exc) if isinstance(exc, (AssertionError, RuntimeError)) else 'inspect_private_log')
        save(BACKUP / 'state.json', state)
        print(json.dumps({'phase': state['phase'], 'healthy': False, 'reason': state['reason']}), flush=True)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
