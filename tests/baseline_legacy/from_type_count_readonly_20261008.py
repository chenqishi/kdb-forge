"""Bounded real count validation; no lifespan, service restart, ES writes or embeddings."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/from_type_count_readonly_20261008.py')
import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

import httpx

from knowledge_interface_tools.search_index_data_interface import SearchDataInterface
from knowledge_interface_tools.es_search_interface import EsSearchInterface
from knowledge_interface_tools.es_count_utils import complete_count

SOURCE = Path('/root/knowledge_database_builder')
ROOT = Path(__legacy_source_file__).resolve().parents[1]


def load_service(engine):
    path = ROOT / 'knowledge_database_search_service/src/knowledge_database_search_es.py'
    spec = importlib.util.spec_from_file_location('_count_readonly_actual_service', path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    # Count needs only the real business method and engine; omit unrelated constructors.
    iface = SearchDataInterface.__new__(SearchDataInterface)
    iface.engine = engine
    module.SEARCH_DATA_INTERFACE = iface
    return module


async def run():
    spec = importlib.util.spec_from_file_location('_approved_count_raw_reader', SOURCE / 'tests/es817_independent_query_compare_20261005.py')
    reader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reader)
    clients = reader.make_clients()
    engine = None
    evidence = {'captured_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'mode': 'actual isolated ASGI handler/business/factory/ES8; no lifespan',
                'versions': {}, 'cases': [], 'writes': 0}
    evidence['implementation_sha256'] = {
        rel: hashlib.sha256((ROOT / rel).read_bytes()).hexdigest() for rel in (
            'knowledge_database_search_service/src/knowledge_database_search_es.py',
            'knowledge_interface_tools/search_index_data_interface.py',
            'knowledge_interface_tools/es_search_interface.py',
            'knowledge_interface_tools/es8_search_interface.py',
            'knowledge_interface_tools/es_count_utils.py',
        )
    }
    try:
        for provider, client in clients.items():
            version = reader.read_es(client, 'GET', '/')['version']['number']
            assert version.startswith('7.' if provider == 'old' else '8.17.'), 'Unexpected cluster version'
            evidence['versions'][provider] = version
        pairs = [('mercado_local', 'serverless'), ('payoneer_olive', 'paas')]
        for index, provider in pairs:
            for name in ('old', provider):
                reader.read_es(clients[name], 'HEAD', '/' + index)
        engine = EsSearchInterface(config_path=str(SOURCE / 'config/config_es_engine_es817.old.local.json'),
                                   index_name='mercado_local', es_version='8.17',
                                   extra_params={'ensure_index_on_init': False, 'auto_update_mapping': False})
        assert engine._impl.has_build_index == {}
        service = load_service(engine)
        parameters = [
            {}, {'from_type': 'chat_auto'}, {'from_type': 'document'},
            {'from_type': '__count_readonly_absent_20261008__'},
            {'start': '2026-09-01 00:00:00', 'end': '2026-10-08 23:59:59'},
            {'start': '2026-09-01 00:00:00'},
        ]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=service.app), base_url='http://inprocess.invalid') as client:
            for index, provider in pairs:
                assert engine._impl.router.resolve_provider(index) == provider
                for parameters_one in parameters:
                    payload = dict(parameters_one, index_name=index)
                    filters = [{'term': {'quality_level': 'high'}},
                               {'term': {'from_type': payload.get('from_type', 'chat_auto')}}]
                    if payload.get('start') and payload.get('end'):
                        filters.append({'range': {'insert_time': {'gte': payload['start'], 'lte': payload['end']}}})
                    query = {'bool': {'filter': filters}}
                    reference = reader.read_es(clients[provider], 'POST', '/' + index + '/_count', {'query': query})
                    old_reference = reader.read_es(clients['old'], 'POST', '/' + index + '/_count', {'query': query})
                    response = await client.post('/get_from_type_count', json=payload)
                    wire = response.json()
                    expected = complete_count(reference)
                    passed = response.status_code == 200 and wire == {'success': True, 'count': expected, 'message': ''}
                    evidence['cases'].append({'request': payload, 'provider': provider, 'query': query,
                        'http_status': response.status_code, 'response': wire,
                        'native_reference': expected, 'native_shards': reference['_shards'],
                        'old_native_reference': complete_count(old_reference), 'passed': passed})
                    await asyncio.sleep(0.15)
        evidence['all_passed'] = all(case['passed'] for case in evidence['cases'])
        assert engine._impl.has_build_index == {}, 'count must not ensure/create indexes'
        return evidence
    finally:
        if engine is not None:
            engine._impl.router.close()
        for client in clients.values():
            client.session.close()


def main():
    output = ROOT / 'docs/reviews/from_type_count_readonly_20261008'
    output.mkdir(mode=0o700, exist_ok=True)
    os.chmod(output, 0o700)
    evidence = asyncio.run(run())
    path = output / 'evidence.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    os.chmod(path, 0o600)
    print(json.dumps({'cases': len(evidence['cases']), 'passed': evidence['all_passed'], 'evidence': str(path)}))
    if not evidence['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
