"""Bounded, read-only paired retrieval evaluation; no engine/config changes."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_independent_query_compare_20261005.py')
import argparse
import hashlib
import json
import os
import re
import time
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from commons.es_http_client import EsHttpClient, shard_failure_reason

ROOT = Path(__legacy_source_file__).resolve().parents[1]
PAIRS = {
    'mercado': ('mercado', 'mercado_mercado_local_admin', 'serverless'),
    'payoneer': ('payoneer', 'payoneer_payoneer', 'paas'),
    'payoneer_olive': ('payoneer_olive', 'payoneer_olive_payoneer_olive', 'paas'),
    'wayfair': ('wayfair', 'wayfair_wayfair_test2', 'serverless'),
    'mercado_local': ('mercado_local', 'mercado_local_mercado_local_admin', 'serverless'),
}
ALLOWED = {name for pair in PAIRS.values() for name in pair[:2]}
ENDPOINTS = {'old': 'http://120.77.147.247:8003/search', 'new': 'http://127.0.0.1:8003/search'}
HISTORY = {
    'mercado': [('发下入驻链接', 'tests/cases/wf_mercado_subflows_chat.md:21', 'existing_test_question'),
                ('我KYC上传一直失败，网页报错', 'tests/cases/wf_mercado_subflows_chat.md:34', 'existing_test_question'),
                ('我的KYC审核不通过怎么办', 'tests/cases/wf_mercado_subflows_chat.md:46', 'existing_test_question')],
    'payoneer': [('拉美活动', 'tests/cases/payoneer_workflow_chat.md:109', 'historical_regression_question'),
                 ('活动内容', 'tests/cases/payoneer_workflow_chat.md:111', 'context_dependent_historical_question'),
                 ('我想开通Payoneer收款账户', 'tests/cases/payoneer_onboarding_group_chat.md', 'existing_test_question')],
    'payoneer_olive': [('在Allegro平台，回款周期是多久一次？', 'docs/payoneer_olive_top_queries.md:109', 'historical_context_completed'),
                       ('在Noon平台入驻时填写的收款账户，后期可以修改吗？', 'docs/payoneer_olive_top_queries.md:151', 'historical_context_completed'),
                       ('TK 小店保证金能退到 P 卡吗', 'tests/cases/wf_payoneer_olive_chat.md:17', 'existing_test_question')],
    'wayfair': [('我们是不是还可以在Wayfair再注册几个店铺？你们能帮忙看下我们符合条件吗？', 'docs/payoneer_olive_top_queries.md:505', 'historical_context_completed'),
                ('要填Wayfair申请流程里的推荐码吗？', 'docs/payoneer_olive_top_queries.md:508', 'historical_context_completed'),
                ('用亚马逊英国站的企业信息可以吗？', 'docs/payoneer_olive_top_queries.md:516', 'historical_context_completed')],
    'mercado_local': [('入驻美客多需要什么材料？', 'tests/cases/wf_mercado_local_chat.md:47', 'historical_test_question_email_removed'),
                      ('我要入驻，我们各平台综合月均销售额200万美金', 'tests/cases/wf_mercado_local_chat.md:61', 'existing_test_question'),
                      ('我想入驻，目前月均销售额1万美金左右', 'tests/cases/wf_mercado_local_chat.md:73', 'existing_test_question')],
}


def make_clients():
    old = json.loads((ROOT / 'config/config_es_engine.json').read_text())
    new = json.loads((ROOT / 'config/config_es_engine_es817.old.local.json').read_text())['providers']
    clients = {}
    for label, cfg in [('old', old), *new.items()]:
        hosts = cfg['hosts']
        client = EsHttpClient([hosts] if isinstance(hosts, str) else hosts,
                              cfg.get('username'), cfg.get('password'), timeout=45)
        client.session.verify = cfg.get('verify_certs', True)
        client.session.mount('http://', HTTPAdapter(max_retries=0))
        client.session.mount('https://', HTTPAdapter(max_retries=0))
        clients[label] = client
    return clients


def read_es(client, method, path, body=None):
    route = path.split('?', 1)[0]
    parts = route.strip('/').split('/')
    allowed = method in {'GET', 'HEAD'} and (route == '/' or parts[0] in ALLOWED)
    if method == 'POST' and parts[0] in ALLOWED and isinstance(body, dict):
        allowed = parts[1:] == ['_count'] or (
            parts[1:] == ['_search'] and 0 <= body.get('size', 10) <= 60) or (
            parts[1:] == ['_mget'] and len(body.get('ids', [])) <= 40)
    if not allowed:
        raise ValueError('outside exact existing-index read-only scope')
    status, payload = client._request(method, path, body)
    if status != 200 or payload.get('error'):
        raise RuntimeError(f'read failed status={status} path={route}')
    if method == 'POST' and shard_failure_reason(payload):
        raise RuntimeError('partial read: ' + str(shard_failure_reason(payload)))
    return payload


def prepare(clients, output, titles=True):
    info = {'captured_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'versions': {}, 'indices': {}}
    for label, client in clients.items():
        version = read_es(client, 'GET', '/')['version']['number']
        if not version.startswith('7.' if label == 'old' else '8.17.'):
            raise ValueError('unexpected deployment version')
        info['versions'][label] = version
    samples = []
    for platform, (public, private, provider) in PAIRS.items():
        for name in [public, private]:
            info['indices'][name] = {}
            for label, client in [('old', clients['old']), ('new', clients[provider])]:
                read_es(client, 'HEAD', '/' + name)
                meta = read_es(client, 'GET', '/' + name)[name]
                count = read_es(client, 'POST', '/' + name + '/_count', {'query': {'match_all': {}}})['count']
                if count <= 0:
                    raise ValueError('empty index refused: ' + name)
                info['indices'][name][label] = {'count': count, 'stored_source': meta['mappings'].get('_source', {})}
        if not titles:
            continue
        for position, (query, source, kind) in enumerate(HISTORY[platform], 1):
            samples.append({'case': f'{platform}-H{position}', 'platform': platform, 'query': query,
                            'origin': '/root/sell_agents/' + source, 'sample_kind': kind})
        hits = read_es(clients['old'], 'POST', '/' + public + '/_search', {
            'size': 60, 'sort': ['_doc'], '_source': ['title', 'ext_info.from_file_name'],
            'query': {'bool': {'filter': [{'term': {'data_type': 'qa'}}, {'terms': {'audit_result': [1, 2]}}],
                               'must_not': [{'term': {'del_flag': 1}}]}}})['hits']['hits']
        valid, seen = [], set()
        for hit in hits:
            title = hit['_source'].get('title')
            if not isinstance(title, str) or not 8 <= len(title) <= 180 or title in seen or re.search(r'@|\d{11}', title):
                continue
            seen.add(title)
            valid.append(hit)
        if len(valid) < 3:
            raise ValueError('insufficient valid title controls')
        for position, hit in enumerate([valid[0], valid[len(valid)//2], valid[-1]], 1):
            samples.append({'case': f'{platform}-T{position}', 'platform': platform, 'query': hit['_source']['title'],
                            'sample_kind': 'old_qa_title_control', 'origin': {'dataset': public, 'id': hit['_id'],
                            'file': hit['_source'].get('ext_info', {}).get('from_file_name')}})
    (output / ('preflight.json' if titles else 'preflight_before_run.json')).write_text(json.dumps(info, ensure_ascii=False, indent=2))
    if titles:
        (output / 'samples.json').write_text(json.dumps(samples, ensure_ascii=False, indent=2))
    return info


def compare(old, new):
    identities = {}
    for label, values in [('old', old), ('new', new)]:
        keys = [(r.get('dataset'), r.get('id')) for r in values]
        if any(key[1] is None for key in keys) or len(set(keys)) != len(keys):
            raise ValueError('null-ID error sentinel or duplicate identity')
        identities[label] = keys
    a, b = identities['old'], identities['new']
    common = set(a) & set(b)
    deltas, changed, timestamps = [], [], []
    fields = ['q', 'a', 'content', 'ext_info', 'metadata', 'primary_category', 'synonyms_title']
    lookup = {key: value for key, value in zip(b, new)}
    for key, before in zip(a, old):
        if key not in common:
            continue
        after = lookup[key]
        delta = float(after['score']) - float(before['score'])
        deltas.append(abs(delta))
        different = [f for f in fields if before.get(f) != after.get(f)]
        if different:
            changed.append({'identity': key, 'fields': different})
        if any(before.get(f) != after.get(f) for f in ['insert_time', 'update_time']):
            timestamps.append(key)
    return {'old_count': len(a), 'new_count': len(b), 'exact_order': a == b,
            'same_set': set(a) == set(b), 'overlap': len(common),
            'same_position': sum(x == y for x, y in zip(a, b)),
            'top1_equal': a[:1] == b[:1], 'top5_equal': a[:5] == b[:5],
            'old_only': [x for x in a if x not in common], 'new_only': [x for x in b if x not in common],
            'common_body_changes': changed, 'common_timestamp_changes': timestamps,
            'max_common_score_delta': max(deltas, default=0)}


def run(clients, output):
    prepare(clients, output, titles=False)
    samples = json.loads((output / 'samples.json').read_text())
    if len(samples) != 30 or any(s['platform'] not in PAIRS for s in samples):
        raise ValueError('expected fixed30 sample')
    result = {'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'cases': []}
    session = requests.Session()
    try:
        for sample in samples:
            public, private, _ = PAIRS[sample['platform']]
            for kind, limit, names, condition in [
                ('qa', 20, private + ',' + public, [{'audit_result': [1, 2], 'data_type': ['qa']}]),
                ('segment', 5, public + ',' + private, [{'data_type': 'segment'}])]:
                body = {'text': sample['query'], 'search_type': kind, 'score_threshold': 0.4,
                        'top_k': limit, 'condition_dicts': condition, 'index_names': names, 'use_synonyms': True}
                row = {**sample, 'kind': kind, 'request': body, 'runs': {}}
                for label in (['old', 'new'] if len(result['cases']) % 2 == 0 else ['new', 'old']):
                    start = time.monotonic()
                    try:
                        response = session.post(ENDPOINTS[label], json=body, timeout=60)
                        response.raise_for_status()
                        payload = response.json()
                        if not isinstance(payload.get('results'), list):
                            raise ValueError('missing results')
                        row['runs'][label] = {'http_status': response.status_code, 'elapsed_s': round(time.monotonic()-start, 3),
                                              'response_bytes': len(response.content), 'results': payload['results']}
                    except Exception as exc:
                        row['runs'][label] = {'error_type': type(exc).__name__, 'elapsed_s': round(time.monotonic()-start, 3)}
                    time.sleep(0.15)
                if all('results' in row['runs'].get(label, {}) for label in ENDPOINTS):
                    try:
                        row['comparison'] = compare(row['runs']['old']['results'], row['runs']['new']['results'])
                    except ValueError as exc:
                        row['comparison_error'] = str(exc)
                result['cases'].append(row)
                (output / 'paired_responses.private.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
                print(json.dumps({'case': sample['case'], 'kind': kind, 'comparison': row.get('comparison'),
                                  'errors': {k: v.get('error_type') for k, v in row['runs'].items() if 'error_type' in v}}, ensure_ascii=False), flush=True)
        result['ended_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        (output / 'paired_responses.private.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
        summary = [{k: v for k, v in row.items() if k not in ['request', 'runs']} for row in result['cases']]
        (output / 'paired_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
    finally:
        session.close()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['prepare', 'run'], required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True, mode=0o700)
    clients = make_clients()
    try:
        baseline = {}
        for path in ['knowledge_interface_tools/es8_search_interface.py', 'knowledge_interface_tools/search_index_data_interface.py',
                     'knowledge_database_search_service/src/knowledge_database_search_es.py']:
            baseline[path] = hashlib.sha256((ROOT/path).read_bytes()).hexdigest()
        (args.output / 'implementation_hashes.json').write_text(json.dumps(baseline, indent=2))
        if args.phase == 'prepare':
            info = prepare(clients, args.output)
            print(json.dumps({'versions': info['versions'], 'counts': {k: {l:v['count'] for l,v in r.items()} for k,r in info['indices'].items()}}, ensure_ascii=False))
        else:
            run(clients, args.output)
    finally:
        for client in clients.values():
            client.session.close()


if __name__ == '__main__':
    main()
