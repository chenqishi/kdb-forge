"""Offline knowledge and document deduplication entrypoint."""
import argparse
import json
import sys
from pathlib import Path

from kdb.retrieval.ingestion.conflict_jobs import estimate_tokens
from kdb.retrieval.ingestion.conflict_store import fingerprint
from kdb.retrieval.ingestion.conflict_runtime import build_job
from kdb.retrieval.ingestion.document_dedup import check_document, apply_document_matches, parsed_text


def read_records(path, kind, only_unchecked=True):
    with open(path, encoding='utf-8') as handle:
        while True:
            line = handle.readline(2 * 1024 * 1024 + 1)
            if not line:
                break
            if len(line) > 2 * 1024 * 1024:
                raise ValueError('JSONL record exceeds 2 MiB')
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get('data_type') != kind:
                raise ValueError('input must contain only the requested data_type')
            previous = row.get('dedup_check') or {}
            if only_unchecked and previous.get('status') == 'complete' and previous.get('fingerprint') == fingerprint(row):
                continue
            row['_offline'] = True
            yield row


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['knowledge', 'document'])
    parser.add_argument('--index', required=True)
    parser.add_argument('--config', help='dedup config; otherwise KDB_DEDUP_CONFIG')
    parser.add_argument('--search-config')
    parser.add_argument('--output', required=True, help='JSONL report (knowledge) or JSON report (document)')
    parser.add_argument('--journal')
    parser.add_argument('--data-type', choices=['qa', 'segment'])
    parser.add_argument('--input', help='new/uninserted knowledge JSONL')
    parser.add_argument('--since')
    parser.add_argument('--until')
    parser.add_argument('--unaudited', action='store_true')
    parser.add_argument('--task-id')
    parser.add_argument('--include-checked', action='store_true')
    parser.add_argument('--max-records', type=int, default=500)
    parser.add_argument('--policy', default='record_only')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--insert-new', action='store_true', help='insert retained offline records before applying replacements')
    parser.add_argument('--estimate-only', action='store_true')
    parser.add_argument('--file-name')
    parser.add_argument('--text-file', help='parsed text, or page JSON with --parsed-json')
    parser.add_argument('--parsed-json', action='store_true')
    parser.add_argument('--seed', type=int, default=0)
    args = parser.parse_args(argv)
    output = Path(args.output)
    artifacts = {output.resolve(), *(Path(str(output) + suffix).resolve()
                                    for suffix in ('.knowledge.jsonl', '.ready.jsonl', '.summary.json'))}
    if any(path and Path(path).resolve() in artifacts for path in (args.input, args.text_file, args.journal)):
        parser.error('outputs must differ from input, text and journal paths')
    if args.mode == 'knowledge':
        if not args.data_type or args.policy not in {'record_only', 'keep_new', 'keep_old'}:
            parser.error('knowledge mode requires --data-type and a knowledge policy')
        if not 1 <= args.max_records <= 10000:
            parser.error('--max-records must be 1..10000')
        if args.insert_new and (not args.input or args.policy == 'record_only'):
            parser.error('--insert-new requires --input and keep_new or keep_old')
    elif not args.file_name or not args.text_file or args.policy not in {'record_only', 'skip_new', 'replace_old'}:
        parser.error('document mode requires --file-name, --text-file and a document policy')
    job = build_job(args.index, config_path=args.config, search_config_path=args.search_config, journal=args.journal)
    output.parent.mkdir(parents=True, exist_ok=True)
    if args.mode == 'document':
        if not args.file_name or not args.text_file:
            parser.error('document mode requires --file-name and --text-file')
        path = Path(args.text_file)
        if path.stat().st_size > 32 * 1024 * 1024:
            raise ValueError('document text exceeds 32 MiB')
        with path.open(encoding='utf-8') as handle:
            text = parsed_text(json.load(handle)) if args.parsed_json else handle.read()
        report = check_document(job.store, job.models, args.file_name, text, seed=args.seed)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        report['actions'] = apply_document_matches(job.store, report, 'record_only' if args.dry_run else args.policy)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'status': report['status'], 'matches': len(report['matches']), 'usage': report['usage']}, ensure_ascii=False))
        return 0
    if not args.data_type:
        parser.error('knowledge mode requires --data-type')
    records = (read_records(args.input, args.data_type, not args.include_checked) if args.input else
               job.store.scan(args.data_type, since=args.since, until=args.until, unaudited=args.unaudited,
                    task_id=args.task_id, only_unchecked=not args.include_checked))
    if args.estimate_only:
        from itertools import islice
        try:
            rows = list(islice(records, args.max_records + 1))
        finally:
            records.close()
        estimates = [estimate_tokens(r, job.limit) for r in rows[:args.max_records]]
        report = {'estimated': True, 'records': len(estimates), 'selection_truncated': len(rows) > args.max_records,
                  'input_tokens': sum(e['input_tokens'] for e in estimates),
                  'output_tokens': sum(e['output_tokens'] for e in estimates)}
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    else:
        with output.open('w', encoding='utf-8') as handle:
            def emit(result):
                handle.write(json.dumps(result, ensure_ascii=False) + '\n')
                handle.flush()
            report = job.run(records, policy=args.policy, dry_run=args.dry_run,
                             insert_new=args.insert_new, max_records=args.max_records, sink=emit)
        offline = report.pop('offline_records')
        if args.input:
            with Path(str(output) + '.knowledge.jsonl').open('w', encoding='utf-8') as handle:
                for row in offline:
                    handle.write(json.dumps(row, ensure_ascii=False) + '\n')
            with Path(str(output) + '.ready.jsonl').open('w', encoding='utf-8') as handle:
                for row in offline:
                    if row.get('dedup_action') == 'retain' and row.get('dedup_check', {}).get('status') == 'complete':
                        handle.write(json.dumps(row, ensure_ascii=False) + '\n')
        Path(str(output) + '.summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False))
    return 2 if report.get('failed') else 3 if report.get('status') == 'partial' else 0


if __name__ == '__main__':
    sys.exit(main())
