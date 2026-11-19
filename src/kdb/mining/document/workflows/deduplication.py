"""Optional document duplicate stage using the existing retrieval bridge."""
import json
from collections import Counter
from pathlib import Path

from kdb.mining.bridges.retrieval import build_dedup_job, check_document_duplicate, apply_document_duplicates


def prepare_document_dedup(controller):
    options = controller.task_info.get('document_dedup')
    if not options or options.get('enabled', False) is not True:
        return True
    policy = options.get('policy', 'record_only')
    if policy not in {'record_only', 'skip_new', 'replace_old'}:
        raise ValueError('invalid document dedup policy')
    if policy == 'replace_old' and getattr(controller, 'review_only', False):
        raise ValueError('review_only cannot replace stored documents')
    job = build_dedup_job(controller.index_name, config_path=options.get('config_path'),
        search_config_path=options.get('search_config_path'),
        journal=Path(controller.data_dir) / 'document_dedup.journal.jsonl')
    kept, reports = [], []
    with open(controller.content_mapping_path, encoding='utf-8') as mapping:
        for line in mapping:
            if not line.strip():
                continue
            fields = line.rstrip('\n').split('\t')
            # Parser appends parse_save_dir/content.json to the original four columns.
            if len(fields) < 6:
                raise ValueError('invalid parsed document mapping')
            path = Path(fields[5])
            if path.stat().st_size > 32 * 1024 * 1024:
                raise ValueError('parsed document exceeds 32 MiB; split before duplicate check')
            with path.open(encoding='utf-8') as handle:
                parsed = json.load(handle)
            report = check_document_duplicate(job, fields[1], parsed, seed=options.get('seed', 0),
                name_check=options.get('name_check', True), content_check=options.get('content_check', True))
            reports.append(report)
            if not (policy == 'skip_new' and report['matches']):
                kept.append(line)
    output = Path(controller.data_dir) / 'document_dedup.report.json'
    output.write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding='utf-8')
    filtered = Path(controller.data_dir) / 'document_dedup.mapping.txt'
    filtered.write_text(''.join(kept), encoding='utf-8')
    controller.content_mapping_path = str(filtered)
    controller._document_dedup = {'job': job, 'reports': reports, 'policy': policy}
    controller._dedup_all_skipped = not kept
    return True


def finish_document_dedup(controller):
    state = getattr(controller, '_document_dedup', None)
    if not state or state['policy'] != 'replace_old':
        return True
    job = state['job']
    expected = Counter()
    for attr in ('search_data_file_path', 'segment_search_data_file_path'):
        value = getattr(controller, attr, None)
        if not value:
            continue
        with open(value, encoding='utf-8') as handle:
            for line in handle:
                if line.strip():
                    row = json.loads(line)
                    expected[((row.get('ext_info') or {}).get('from_file_name'), row['data_type'])] += 1
    actual = Counter()
    new_ids = set()
    for kind in ('qa', 'segment'):
        for row in job.store.scan(kind, task_id=controller.task_id, only_unchecked=False):
            actual[((row.get('ext_info') or {}).get('from_file_name'), kind)] += 1
            new_ids.add(row['_id'])
    if not expected or any(actual[key] < count for key, count in expected.items()):
        raise RuntimeError('new document insertion is incomplete; old documents were preserved')
    actions = []
    for report in state['reports']:
        if report['matches'] and not any(name == report['from_file_name'] for name, _ in expected):
            raise RuntimeError('replacement document produced no knowledge; old document was preserved')
        for match in report['matches']:
            match['records'] = [old for old in match['records'] if old['_id'] not in new_ids]
        actions.append(apply_document_duplicates(job, report, 'replace_old'))
    (Path(controller.data_dir) / 'document_dedup.actions.json').write_text(
        json.dumps(actions, ensure_ascii=False, indent=2), encoding='utf-8')
    return True
