"""Bounded real auto-create verification in the previously authorized synthetic scope."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es8_autocreate_live_20261005.py')
import argparse
import asyncio
import copy
import hashlib
import importlib.util
import json
import logging
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import elasticsearch
import httpx
import numpy as np
from requests.adapters import HTTPAdapter

from commons.es_http_client import EsHttpClient, shard_failure_reason
from commons.embedding_tools import AliEmbedding
from commons.simility_tools import cosine_similarity
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
from knowledge_interface_tools.es_search_interface import EsSearchInterface
from knowledge_interface_tools.search_index_data_interface import SearchDataInterface

ROOT = Path(__legacy_source_file__).resolve().parents[1]
SERVICE_CONFIG = Path('/root/knowledge_database_builder/config/config_for_search_index_es817.local.json')
RUNTIME = Path('/root/kdb-forge/config/config_es_runtime.local.json')
NAMES = ['codex_source_probe_20261004_63a68e52aebb_a', 'codex_source_probe_20261004_63a68e52aebb_b']
DOC_ID = 'source-probe'
OWNER = '63a68e52aebb'
TITLE = 'Codex synthetic CRUD fixture 63a68e52aebb'


class AutoProbe:
    def __init__(self, provider):
        cfg = json.loads(RUNTIME.read_text())['providers'][provider]
        hosts = cfg['hosts']
        self.client = EsHttpClient([hosts] if isinstance(hosts, str) else hosts,
                                   cfg.get('username'), cfg.get('password'), timeout=20)
        self.client.session.verify = cfg.get('verify_certs', True)
        self.client.session.mount('http://', HTTPAdapter(max_retries=0))
        self.client.session.mount('https://', HTTPAdapter(max_retries=0))
        self.owned = {}
        self.absent = set()
        self.started = int(time.time() * 1000)
        self.requests = []
        self.vector = None

    def request(self, method, path, body=None, missing=False):
        route = path.split('?', 1)[0]
        parts = route.strip('/').split('/')
        read = method in {'GET', 'HEAD'} and (route == '/' or parts[0] in NAMES)
        read = read or (method == 'POST' and parts[0] in NAMES and parts[1:] == ['_search']
                        and isinstance(body, dict) and 0 <= body.get('size', 0) <= 2)
        mutation = (parts[0] in NAMES and method == 'PUT' and parts[1:] in [[], ['_doc', DOC_ID]])
        mutation = mutation or (parts[0] in NAMES and method == 'DELETE' and parts[1:] == [] and parts[0] in self.owned)
        if not (read or mutation) or 'script' in json.dumps(body or {}):
            raise ValueError('outside exact synthetic auto-create verification scope')
        status, response = self.client._request(method, path, body)
        self.requests.append({'method': method, 'path': route, 'status': status})
        if missing and status == 404:
            return None
        if status not in {200, 201} or response.get('error'):
            raise RuntimeError('synthetic request failed: status=%s' % status)
        if method == 'POST' and shard_failure_reason(response):
            raise ValueError('partial synthetic read')
        return response

    def claim(self, mapping):
        for name in NAMES:
            if self.request('GET', '/' + name, missing=True) is not None:
                raise ValueError('preexisting fixture retained')
            self.absent.add(name)
        version = self.request('GET', '/')['version']['number']
        if not version.startswith('8.17.'):
            raise ValueError('not an ES8.17 provider')
        mapping = copy.deepcopy(mapping)
        mapping['_meta'] = {'codex_source_probe_owner': OWNER}
        result = self.request('PUT', '/' + NAMES[0], {
            'settings': {'number_of_shards': 1}, 'mappings': mapping})
        if result.get('acknowledged') is not True:
            raise ValueError('creation not acknowledged')
        self.capture(NAMES[0])
        return version

    def capture(self, name):
        if name not in self.absent:
            raise ValueError('fixture was not absent before this run')
        row = self.request('GET', '/' + name)[name]
        index = row['settings']['index']
        if row.get('aliases') or (index.get('creation_date') is not None and int(index['creation_date']) < self.started - 2000):
            raise ValueError('fixture identity/creation window changed')
        mapping = row['mappings']
        if name == NAMES[0] and mapping.get('_meta', {}).get('codex_source_probe_owner') != OWNER:
            raise ValueError('public fixture owner changed')
        index_uuid = self.uuid(name, row)
        props = mapping['properties']
        for field in ['indexes', 'image_indexes']:
            vector = props[field]['properties']['embedding']
            if props[field]['type'] != 'nested' or vector.get('index') is not True or vector['dims'] != 1024:
                raise ValueError('invalid automatically-created nested mapping')
        if mapping.get('_source', {}).get('excludes') or mapping.get('_source', {}).get('enabled') is False:
            raise ValueError('pruned automatic source')
        self.owned[name] = index_uuid
        return {'uuid': index_uuid, 'native_mapping': True, 'stored_source_unpruned': True}

    def uuid(self, name, row):
        value = row.get('settings', {}).get('index', {}).get('uuid')
        if not value:
            stats = self.request('GET', '/' + name + '/_stats/docs?filter_path=indices.*.uuid')
            if set(stats.get('indices', {})) != {name}:
                raise ValueError('UUID stats identity mismatch')
            value = stats['indices'][name].get('uuid')
        if not isinstance(value, str) or not value:
            raise ValueError('UUID unavailable; preserve')
        return value

    def write(self, kind):
        if NAMES[0] not in self.owned:
            raise ValueError('public fixture not owned')
        doc = {'content': TITLE, 'data_type': kind, 'del_flag': 0, 'audit_result': 2,
               'indexes': [{'text': TITLE, 'embedding': self.vector}],
               'content_embedding': self.vector,
               'ext_info': {'synthetic_owner': OWNER, 'from_file_name': 'synthetic.txt'}}
        if kind == 'qa':
            doc.update(title=TITLE, title_embedding=self.vector)
        self.request('PUT', '/' + NAMES[0] + '/_doc/' + DOC_ID + '?refresh=true', doc)
        actual = self.request('GET', '/' + NAMES[0] + '/_doc/' + DOC_ID)['_source']
        if actual != doc:
            raise ValueError('synthetic full stored source differs; preserve evidence')
        return {'step': 'full_stored_source', 'kind': kind, 'passed': True,
                'root_content_dims': len(actual['content_embedding']),
                'nested_dims': len(actual['indexes'][0]['embedding'])}

    def cleanup(self):
        outcome = []
        for name in reversed(NAMES):
            if name not in self.owned:
                continue
            row = self.request('GET', '/' + name)[name]
            if row.get('aliases') or self.uuid(name, row) != self.owned[name]:
                raise ValueError('fixture UUID/alias changed; preserve')
            response = self.request('POST', '/' + name + '/_search', {
                'size': 2, 'track_total_hits': True,
                '_source': ['ext_info.synthetic_owner'], 'query': {'match_all': {}}})
            hits = response['hits']['hits']
            total = response['hits']['total']['value']
            if total != len(hits) or total > (1 if name == NAMES[0] else 0):
                raise ValueError('foreign fixture document count; preserve')
            if any(h['_id'] != DOC_ID or h.get('_routing') is not None or
                   h['_source'].get('ext_info', {}).get('synthetic_owner') != OWNER for h in hits):
                raise ValueError('foreign fixture document; preserve')
            result = self.request('DELETE', '/' + name)
            if result.get('acknowledged') is not True or self.request('GET', '/' + name, missing=True) is not None:
                raise ValueError('cleanup not confirmed')
            outcome.append({'index': name, 'status': 'owned_deleted_verified_404'})
        return outcome


async def post_checks(client, probe, report):
    async with client:
        for kind in ['qa', 'segment']:
            report['checks'].append(probe.write(kind))
            for endpoint in ['/search', '/web_search']:
                for names in [NAMES[::-1], NAMES]:
                    request = {'text': TITLE, 'index_names': ','.join(names), 'search_type': kind,
                               'condition_dicts': [{'data_type': kind, 'audit_result': [1, 2]}],
                               'top_k': 3, 'page_size': 3, 'score_threshold': -1, 'use_synonyms': True}
                    response = await client.post(endpoint, json=request)
                    wire = response.json()
                    hits = wire.get('results', [])
                    id_field = 'id' if endpoint == '/search' else '_id'
                    ok = response.status_code == 200 and len(hits) == 1 and hits[0].get(id_field) == DOC_ID
                    ok = ok and hits[0].get('ext_info', {}).get('synthetic_owner') == OWNER
                    ok = ok and not hits[0].get('error') and hits[0].get('q') != '检索结果错误'
                    identity_ok = ok
                    score = hits[0].get('score') if hits else None
                    score_ok = isinstance(score, (int, float)) and math.isfinite(score) and score > 0
                    if endpoint == '/search':
                        ok = ok and score_ok
                    report['checks'].append({'kind': kind, 'endpoint': endpoint,
                        'private_first': names[0] == NAMES[1], 'status': response.status_code,
                        'count': len(hits), 'valid_id_and_metadata': identity_ok,
                        'score': score, 'positive_finite_score': score_ok, 'passed': ok})
                    if NAMES[1] not in probe.owned:
                        report['automatic_private'] = probe.capture(NAMES[1])
        for endpoint in ['/search', '/web_search']:
            response = await client.post(endpoint, json={'text': TITLE, 'index_names': NAMES[1],
                                                        'top_k': 3, 'page_size': 3, 'score_threshold': -1})
            wire = response.json()
            report['checks'].append({'kind': 'empty_private', 'endpoint': endpoint,
                'status': response.status_code, 'count': len(wire.get('results', [])),
                'passed': response.status_code == 200 and wire.get('results') == []})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--phase', choices=['isolated', 'running'], required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    if not args.execute or elasticsearch.__version__[:2] != (8, 17):
        parser.error('explicit authorized execution and existing ES8.17 runtime required')
    output = Path(args.output)
    if output.exists():
        parser.error('preserve existing evidence')
    logging.disable(logging.CRITICAL)
    config = json.loads(RUNTIME.read_text())
    report = {'phase': args.phase, 'phases': [], 'source_SHA256': hashlib.sha256(
        (ROOT/'knowledge_interface_tools/es8_search_interface.py').read_bytes()).hexdigest(),
        'scope': {'names': NAMES, 'doc_id': DOC_ID, 'no_business_staging_writes': True},
        'embedding_boundary': 'matched synthetic unit vectors for isolated; configured real model fixture and real service query embedding for running'}
    for provider in (['serverless', 'paas'] if args.phase == 'isolated' else ['serverless']):
        row = {'provider': provider, 'checks': []}
        report['phases'].append(row)
        probe = AutoProbe(provider)
        factory = None
        try:
            # A controlled legal vector keeps this auto-create fixture independent
            # of any preexisting document's stored-source completeness.
            probe.vector = [1.0] + [0.0] * 1023
            if args.phase == 'running':
                service_config = json.loads(SERVICE_CONFIG.read_text())
                vector = AliEmbedding(service_config['embedding_config_path']).text2embedding(TITLE)
                if vector.shape != (1024,) or not np.isfinite(vector).all() or np.linalg.norm(vector) == 0:
                    raise ValueError('invalid real fixture embedding')
                row['fixture_embedding'] = {'dims': 1024, 'model_method_calls': 1,
                    'discarded_unit_fixture_cosine': float(cosine_similarity(vector, probe.vector)),
                    'same_title_real_model': True}
                probe.vector = vector.tolist()
            cfg = copy.deepcopy(config)
            cfg['index_name'] = NAMES[0]
            cfg['index_routes'] = {name: provider for name in NAMES}
            cfg['extra_params'] = dict(cfg['extra_params'], ensure_index_on_init=False, auto_update_mapping=False)
            definition = EsSearchInterfaceES8(config=cfg)
            try:
                row['version'] = probe.claim(definition._build_mapping())
            finally:
                definition.close()
            if args.phase == 'isolated':
                cfg['extra_params']['ensure_index_on_init'] = True
                with tempfile.TemporaryDirectory(prefix='old_autocreate_') as directory:
                    path = Path(directory)/'engine.json'
                    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                    with os.fdopen(descriptor, 'w') as handle:
                        json.dump(cfg, handle)
                    factory = EsSearchInterface(config_path=str(path))
                    assert isinstance(factory._impl, EsSearchInterfaceES8)
                    iface = SearchDataInterface(search_engine=factory, config_path=str(SERVICE_CONFIG))
                    iface.embedding_tools.text2embedding = Mock(return_value=np.asarray(probe.vector))
                    service_path = ROOT/'knowledge_database_search_service/src/knowledge_database_search_es.py'
                    spec = importlib.util.spec_from_file_location('_actual_old_autocreate_live', service_path)
                    service = importlib.util.module_from_spec(spec)
                    sys.modules[spec.name] = service
                    spec.loader.exec_module(service)
                    service.SEARCH_DATA_INTERFACE = iface
                    logging.disable(logging.CRITICAL)
                    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app),
                                               base_url='http://isolated.invalid', timeout=30)
                    asyncio.run(post_checks(client, probe, row))
            else:
                asyncio.run(post_checks(httpx.AsyncClient(base_url='http://127.0.0.1:8003', timeout=40), probe, row))
            row['passed'] = all(item['passed'] for item in row['checks'])
        except Exception as exc:
            row.update(passed=False, error_type=type(exc).__name__)
        finally:
            try:
                row['cleanup'] = probe.cleanup()
            except Exception as exc:
                row.update(passed=False, cleanup_error_type=type(exc).__name__)
            row['requests'] = probe.requests
            if factory is not None:
                factory.close()
            probe.client.session.close()
        print(json.dumps({'provider': provider, 'passed': row.get('passed'),
                          'checks': len(row['checks']), 'error': row.get('error_type'),
                          'cleanup': row.get('cleanup')}), flush=True)
    report['passed'] = all(phase.get('passed') for phase in report['phases'])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
