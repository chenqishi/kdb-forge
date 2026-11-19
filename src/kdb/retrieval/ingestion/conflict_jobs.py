"""Incremental deduplication orchestration shared by CLI and leader tools."""
import copy
import math
from datetime import datetime, timezone
from itertools import islice

from kdb.retrieval.ingestion.conflict_check import compare_candidates, topic_terms
from kdb.retrieval.ingestion.conflict_store import fingerprint

POLICIES = {'record_only', 'keep_new', 'keep_old'}


def newness(record):
    if record.get('_offline'):
        return (float('inf'), str(record['_id']))
    value = record.get('insert_time')
    if not value:
        raise ValueError('insert_time required to choose newer/older existing knowledge')
    parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        from zoneinfo import ZoneInfo
        parsed = parsed.replace(tzinfo=ZoneInfo('Asia/Shanghai'))
    return (parsed.timestamp(), str(record['_id']))


def shortlist(record, online, additional, limit):
    known = {r['_id'] for r in online}
    extra = [r for r in additional if r.get('data_type') == record.get('data_type')
             and r.get('_id') != record.get('_id') and r.get('_id') not in known
             and r.get('del_flag', 0) == 0 and r.get('dedup_action') != 'skip']
    truncated = len(online) + len(extra) > limit
    if not truncated:
        return online + extra, False
    terms = topic_terms(record)
    extra.sort(key=lambda r: len(terms & topic_terms(r)), reverse=True)
    budget = min(len(extra), max(1, limit // 2))
    return online[:limit - budget] + extra[:budget], True


def estimate_tokens(record, candidate_count=60):
    # UTF-8 bytes give a conservative input allowance; provider tokenization varies.
    size = len((str(record.get('title') or '') + str(record.get('content') or '')).encode('utf-8'))
    return {'estimated': True, 'candidate_count': candidate_count,
            'input_tokens': (size * 4 + 900) * candidate_count,
            'output_tokens': 1500 * candidate_count,
            'assumption': 'candidate length equals current; includes rerank + judge, excludes rewrite and embedding'}


class DedupJob:
    def __init__(self, store, models, *, limit=60, threshold=0.1, min_shared_topics=1, aliases=None):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 60:
            raise ValueError('candidate limit must be 1..60')
        if threshold is not None and (isinstance(threshold, bool) or not math.isfinite(threshold) or not 0 <= threshold <= 1):
            raise ValueError('threshold must be 0..1')
        if isinstance(min_shared_topics, bool) or min_shared_topics not in (0, 1, 2):
            raise ValueError('min_shared_topics must be 0, 1 or 2')
        self.store, self.models = store, models
        self.limit, self.threshold = limit, threshold
        self.min_shared_topics, self.aliases = min_shared_topics, aliases

    def analyze(self, record, additional=()):
        record = copy.deepcopy(record)
        candidates = self.store.recall(record, self.limit)
        candidates, truncated = shortlist(record, candidates, additional, self.limit)
        result = compare_candidates(record, candidates, self.models.rerank, self.models.judge,
            self.threshold, self.min_shared_topics, self.aliases)
        result.update({'current': record, 'index': self.store.index, 'candidates': candidates,
                       'candidate_limit': self.limit, 'truncated': truncated,
                       'candidate_limit_reached': len(candidates) >= self.limit,
                       'estimate': estimate_tokens(record, len(candidates))})
        return result

    def apply(self, result, policy='record_only', *, dry_run=False, insert_new=False):
        if policy not in POLICIES:
            raise ValueError('unknown processing policy')
        current = result['current']
        relations = result['similarity_info']
        result['policy'] = policy
        result['actions'] = []
        duplicates = [r for r in relations if r['relation'] == 'duplicate']
        conflicts = [r for r in relations if r['relation'] == 'conflict']
        candidates = {r['_id']: r for r in result['candidates']}
        duplicate_rows = [current] + [candidates[r['related_id']] for r in duplicates]
        winner = current
        if policy != 'record_only' and duplicates and result['status'] == 'complete':
            winner = (max if policy == 'keep_new' else min)(duplicate_rows, key=newness)
        result['dedup_action'] = 'skip' if winner['_id'] != current['_id'] else 'retain'
        evaluated = set(result.get('evaluated_ids', [])) | {r['related_id'] for r in relations}
        stored_relations = [r for r in current.get('similarity_info', []) if r.get('related_id') not in evaluated] + relations
        current['similarity_info'] = stored_relations
        marker = {'status': ('partial' if result.get('scope') == 'explicit_candidates' and result['status'] == 'complete' else result['status']),
                  'fingerprint': fingerprint(current), 'version': 1,
                  'checked_at': datetime.now(timezone.utc).isoformat(), 'policy': policy,
                  'candidate_limit': self.limit, 'threshold': self.threshold, 'min_shared_topics': self.min_shared_topics}
        if dry_run:
            result['applied'] = False
            return result
        if result['status'] != 'complete':
            marker['status'] = 'failed'
        elif policy != 'record_only':
            offline = current.get('_offline', False)
            if offline and not insert_new:
                result['actions'] = [{'action': 'deferred_until_insert', 'related_id': r['related_id'],
                                      'relation': r['relation']} for r in duplicates + conflicts]
                for old in duplicate_rows:
                    if old.get('_offline') and old['_id'] != winner['_id']:
                        old['dedup_action'] = 'skip'
            else:
                # Resolve all conflict rewrites before any deletion. Rebuild vectors for changed text.
                rewrites = {}
                for relation in conflicts:
                    old = candidates[relation['related_id']]
                    if old.get('_offline'):
                        raise ValueError('apply batch offline records only after inserting retained records')
                    preferred, outdated = (current, old) if newness(current) >= newness(old) else (old, current)
                    if outdated.get('multimodal_contents'):
                        raise ValueError('multimodal conflict requires a reviewed content update; automatic rewrite was not applied')
                    base = rewrites.get(outdated['_id'], (outdated, {}))
                    previous_revision = {**base[0], **base[1]}
                    fields = self.models.resolve(preferred, previous_revision, relation['evidence'])
                    revised = copy.deepcopy(previous_revision)
                    revised.update(fields, audit_result=-1)
                    for key in ('indexes', 'title_embedding', 'content_embedding', '_seq_no', '_primary_term',
                                '_index', 'score', '_offline', 'dedup_action'):
                        revised.pop(key, None)
                    if not self.store.interface.process_one_data(revised, index_name=self.store.index):
                        raise RuntimeError('conflict revision preparation failed')
                    patch = {key: revised[key] for key in ('title', 'content', 'audit_result', 'indexes',
                        'title_embedding', 'content_embedding') if key in revised}
                    patch['dedup_check'] = {'status': 'pending', 'reason': 'conflict_revised'}
                    rewrites[outdated['_id']] = (outdated, patch)
                if offline and result['dedup_action'] != 'skip':
                    inserted = self.store.insert(current)
                    result['actions'].append({'action': 'insert', 'id': inserted['_id']})
                    current = result['current'] = inserted
                    winner = current
                current_revised = False
                for old, patch in rewrites.values():
                    self.store.patch(old, patch)
                    result['actions'].append({'action': 'revise_conflict', 'id': old['_id']})
                    if old['_id'] == current['_id']:
                        current.update(patch)
                        current_revised = True
                if current_revised:
                    # Pair conclusions were for the old text; recheck before deleting anything.
                    marker.update(status='pending', fingerprint=fingerprint(current), reason='recheck_revised_content')
                    current['dedup_check'] = marker
                    self.store.patch(current, {'dedup_check': marker})
                    result.update(applied=True, needs_recheck=True)
                    return result
                for old in duplicate_rows:
                    if old['_id'] == winner['_id']:
                        continue
                    if old.get('_offline'):
                        old['dedup_action'] = 'skip'
                        continue
                    retained = self.store.read(winner['_id'])
                    if not retained or retained.get('del_flag', 0) != 0 or fingerprint(retained) != fingerprint(winner):
                        raise RuntimeError('retained knowledge changed; rerun required')
                    patch = {'del_flag': 1, 'del_reason': 'dedup_' + policy + ' ' + str(winner['_id'])}
                    if old['_id'] == current['_id']:
                        patch.update({'similarity_info': stored_relations, 'dedup_check': marker})
                    self.store.patch(old, patch)
                    result['actions'].append({'action': 'soft_delete_duplicate', 'id': old['_id']})
                    if old['_id'] == current['_id']:
                        current['del_flag'] = 1
        stored_relations = [r for r in stored_relations if r.get('related_id') != current.get('_id')]
        current['similarity_info'] = stored_relations
        marker['fingerprint'] = fingerprint(current)
        current['dedup_check'] = marker
        if not current.get('_offline') and current.get('del_flag', 0) == 0:
            self.store.patch(current, {'similarity_info': stored_relations, 'dedup_check': marker})
        result['applied'] = True
        return result

    def run(self, records, *, policy='record_only', dry_run=False, insert_new=False, max_records=500, sink=None):
        if policy not in POLICIES or not isinstance(max_records, int) or not 1 <= max_records <= 10000:
            raise ValueError('invalid policy or max_records (1..10000)')
        try:
            selected = list(islice(records, max_records + 1))
        finally:
            if hasattr(records, 'close'):
                records.close()
        truncated = len(selected) > max_records
        selected = selected[:max_records]
        report = {'status': 'complete', 'index': self.store.index, 'processed': 0, 'failed': 0,
                  'selection_truncated': truncated, 'results': [], 'skipped': 0, 'needs_recheck': 0}
        for n, record in enumerate(selected):
            result = None
            try:
                if record.get('_offline'):
                    record.setdefault('_id', 'offline:' + str(n + 1).zfill(8))
                else:
                    fresh = self.store.read(record['_id'])
                    if not fresh or fresh.get('del_flag', 0) != 0:
                        report['skipped'] += 1
                        continue
                    if (fingerprint(fresh) != fingerprint(record)
                            or fresh.get('audit_result') != record.get('audit_result')):
                        report['skipped'] += 1
                        skipped = {'status': 'skipped', 'current': record, 'reason': 'changed_after_selection'}
                        if sink:
                            sink(skipped)
                        else:
                            report['results'].append(skipped)
                        continue
                    record = selected[n] = fresh
                additional = [r for r in selected[:n] if r.get('_offline') and r.get('dedup_action') != 'skip']
                result = self.analyze(record, additional)
                result = self.apply(result, policy, dry_run=dry_run, insert_new=insert_new)
                if result['status'] != 'complete':
                    report['failed'] += 1
                if result.get('needs_recheck'):
                    report['needs_recheck'] += 1
                record.clear()
                record.update(result['current'])
                record['dedup_action'] = result['dedup_action']
            except Exception as exc:
                report['failed'] += 1
                result = result or {'current': record, 'index': self.store.index, 'similarity_info': [], 'actions': []}
                result['status'] = 'failed'
                result.setdefault('errors', []).append({'stage': 'job', 'error': str(exc)})
                record['dedup_check'] = {'status': 'failed', 'fingerprint': fingerprint(record)}
                record['dedup_action'] = 'failed'
                if not dry_run and not record.get('_offline') and record.get('del_flag', 0) == 0:
                    try:
                        self.store.patch(record, {'dedup_check': record['dedup_check']})
                    except Exception as marker_error:
                        result['errors'].append({'stage': 'checkpoint', 'error': str(marker_error)})
            report['processed'] += 1
            if sink:
                sink(result)
            else:
                report['results'].append(result)
        report['usage'] = copy.deepcopy(self.models.usage)
        report['usage']['embedding'] = {'total_tokens': None, 'note': 'existing embedding interface does not return usage'}
        report['offline_records'] = [r for r in selected if r.get('_offline')]
        if report['failed']:
            report['status'] = 'failed'
        elif report['needs_recheck']:
            report['status'] = 'partial'
        return report
