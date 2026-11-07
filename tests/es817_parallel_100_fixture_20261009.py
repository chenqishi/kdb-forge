"""Preserve verified private inputs; no repeated retrieval or deployment."""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('tests/es817_parallel_100_fixture_20261009.py')
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from es817_parallel_100_20261009 import REMOTE

PREPARE = REMOTE.rsplit('\nremote_main()', 1)[0] + r'''
from knowledge_interface_tools.es8_search_interface import EsSearchInterfaceES8
logging.disable(logging.CRITICAL)
initial=snapshot()
cfg=json.loads((root/'config/config_es_engine_es817.online.json').read_text())
cfg['extra_params'].update(ensure_index_on_init=False,auto_update_mapping=False)
for p in cfg['providers'].values():p.update(max_retries=0,retry_on_timeout=False,request_timeout=15)
engine=EsSearchInterfaceES8(config=cfg,ensure_index=False)
try:
    for index in ['payoneer_olive','mercado']:trace_node(engine.get_client_by_index(index))
    cases,preflight=prepare_cases()
    print(json.dumps({'cases':cases,'preflight':preflight,'reads':calls,'before':initial,'after':snapshot()},allow_nan=False))
finally:engine.router.close()
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--private-output', type=Path, required=True)
    parser.add_argument('--summary', type=Path, required=True)
    args = parser.parse_args()
    expected = [json.loads(line) for line in args.cases.read_text().splitlines()]
    if len(expected) != 200:
        raise ValueError('complete 200-query evidence required')
    command = ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=8', 'shenzhen-120',
        'cd /root/knowledge_database_builder && PYTHONDONTWRITEBYTECODE=1 nice -n 15 .venv-es817/bin/python -c ' + shlex.quote(PREPARE)]
    result = subprocess.run(command, text=True, capture_output=True, timeout=100)
    if result.returncode:
        raise RuntimeError('readonly input recapture failed; do not overwrite evidence')
    actual = json.loads(result.stdout)
    by_case = {case['case']: case for case in actual['cases']}
    exact = []
    for row in expected:
        case = by_case.get(row['case'])
        if not case:
            continue
        keys = ['query_sha256', 'vector_sha256', 'indexes', 'top_k', 'search_type', 'use_synonyms', 'score_threshold']
        condition_sha = hashlib.sha256(json.dumps(case['condition'], ensure_ascii=False, sort_keys=True,
                                                   separators=(',', ':'), allow_nan=False).encode()).hexdigest()
        if all(row[key] == case[key] for key in keys) and condition_sha == row['condition_sha256']:
            exact.append(row['case'])
    unchanged = all(actual['before'][key] == actual['after'][key] for key in ['services', 'file_sha256'])
    with args.private_output.open('x') as handle:
        handle.write(json.dumps(actual['cases'], ensure_ascii=False, allow_nan=False))
    args.private_output.chmod(0o600)
    summary = {'expected': 200, 'recaptured': len(by_case), 'input_hash_matches': len(exact),
        'missing_or_changed': sorted(set(row['case'] for row in expected) - set(exact)),
        'readonly_ES_requests': actual['reads'], 'online_state_unchanged': unchanged, 'persistent_ES_writes': 0,
        'private_fixture_sha256': hashlib.sha256(args.private_output.read_bytes()).hexdigest(),
        'tool_sha256': hashlib.sha256(Path(__legacy_source_file__).read_bytes()).hexdigest()}
    with args.summary.open('x') as handle:
        handle.write(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary), flush=True)
    if len(exact) != 200 or not unchanged:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
