"""Further bounded read-only category tests; never writes ES or application code."""
import argparse
import copy
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path

import requests

from es817_independent_query_compare_20261005 import ROOT, PAIRS, make_clients, read_es
from es817_category_filter_compare_20261008 import (
    SOURCE_FIELDS, capture_sources, field_values, matches, oracle_query,
    request_endpoint, resolve_sources,
)

TARGETS = {
    'mercado_local': ['业务地区-墨西哥', '业务地区-巴西', '默认分组', '服务商信息'],
    'payoneer_olive': ['TikTok Shop-墨西哥', 'TikTok Shop-印尼', 'TikTok Shop-东南亚',
                      'TikTok Shop-美国ACCU', 'TikTok Shop', 'Noon', 'Bol', 'Chewy',
                      'Walmart', '默认分组', 'eMAG'],
}
IMPLEMENTATION = ('knowledge_interface_tools/es8_search_interface.py',
                  'knowledge_interface_tools/search_index_data_interface.py',
                  'knowledge_database_search_service/src/knowledge_database_search_es.py')


def save(output, name, value):
    path = output / name
    if path.exists() and name not in {'progress.json', 'paired_responses.private.json',
                                     'condition_evidence.json', 'source_cache.private.json'}:
        raise ValueError('refuse replacing artifact: ' + name)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    path.chmod(0o600)


def preflight(clients, output):
    result = {'utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'indexes': {},
              'versions': {}, 'hashes': {}, 'git': {}, 'service': ''}
    for label, client in clients.items():
        version = read_es(client, 'GET', '/')['version']['number']
        if not version.startswith('7.' if label == 'old' else '8.17.'):
            raise ValueError('unexpected deployment version')
        result['versions'][label] = version
    for platform in TARGETS:
        public, private, provider = PAIRS[platform]
        for index in (public, private):
            result['indexes'][index] = {}
            for side, client in [('old', clients['old']), ('new', clients[provider])]:
                read_es(client, 'HEAD', '/' + index)
                mapping = read_es(client, 'GET', '/' + index)[index]['mappings']
                count = read_es(client, 'POST', '/' + index + '/_count', {'query': {'match_all': {}}})['count']
                result['indexes'][index][side] = {'mapping': mapping, 'count': count}
    result['hashes'] = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in IMPLEMENTATION}
    for key, command in [('branch', ['git', 'branch', '--show-current']), ('head', ['git', 'rev-parse', 'HEAD']),
                         ('status', ['git', 'status', '--short'])]:
        result['git'][key] = subprocess.check_output(command, cwd=ROOT, text=True).strip()
    result['service'] = subprocess.check_output(['systemctl', 'show', 'knowledge-database-search.service',
                                                '-p', 'MainPID', '-p', 'ActiveState', '-p', 'ActiveEnterTimestamp'], text=True)
    save(output, 'preflight.json', result)
    return result


def discover(clients, meta, output):
    discovery, fixtures = {}, []
    for platform, paths in TARGETS.items():
        public, private, provider = PAIRS[platform]
        discovery[platform] = {}
        for index in (public, private):
            discovery[platform][index] = {}
            for side, client in [('old', clients['old']), ('new', clients[provider])]:
                aggs = {field: {'terms': {'field': 'primary_category.' + field, 'size': 60}}
                        for field in ('category_path', 'cate1_id', 'cate2_id')}
                aggs.update({field: {'filter': {'exists': {'field': 'primary_category.' + field}}}
                             for field in ('cate3_id', 'cate4_id')})
                aggs['missing_category'] = {'filter': {'bool': {'must_not': [
                    {'exists': {'field': 'primary_category.category_ids'}}]}}}
                response = read_es(client, 'POST', '/' + index + '/_search', {
                    'size': 0, 'track_total_hits': True,
                    'query': {'term': {'del_flag': 0}}, 'aggs': aggs})
                discovery[platform][index][side] = {'total': response['hits']['total'], 'aggs': response['aggregations']}
        for path in paths:
            fixture = None
            for reviewed in (True, False):
                for index in (public, private):
                    filters = [{'term': {'primary_category.category_path': path}}, {'term': {'del_flag': 0}}]
                    if reviewed:
                        filters.extend([{'term': {'data_type': 'qa'}}, {'terms': {'audit_result': [1, 2, -1]}}])
                    hits = read_es(clients['old'], 'POST', '/' + index + '/_search', {
                        'size': 1, 'sort': ['_doc'], '_source': SOURCE_FIELDS,
                        'query': {'bool': {'filter': filters}}})['hits']['hits']
                    if hits:
                        fixture = {'platform': platform, 'path': path, 'reviewed_qa': reviewed, 'fixture': hits[0]}
                        break
                if fixture:
                    break
            if fixture:
                fixtures.append(fixture)
    save(output, 'discovery.json', discovery)
    save(output, 'fixtures.private.json', fixtures)
    return discovery, fixtures


def build_cases(discovery, fixtures):
    definitions = []
    for fixture in fixtures:
        platform, path, hit = fixture['platform'], fixture['path'], fixture['fixture']
        source = hit['_source']
        category = source['primary_category']
        leaf = category['category_ids'][-1]
        title = source.get('title')
        if not isinstance(title, str) or not 2 <= len(title) <= 240 or '@' in title:
            continue
        base = {'category_ids': leaf, 'data_type': source.get('data_type', 'qa')}
        if 'audit_result' in source:
            base['audit_result'] = source['audit_result']
        kind = 'segment' if source.get('data_type') == 'segment' else 'qa'
        origin = {'index': hit['_index'], 'id': hit['_id'], 'type': 'existing_source_title', 'path': path}
        definitions.append((platform, 'search', kind, 'title_control-' + path, [base], [base], title, 5, 1, origin))
        definitions.append((platform, 'web_search', 'web', 'text_path-' + path,
                            [{'category_path': path}], [{'category_path': path}], title, 5, 1, origin))
    for platform in TARGETS:
        choices = [row for row in fixtures if row['platform'] == platform]
        paths = ('业务地区-墨西哥', '业务地区-巴西') if platform == 'mercado_local' else ('TikTok Shop-墨西哥', 'TikTok Shop-印尼')
        left, right = [next(row for row in choices if row['path'] == path) for path in paths]
        a, b = left['fixture']['_source']['primary_category'], right['fixture']['_source']['primary_category']
        first, second, parent = a['category_ids'][-1], b['category_ids'][-1], a['cate1_id']
        query = '入驻美客多需要什么材料？' if platform == 'mercado_local' else 'TK 小店保证金能退到 P 卡吗'
        provenance = {'type': 'existing_historical_question', 'source':
                      '/root/sell_agents/tests/cases/wf_mercado_local_chat.md:47' if platform == 'mercado_local'
                      else '/root/sell_agents/tests/cases/wf_payoneer_olive_chat.md:17'}
        variants = [
            ('parent_id', [{'category_ids': parent}]),
            ('parent_level_field', [{'cate1_id': parent}]),
            ('parent_path_exact', [{'category_path': a['cate1_name']}]),
            ('child_numeric_id', [{'category_ids': int(first)}]),
            ('two_child_ids_anyof', [{'category_ids': [first, second]}]),
            ('parent_child_ids_anyof', [{'category_ids': [parent, first]}]),
            ('parent_and_child', [{'cate1_id': parent, 'cate2_id': first}]),
            ('child_and_other_parent_negative', [{'cate2_id': first, 'cate1_id': '__absent_category_20261008__'}]),
            ('two_child_branches_or', [{'category_ids': first}, {'category_ids': second}]),
            ('id_and_different_path_negative', [{'category_ids': first, 'category_path': b['category_path']}]),
            ('empty_id_list_negative', [{'category_ids': []}]),
            ('missing_id_negative', [{'category_ids': '__absent_category_20261008__'}]),
        ]
        for name, groups in variants:
            definitions.append((platform, 'web_search', 'web', name, groups, groups, '', 10, 1, provenance))
            if name in {'two_child_ids_anyof', 'parent_and_child', 'two_child_branches_or', 'id_and_different_path_negative', 'empty_id_list_negative'}:
                constrained = [{**group, 'data_type': 'qa', 'audit_result': [1, 2]} for group in groups]
                definitions.append((platform, 'search', 'qa', name, constrained, constrained, query, 5, 1, provenance))
        for name, groups, expected in [
            ('names_parent', [{'category_names': a['cate1_name']}], [{'category_ids': parent}]),
            ('names_two_complete_paths', [{'category_names': [a['category_path'], b['category_path']]}], [{'category_ids': [first, second]}]),
            ('names_plus_ids_union', [{'category_names': a['category_path'], 'category_ids': second}], [{'category_ids': [first, second]}]),
        ]:
            definitions.append((platform, 'web_search', 'web', name, groups, expected, query, 5, 1, provenance))
        for path in ('默认分组', '服务商信息') if platform == 'mercado_local' else ('eMAG',):
            if not any(row['path'] == path for row in choices):
                continue
            for page in (1, 2):
                definitions.append((platform, 'web_search', 'web', 'small_page-' + path + '-' + str(page),
                                    [{'category_path': path}], [{'category_path': path}], '', 5, page, provenance))
        for name, groups in [
            ('audit_one', [{'category_ids': first, 'data_type': 'qa', 'audit_result': 1}]),
            ('explicit_deleted', [{'category_ids': first, 'del_flag': 1}]),
            ('qa_segment_union', [{'category_ids': first, 'data_type': ['qa', 'segment'], 'audit_result': [1, 2, -1]}]),
        ]:
            definitions.append((platform, 'web_search', 'web', name, groups, groups, '', 10, 1, provenance))
        filename = left['fixture']['_source'].get('ext_info', {}).get('from_file_name')
        if filename:
            groups = [{'category_ids': first, 'from_file_name': filename}]
            definitions.append((platform, 'web_search', 'web', 'text_file_and_category', groups, groups,
                                left['fixture']['_source']['title'], 10, 1,
                                {'type': 'existing_source_title', 'index': left['fixture']['_index'], 'id': left['fixture']['_id']}))
    cases = []
    for platform, endpoint, kind, name, groups, expected, text, size, page, origin in definitions:
        public, private, _ = PAIRS[platform]
        body = {'text': text, 'index_names': private + ',' + public if endpoint == 'search' else public + ',' + private,
                'condition_dicts': groups, 'score_threshold': -1}
        if endpoint == 'search':
            body.update({'search_type': kind, 'top_k': size, 'use_synonyms': True})
        else:
            body.update({'client': platform, 'page_size': size, 'page_num': page})
        cases.append({'case': platform + '-' + kind + '-' + name, 'platform': platform, 'endpoint': endpoint,
                      'kind': kind, 'variant': name, 'request': body, 'expected_groups': expected,
                      'query_origin': origin})
    if not 1 <= len(cases) <= 105 or len({case['case'] for case in cases}) != len(cases):
        raise ValueError('invalid bounded matrix')
    return cases


def membership_query(case, mapping):
    filters = oracle_query(case['expected_groups'], case['endpoint'], mapping)
    text = case['request']['text']
    if case['endpoint'] != 'web_search' or not text:
        return filters
    return {'bool': {'filter': [filters], 'minimum_should_match': 1, 'should': [
        {'multi_match': {'query': text, 'fields': ['title^2', 'content^1.5', 'indexes.text'],
                         'type': 'best_fields', 'tie_breaker': 0.3}},
        {'match': {'synonyms_title': {'query': text, 'boost': 1.8}}},
    ]}}


def evaluate(case, runs, clients, meta, caches, counts):
    platform = case['platform']
    public, private, provider = PAIRS[platform]
    result, identities = {}, {}
    for side, client in [('old', clients['old']), ('new', clients[provider])]:
        values, pool, count = {}, [], 0
        for index in (public, private):
            query = membership_query(case, meta['indexes'][index][side]['mapping'])
            key = json.dumps([side, index, query], sort_keys=True, ensure_ascii=False)
            if key not in counts:
                counts[key] = read_es(client, 'POST', '/' + index + '/_count', {'query': query})['count']
            values[index] = counts[key]
            count += counts[key]
            if case['endpoint'] == 'web_search' and not case['request']['text'] and 0 < counts[key] <= 30:
                hits = read_es(client, 'POST', '/' + index + '/_search', {
                    'size': counts[key], '_source': SOURCE_FIELDS, 'query': query})['hits']['hits']
                pool.extend((index, hit['_id']) for hit in hits)
        check = {'native_matching_count': count, 'physical_counts': values, 'checked_hits': 0,
                 'violations': [], 'unresolved': [], 'ambiguous': [], 'pool_complete': len(pool) == count,
                 'membership_pool': pool if len(pool) == count else None}
        result[side] = check
        if 'response' not in runs[side]:
            check['service_error'] = runs[side]
            continue
        response, returned = runs[side]['response'], []
        rows = response['results']
        ids = [row.get('id') if case['endpoint'] == 'search' else row.get('_id') or row.get('id') for row in rows]
        sources = capture_sources(client, (public, private), ids, caches[(side, platform)])
        identities[side] = [(row.get('dataset'), identifier) for row, identifier in zip(rows, ids)]
        for row, identifier in zip(rows, ids):
            options = resolve_sources(row, sources[identifier])
            if not options:
                check['unresolved'].append(identifier)
                continue
            verdicts = [matches({**option['source'], '_id': identifier}, case['expected_groups'], case['endpoint']) for option in options]
            if len(set(verdicts)) > 1:
                check['ambiguous'].append(identifier)
            elif not any(verdicts):
                check['violations'].append({'id': identifier, 'sources': options})
            check['checked_hits'] += 1
            if len(options) == 1:
                returned.append((options[0]['index'], identifier))
        check.update({'returned_count': len(rows), 'returned_physical': returned,
                      'zero_despite_members': not rows and count > 0})
        if case['endpoint'] == 'web_search':
            check['actual_total'] = response['total_count']
            check['total_correct'] = response['total_count'] == count
            check['current_count_correct'] = response['current_count'] == len(rows)
            check['within_page_size'] = len(rows) <= case['request']['page_size']
            check['small_complete_request'] = bool(count and len(pool) == count and
                                                  case['request']['page_num'] == 1 and case['request']['page_size'] >= count)
            if check['small_complete_request']:
                check['complete_id_set'] = set(returned) == set(pool)
    if len(identities) == 2:
        a, b = identities['old'], identities['new']
        result['comparison'] = {'same_order': a == b, 'same_set': set(a) == set(b),
                                'same_top1': a[:1] == b[:1], 'overlap': len(set(a) & set(b))}
    return result


def run(clients, output, cases):
    if (output / 'paired_responses.private.json').exists():
        raise ValueError('refuse replacing previous run')
    meta = json.loads((output / 'preflight.json').read_text())
    caches = {(side, platform): {} for side in ('old', 'new') for platform in TARGETS}
    raw, checks, counts = [], [], {}
    with requests.Session() as session:
        for position, case in enumerate(cases):
            platform = case['platform']
            public, private, provider = PAIRS[platform]
            replies = {}
            for side in ('old', 'new') if position % 2 == 0 else ('new', 'old'):
                client = clients['old' if side == 'old' else provider]
                for index in (public, private):
                    read_es(client, 'HEAD', '/' + index)
                replies[side] = request_endpoint(session, side, case['endpoint'], copy.deepcopy(case['request']))
                time.sleep(0.15)
            raw.append({**case, 'runs': replies})
            save(output, 'paired_responses.private.json', raw)
            evaluated = evaluate(case, replies, clients, meta, caches, counts)
            checks.append({**case, 'checks': evaluated})
            save(output, 'condition_evidence.json', checks)
            save(output, 'source_cache.private.json', {side + ':' + platform: values
                 for (side, platform), values in caches.items()})
            save(output, 'progress.json', {'completed_pairs': len(checks), 'total_pairs': len(cases), 'last_case': case['case']})
            print(json.dumps({'done': len(checks), 'case': case['case'], 'checks': {side: {
                'count': values['native_matching_count'], 'returned': values.get('returned_count'),
                'violations': len(values['violations']), 'unresolved': len(values['unresolved']),
                'ambiguous': len(values['ambiguous']), 'error': bool(values.get('service_error')),
                'web_total_correct': values.get('total_correct')}
                for side, values in evaluated.items() if side != 'comparison'},
                'comparison': evaluated.get('comparison')}, ensure_ascii=False), flush=True)
    statistics = {'new_pairs': len(checks), 'new_service_requests': len(checks) * 2,
                  'by_platform': {}, 'sides': {}}
    for platform in TARGETS:
        statistics['by_platform'][platform] = sum(row['platform'] == platform for row in checks)
    for side in ('old', 'new'):
        values = [row['checks'][side] for row in checks]
        statistics['sides'][side] = {
            'service_errors': sum(bool(value.get('service_error')) for value in values),
            'checked_hits': sum(value['checked_hits'] for value in values),
            'violations': sum(len(value['violations']) for value in values),
            'unresolved': sum(len(value['unresolved']) for value in values),
            'ambiguous': sum(len(value['ambiguous']) for value in values),
            'web_total_mismatch': sum(not value['total_correct'] for value in values if 'total_correct' in value),
            'zero_despite_members': sum(value.get('zero_despite_members', False) for value in values),
        }
    after = {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in IMPLEMENTATION}
    statistics['before_hashes'] = meta['hashes']
    statistics['after_hashes'] = after
    statistics['implementation_unchanged'] = meta['hashes'] == after
    save(output, 'statistics.json', statistics)
    save(output, 'native_counts.json', counts)
    print(json.dumps(statistics, ensure_ascii=False), flush=True)


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--phase', choices=['prepare', 'run'], required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, exist_ok=True)
    clients = make_clients()
    try:
        if args.phase == 'prepare':
            meta = preflight(clients, args.output)
            discovery, fixtures = discover(clients, meta, args.output)
            cases = build_cases(discovery, fixtures)
            save(args.output, 'matrix.json', cases)
            print(json.dumps({'prepared_pairs': len(cases), 'fixture_categories':
                             [(item['platform'], item['path']) for item in fixtures]}, ensure_ascii=False))
        else:
            run(clients, args.output, json.loads((args.output / 'matrix.json').read_text()))
    finally:
        for client in clients.values():
            client.session.close()


if __name__ == '__main__':
    main()
