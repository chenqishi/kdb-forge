"""Whole-document detection. Content evidence comes exclusively from segments."""
import copy
import random
import re
from difflib import SequenceMatcher


def parsed_text(value):
    if isinstance(value, list):
        return '\n'.join(parsed_text(item) for item in value)
    if isinstance(value, dict):
        if value.get('type') in {'text', 'table'}:
            return str(value.get('text_content') or value.get('content') or '')
        return '\n'.join(parsed_text(item) for item in value.values() if isinstance(item, (list, dict)))
    return ''


def sample_text(text, seed=0, size=450):
    if not isinstance(text, str) or not text.strip():
        raise ValueError('parsed document contains no text')
    if not 400 <= size <= 500:
        raise ValueError('sample size must be 400..500 characters')
    start = random.Random(seed).randint(0, max(0, len(text) - size))
    return {'text': text[start:start + size], 'offset': start, 'seed': seed}


def coverage(sample, segments, min_match=12):
    normalized = re.sub(r'\s+', '', sample).lower()
    covered = set()
    evidence = []
    for segment in segments:
        text = re.sub(r'\s+', '', str(segment.get('content') or '')).lower()
        for block in SequenceMatcher(None, normalized, text, autojunk=False).get_matching_blocks():
            if block.size < min_match:
                continue
            covered.update(range(block.a, block.a + block.size))
            evidence.append({'segment_id': segment['_id'], 'sample_start': block.a,
                             'length': block.size, 'normalized_quote': normalized[block.a:block.a + block.size]})
    return {'coverage': len(covered) / len(normalized) if normalized else 0,
            'matched_chars': len(covered), 'sample_chars': len(normalized), 'evidence': evidence,
            'normalization': 'lowercase_and_remove_whitespace'}


def check_document(store, models, name, text, *, seed=0, name_check=True, content_check=True):
    if not name or not (name_check or content_check):
        raise ValueError('file name and at least one detection method are required')
    before_usage = copy.deepcopy(models.usage)
    sample = sample_text(text, seed)
    matches = {}
    if name_check:
        for existing in store.file_names():
            verdict = models.names(name, existing)
            if not isinstance(verdict.get('same_document'), bool):
                raise ValueError('invalid document name verdict')
            if verdict['same_document']:
                matches[existing] = {'from_file_name': existing, 'by_name': True,
                                     'name_reason': verdict.get('reason', '')}
    if content_check:
        groups = {}
        # One full sample plus subqueries prevent a single segment from dominating recall.
        queries = [sample['text']] + [sample['text'][i:i + 150] for i in range(0, len(sample['text']), 150)]
        for query in queries:
            for segment in store.recall({'data_type': 'segment', 'content': query}, 60):
                if segment.get('data_type') != 'segment':
                    raise ValueError('document coverage may only use segments')
                source = (segment.get('ext_info') or {}).get('from_file_name')
                if source:
                    groups.setdefault(source, {})[segment['_id']] = segment
        for source, segments in groups.items():
            score = coverage(sample['text'], list(segments.values()))
            if score['coverage'] >= 0.7:
                matches.setdefault(source, {'from_file_name': source, 'by_name': False}).update(score, by_content=True)
    for match in matches.values():
        match['records'] = store.file_records(match['from_file_name'])
    usage = {stage: {key: count - before_usage.get(stage, {}).get(key, 0) for key, count in values.items()}
             for stage, values in models.usage.items()}
    usage['embedding'] = {'total_tokens': None, 'note': 'existing embedding interface does not return usage'}
    return {'status': 'complete', 'index': store.index, 'from_file_name': name,
            'sample': sample, 'matches': list(matches.values()), 'usage': usage}


def apply_document_matches(store, report, policy='record_only'):
    if policy not in {'record_only', 'skip_new', 'replace_old'}:
        raise ValueError('document policy must be record_only, skip_new or replace_old')
    if report['index'] != store.index or report.get('status') != 'complete':
        raise ValueError('document comparison is incomplete or for another index')
    result = {'skip_new': bool(report['matches']) and policy == 'skip_new', 'deleted': [], 'policy': policy}
    if policy == 'replace_old':
        seen = set()
        for match in report['matches']:
            for old in match['records']:
                if old['_id'] in seen:
                    continue
                seen.add(old['_id'])
                store.patch(old, {'del_flag': 1, 'del_reason': 'document_replaced_by ' + report['from_file_name']})
                result['deleted'].append(old['_id'])
    return result
