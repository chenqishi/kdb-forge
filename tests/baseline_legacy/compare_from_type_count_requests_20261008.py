"""Independent contract comparison of the two actual request models; no clients."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/compare_from_type_count_requests_20261008.py')
import copy
import importlib.util
import json
import sys
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__legacy_source_file__).resolve().parents[1]


def run():
    new_root = Path('/root/kdb-forge-learning-count-20261008')
    sys.path.insert(0, str(new_root / 'src'))
    from kdb.api.search_routes import FromTypeCountRequest as NewRequest
    path = ROOT / 'knowledge_database_search_service/src/knowledge_database_search_es.py'
    spec = importlib.util.spec_from_file_location('_count_contract_actual_old', path)
    old = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = old
    spec.loader.exec_module(old)
    valid = [{}, {'index_name': ''}, {'index_name': None},
        {'indexName': 'mercado_local'}, {'index_name': 'mercado_local', 'indexName': 'mercado_local'},
        {'index_name': 'payoneer_olive'}, {'index_name': 'mercado_local', 'from_type': 'document'},
        {'index_name': 'mercado_local', 'from_type': ' chat_auto '},
        {'index_name': 'mercado_local', 'start': '2026-09-01 00:00:00'},
        {'index_name': 'mercado_local', 'end': '2026-09-30 23:59:59'},
        {'index_name': 'mercado_local', 'start': None, 'end': None},
        {'index_name': 'mercado_local', 'start': '0001-01-01 00:00:00', 'end': '2026-09-30 23:59:59'},
        {'index_name': 'mercado_local', 'start': '2026-09-30 23:59:59', 'end': '2026-09-01 00:00:00'},
    ]
    invalid = [{'index_name': 'mercado_local', 'indexName': 'payoneer_olive'},
        {'index_name': 'a,b'}, {'index_name': '*'}, {'index_name': 'a?'}, {'index_name': '_all'},
        {'index_name': '-mercado_local'}, {'index_name': '+mercado_local'}, {'index_name': '_hidden'},
        {'index_name': '.'}, {'index_name': '..'}, {'index_name': 'cluster:index'},
        {'index_name': 'a' * 256}, {'index_name': '中' * 86}, {'index_name': 123},
        {'from_type': None}, {'from_type': ''}, {'from_type': 42},
        {'start': '2026-02-30 00:00:00'}, {'start': '2026-09-01T00:00:00+08:00'},
        {'end': '2026-09-01'}, {'end': 1790841599}, {'start': '0000-01-01 00:00:00'},
        {'index_name': 'mercado_local', 'del_flag': 0},
    ]
    rows = []
    for expected, payloads in [(True, valid), (False, invalid)]:
        for payload in payloads:
            before = copy.deepcopy(payload)
            results = []
            for cls in (old.FromTypeCountRequest, NewRequest):
                try:
                    value = cls.model_validate(payload)
                    fields = {}
                    for field in ('index_name', 'from_type', 'start', 'end'):
                        raw = getattr(value, field)
                        fields[field] = raw.isoformat(sep=' ', timespec='seconds') if isinstance(raw, datetime) else raw
                    fields['index_name'] = fields['index_name'] or None
                    results.append({'accepted': True, 'fields': fields})
                except ValidationError:
                    results.append({'accepted': False})
            passed = results[0] == results[1] and results[0]['accepted'] == expected and payload == before
            rows.append({'input': payload, 'expected_accept': expected, 'old': results[0], 'new': results[1], 'passed': passed})
    return {'cases': len(rows), 'all_passed': all(row['passed'] for row in rows), 'results': rows}


def main():
    evidence = run()
    path = ROOT / 'docs/reviews/from_type_count_request_parity_20261008.json'
    path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'cases': evidence['cases'], 'passed': evidence['all_passed'],
                      'mismatches': [row for row in evidence['results'] if not row['passed']]}, ensure_ascii=False))
    if not evidence['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
