#!/usr/bin/env python
# -*- coding:utf8 -*-

"""
聊天 QA 独立入库审核。

上游抽取器只生成候选；本模块对每条候选发起独立模型请求，
保留原始 q/a 和所有扩展字段，只追加审核结果。
入库是下游程序闸门的职责，不由模型直接执行。
"""

import json
import logging
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import config as cqe_config
from . import llm_client
from .qa_extractor import clear_think, load_prompt


REVIEW_VERSION = 'chat_qa_review_v2_client_prompt'
VALID_DECISIONS = {'accept', 'review', 'reject'}
VALID_QUALITY_LEVELS = {'high', 'mid', 'low'}
VALID_SCOPES = {'universal', 'industry_specific', 'client_specific'}
ANSWER_SOURCE_ROLES = {'leader/可作为答案来源', '同事/可作为答案来源'}

_STRONG_AI_SOURCE_RE = re.compile(
    r'(?i)(?:ai\s*(?:助理|助手|客服)|智能(?:助理|助手|客服)|机器人|\bbot\b)'
)
_BROKEN_PLACEHOLDER_RE = re.compile(
    r'\[(?:已脱敏|业务ID|用户ID|账号|账户|公司名|店铺名|姓名|手机号|电话|邮箱)\]',
    re.I,
)
_EMAIL_RE = re.compile(r'(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b')
_PHONE_RE = re.compile(r'(?<!\d)(?:\+?86[- ]?)?1[3-9]\d{9}(?!\d)')
_LONG_IDENTIFIER_RE = re.compile(r'(?<!\d)\d{12,}(?!\d)')


def _normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value or '').strip().lower()
    if text in {'1', 'true', 'yes', 'y'}:
        return True
    if text in {'0', 'false', 'no', 'n'}:
        return False
    return default


def _normalize_string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [item.strip() for item in re.split(r'[,，;；\n]+', value) if item.strip()]
    return []


def parse_review_json(raw: str) -> Optional[Dict[str, Any]]:
    """兼容模型偶发返回 fenced JSON，但不从自由文本猜测审核结果。"""
    text = clear_think(raw or '').strip()
    if text.startswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.I)
        text = re.sub(r'\s*```$', '', text)
    try:
        data = json.loads(text)
    except Exception:
        match = re.search(r'\{.*\}', text, flags=re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except Exception:
            return None
    return data if isinstance(data, dict) else None


def compact_turn_evidence(text: str, max_chars: int = 24000) -> str:
    """去掉超长的同事名单，并确保尾部“当前待评估答案”不被截断。"""
    text = str(text or '')
    text = re.sub(r'^answer_source_names:.*$', 'answer_source_names: [omitted]', text, flags=re.M)
    if len(text) <= max_chars:
        return text
    return '[earlier context truncated]\n' + text[-max_chars:]


def deterministic_reject_reasons(item: Dict[str, Any]) -> List[str]:
    """只放置高确定性安全规则；边界判断留给审核模型。"""
    reasons: List[str] = []
    source = str(item.get('source') or item.get('from_user') or '').strip()
    source_identity = str(item.get('source_identity') or '').strip()
    q = str(item.get('q') or '')
    a = str(item.get('a') or '')
    combined = f'{q}\n{a}'

    if _normalize_bool(item.get('source_is_ai'), default=False) or _STRONG_AI_SOURCE_RE.search(source):
        reasons.append('ai_answer_source')
    if source_identity and source_identity not in ANSWER_SOURCE_ROLES:
        reasons.append('non_human_answer_source')
    if _BROKEN_PLACEHOLDER_RE.search(combined):
        reasons.append('broken_redaction_placeholder')
    if _EMAIL_RE.search(combined) or _PHONE_RE.search(combined) or _LONG_IDENTIFIER_RE.search(combined):
        reasons.append('direct_identifier_exposed')
    return list(dict.fromkeys(reasons))


def _fail_closed_result(reason_code: str, reason: str) -> Dict[str, Any]:
    return {
        'decision': 'review',
        'quality_level': 'mid',
        'grounded': False,
        'knowledge_scope': 'client_specific',
        'sensitive': False,
        'temporary': False,
        'valid_until': None,
        'reason_codes': [reason_code],
        'reason': reason,
    }


def normalize_review_result(data: Dict[str, Any]) -> Dict[str, Any]:
    decision = str(data.get('decision') or '').strip().lower()
    quality_level = str(data.get('quality_level') or '').strip().lower()
    scope = str(data.get('knowledge_scope') or '').strip().lower()
    grounded = _normalize_bool(data.get('grounded'), default=False)
    sensitive = _normalize_bool(data.get('sensitive'), default=False)
    temporary = _normalize_bool(data.get('temporary'), default=False)

    if decision not in VALID_DECISIONS:
        decision = 'review'
    if quality_level not in VALID_QUALITY_LEVELS:
        quality_level = 'mid'
    if scope not in VALID_SCOPES:
        scope = 'client_specific'

    reason_codes = _normalize_string_list(data.get('reason_codes'))
    reason = str(data.get('reason') or '').strip()

    # 模型即使误给 accept，也必须经过确定性准入条件。
    blockers = []
    if quality_level != 'high':
        blockers.append('not_high_quality')
    if not grounded:
        blockers.append('not_grounded')
    if sensitive:
        blockers.append('sensitive_content')
    if temporary:
        blockers.append('temporary_content')
    if scope == 'client_specific':
        blockers.append('client_specific')
    if decision == 'accept' and blockers:
        decision = 'reject' if sensitive or temporary or scope == 'client_specific' else 'review'
        reason_codes.extend(blockers)

    if decision == 'review':
        quality_level = 'mid'
    elif decision == 'reject':
        quality_level = 'low'

    return {
        'decision': decision,
        'quality_level': quality_level,
        'grounded': grounded,
        'knowledge_scope': scope,
        'sensitive': sensitive,
        'temporary': temporary,
        'valid_until': data.get('valid_until') or None,
        'reason_codes': list(dict.fromkeys(reason_codes)),
        'reason': reason,
    }


class ChatQAReviewer:
    def __init__(self, client: Optional[str] = None, model: Optional[str] = None,
                 max_tokens: int = 1800, temperature: float = 0.0,
                 timeout: int = 180, usage_out: Optional[dict] = None):
        cqe_config.load_llm_config()
        self.client = str(client or '').strip()
        # 沿用生产 models.quality 配置；review 是新的处理阶段名，不要求客户再补一份模型配置。
        self.model = cqe_config.get_model('quality', model)
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.usage_out = usage_out

        base_prompt = load_prompt('review.default')
        augment = load_prompt(f'review.{self.client}') if self.client else ''
        self.system_prompt = f'{base_prompt}\n\n{augment}' if augment else base_prompt

    def _build_query(self, item: Dict[str, Any]) -> str:
        payload = {
            'client': item.get('client') or item.get('platform') or self.client,
            'q': item.get('q'),
            'a': item.get('a'),
            'source': item.get('source') or item.get('from_user'),
            'source_identity': item.get('source_identity'),
            'source_quote': item.get('source_quote'),
            'extractor_quality_level': item.get('quality_level'),
            'extractor_reuse_scope': item.get('reuse_scope'),
            'extractor_is_qualified': item.get('is_qualified'),
            'marketplace': item.get('marketplace') or item.get('model_platform'),
            'current_turn_evidence': compact_turn_evidence(item.get('from_chat_history', '')),
        }
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)

    def review(self, item: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
        hard_reasons = deterministic_reject_reasons(item)
        if hard_reasons:
            return ({
                'decision': 'reject',
                'quality_level': 'low',
                'grounded': False,
                'knowledge_scope': 'client_specific',
                'sensitive': 'direct_identifier_exposed' in hard_reasons,
                'temporary': False,
                'valid_until': None,
                'reason_codes': hard_reasons,
                'reason': '命中程序硬性安全规则',
            }, False)

        raw, detail = llm_client.request_llm(
            model_name=self.model,
            query=self._build_query(item),
            system_message=self.system_prompt,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            timeout=self.timeout,
            usage_out=self.usage_out,
        )
        parsed = parse_review_json(raw)
        if parsed is None:
            logging.error('ChatQAReviewer: 无法解析审核返回，detail=%s raw=%s', detail[:300], raw[:1000])
            return _fail_closed_result('review_model_error', '审核模型返回无法解析'), True
        return normalize_review_result(parsed), True


def apply_review_result(item: Dict[str, Any], review: Dict[str, Any], model: str) -> Dict[str, Any]:
    """不删除、不改写上游扩展字段；新增审核字段供入库闸门和追溯。"""
    output = dict(item)
    output['extractor_quality_level'] = item.get('quality_level')
    output['quality_level'] = review['quality_level']
    output['review_decision'] = review['decision']
    output['review_reason_codes'] = review['reason_codes']
    output['review_reason'] = review['reason']
    output['grounded'] = review['grounded']
    output['knowledge_scope'] = review['knowledge_scope']
    output['sensitive'] = review['sensitive']
    output['temporary'] = review['temporary']
    output['valid_until'] = review['valid_until']
    output['review_model'] = model
    output['review_version'] = REVIEW_VERSION
    output['auto_import'] = review['decision'] == 'accept' and review['quality_level'] == 'high'
    return output


def _load_jsonl(path: str) -> Iterable[Dict[str, Any]]:
    with open(path, encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                logging.error('ChatQAReviewer: JSONL 第 %s 行无法解析 path=%s', line_no, path)
                continue
            if isinstance(item, dict):
                yield item


def review_qa_file(input_file: str, output_file: str, reviewer: ChatQAReviewer,
                   stats: Dict[str, Any]) -> str:
    buckets: Dict[str, List[Dict[str, Any]]] = {'high': [], 'mid': [], 'low': []}
    for item in _load_jsonl(input_file):
        stats['extracted_candidate_num'] += 1
        review, used_model = reviewer.review(item)
        reviewed = apply_review_result(item, review, reviewer.model)
        decision = reviewed['review_decision']
        stats[f'review_{decision}_num'] += 1
        stats['model_review_request_num' if used_model else 'deterministic_reject_num'] += 1
        if 'review_model_error' in reviewed.get('review_reason_codes', []):
            stats['review_model_error_num'] += 1
        buckets[reviewed['quality_level']].append(reviewed)

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(buckets, f, ensure_ascii=False, indent=2)
    return output_file


def review_batch(batch_file: str, output_batch_file: str, process_field_num: int = 4,
                 client: str = '', stats_file: Optional[str] = None,
                 model: Optional[str] = None,
                 output_suffix: str = '_reviewed_and_resplit.txt') -> Dict[str, Any]:
    process_field_num = int(process_field_num)
    usage: Dict[str, Any] = {}
    reviewer = ChatQAReviewer(client=client, model=model, usage_out=usage)
    stats: Dict[str, Any] = {
        'extracted_candidate_num': 0,
        'model_review_request_num': 0,
        'deterministic_reject_num': 0,
        'review_accept_num': 0,
        'review_review_num': 0,
        'review_reject_num': 0,
        'review_model_error_num': 0,
        'review_version': REVIEW_VERSION,
        'review_model': reviewer.model,
    }

    with open(batch_file, encoding='utf-8') as f, open(output_batch_file, 'w', encoding='utf-8') as out:
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            fields = line.split('\t')
            if len(fields) <= process_field_num:
                logging.warning('ChatQAReviewer: skip invalid batch line: %s', line)
                continue
            qa_file = fields[process_field_num]
            root, ext = os.path.splitext(qa_file)
            output_file = (root + output_suffix) if ext else (qa_file + output_suffix)
            review_qa_file(qa_file, output_file, reviewer, stats)
            out.write(line + '\t' + output_file + '\n')

    stats['usage'] = usage
    if stats_file:
        temp_file = stats_file + '.tmp'
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(temp_file, stats_file)
    logging.info('ChatQAReviewer stats: %s', stats)
    return stats


if __name__ == '__main__':
    import fire
    logging.basicConfig(level=logging.INFO)
    fire.Fire({'review_batch': review_batch})
