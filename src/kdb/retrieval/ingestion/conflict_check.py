"""Pure candidate comparison for knowledge duplicate and conflict checks."""
from __future__ import annotations

import math
import re
from typing import Any, Callable

RELATIONS = frozenset({'duplicate', 'overlap', 'conflict', 'different', 'uncertain'})
STOP_WORDS = frozenset('如何 什么 怎么 可以 是否 需要 进行 关于 问题 答案 一般 情况 用户 the and for with how what'.split())


def topic_terms(record, aliases=None):
    import jieba
    text = str(record.get('title') or '') + '\n' + str(record.get('content') or '')
    keywords = record.get('keywords') or []
    if isinstance(keywords, str):
        keywords = re.split(r'[,，;；\s]+', keywords)
    words = list(jieba.cut(text)) + [str(w) for w in keywords]
    aliases = aliases or {}
    return {aliases.get(w, w) for word in words
            if len(w := word.strip().lower()) > 1 and w not in STOP_WORDS
            and re.search(r'[a-z\u4e00-\u9fff]', w)}


def shared_topics(current, candidate, aliases=None):
    return sorted(topic_terms(current, aliases) & topic_terms(candidate, aliases))


def compare_candidates(current: dict, candidates: list[dict], rerank: Callable,
                       judge: Callable, threshold: float | None = None,
                       min_shared_topics: int = 0, aliases=None) -> dict[str, Any]:
    """Compare recalled candidates without changing data; errors are explicit."""
    kind = current.get('data_type')
    if kind not in {'qa', 'segment'}:
        raise ValueError('data_type must be qa or segment')
    if threshold is not None and (not math.isfinite(threshold) or not 0 <= threshold <= 1):
        raise ValueError('threshold must be between 0 and 1')
    if not isinstance(min_shared_topics, int) or not 0 <= min_shared_topics <= 2:
        raise ValueError('min_shared_topics must be 0, 1 or 2')
    eligible = [item for item in candidates if item.get('data_type') == kind
                and not (current.get('_id') and item.get('_id') == current['_id'])]
    result = {'status': 'complete', 'candidate_count': len(eligible),
              'judged_count': 0, 'filtered_count': 0, 'similarity_info': [], 'errors': [], 'filter_details': [],
              'evaluated_ids': []}
    if not eligible:
        return result
    try:
        scores = list(rerank(current, eligible))
        if len(scores) != len(eligible) or any(isinstance(s, bool) or not isinstance(s, (int, float)) or not math.isfinite(s) or not 0 <= s <= 1 for s in scores):
            raise ValueError('invalid rerank scores')
    except Exception as exc:
        result['status'] = 'failed'
        result['errors'].append({'stage': 'rerank', 'error': str(exc)})
        return result
    for item, score in zip(eligible, scores):
        topics = shared_topics(current, item, aliases) if min_shared_topics else []
        filtered = ('relevance' if threshold is not None and score < threshold else
                    'topic' if len(topics) < min_shared_topics else None)
        if filtered:
            result['filtered_count'] += 1
            result['filter_details'].append({'related_id': item.get('_id'), 'relevance_score': score,
                                             'shared_topics': topics, 'reason': filtered})
            continue
        try:
            verdict = judge(current, item)
            relation = verdict.get('relation')
            if relation not in RELATIONS:
                raise ValueError('invalid relation')
            result['judged_count'] += 1
            result['evaluated_ids'].append(item.get('_id'))
            if relation == 'different':
                continue
            evidence = verdict.get('evidence') or {}
            if not isinstance(evidence, dict):
                evidence = {}
            if relation == 'conflict':
                scope = verdict.get('effective_scope')
                explicit = (isinstance(scope, str) and bool(re.search(r'20\d{2}|[vV]\d|第.+版', scope))
                            and scope in str(current.get('title') or '') + '\n' + str(current.get('content') or '')
                            and scope in str(item.get('title') or '') + '\n' + str(item.get('content') or ''))
                confirmed = verdict.get('scope_confirmed') is True and (verdict.get('scope_kind') == 'timeless_fact' or explicit)
                if not confirmed:
                    relation = 'uncertain'
                    verdict['reason'] = '相同适用条件和时段尚未确认；' + str(verdict.get('reason') or '')
            current_quote, related_quote = evidence.get('current'), evidence.get('related')
            if relation != 'uncertain':
                valid = (isinstance(current_quote, str) and current_quote.strip()
                         and current_quote in (str(current.get('title') or '') + '\n' + str(current.get('content') or ''))
                         and isinstance(related_quote, str) and related_quote.strip()
                         and related_quote in (str(item.get('title') or '') + '\n' + str(item.get('content') or '')))
                if not valid:
                    relation = 'uncertain'
                    evidence = {}
                    verdict['reason'] = '原文证据校验失败；' + str(verdict.get('reason') or '')
            else:
                if not (isinstance(current_quote, str) and current_quote.strip()
                        and current_quote in str(current.get('title') or '') + '\n' + str(current.get('content') or '')
                        and isinstance(related_quote, str) and related_quote.strip()
                        and related_quote in str(item.get('title') or '') + '\n' + str(item.get('content') or '')):
                    evidence = {}
            result['similarity_info'].append({'related_id': item.get('_id'), 'related_data_type': kind,
                                              'relation': relation, 'relevance_score': float(score),
                                              'reason': verdict.get('reason', ''), 'evidence': evidence,
                                              'shared_topics': topics})
        except Exception as exc:
            result['status'] = 'failed'
            result['errors'].append({'stage': 'judge', 'related_id': item.get('_id'), 'error': str(exc)})
    return result


def check_batch(records: list[dict], candidates: list[dict], recall: Callable,
                rerank: Callable, judge: Callable, threshold: float | None = None,
                limit: int = 60) -> list[dict]:
    """Run checks on supplied increment against a caller-scoped candidate set."""
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 60:
        raise ValueError('limit must be between 1 and 60')
    output = []
    for record in records:
        try:
            kind = record.get('data_type')
            if kind not in {'qa', 'segment'}:
                raise ValueError('data_type must be qa or segment')
            available = [row for row in candidates if row.get('data_type') == kind
                         and not (record.get('_id') and row.get('_id') == record['_id'])]
            matches = list(recall(record, available, limit + 1))
            allowed = {id(row) for row in available}
            if any(id(row) not in allowed for row in matches):
                raise ValueError('recall returned an out-of-scope candidate')
            result = compare_candidates(record, matches[:limit], rerank, judge, threshold)
            result.update({'id': record.get('_id'), 'candidate_limit': limit,
                           'truncated': len(matches) > limit})
        except Exception as exc:
            result = {'id': record.get('_id'), 'status': 'failed', 'similarity_info': [],
                      'candidate_limit': limit, 'truncated': None,
                      'errors': [{'stage': 'recall', 'error': str(exc)}]}
        output.append(result)
    return output
