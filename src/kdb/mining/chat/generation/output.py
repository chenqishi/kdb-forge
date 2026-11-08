from kdb.mining.chat.message_cleaning import looks_like_image_reference_answer
from kdb.mining.chat.quality.normalization import fix_context_only_bank_detail
from kdb.mining.chat.quality.normalization import fix_overbroad_listing_type_question
from kdb.mining.chat.quality.normalization import fix_platform_placeholder_qa_text
from kdb.mining.chat.quality.normalization import fix_source_bound_qa_text
from kdb.mining.chat.quality.normalization import fix_unsupported_business_object_terms
from kdb.mining.chat.quality.normalization import generalize_reusable_qa_text
from kdb.mining.chat.quality.normalization import infer_is_qualified
from kdb.mining.chat.quality.normalization import merge_qa_tags
from kdb.mining.chat.quality.normalization import normalize_confidence
from kdb.mining.chat.quality.normalization import normalize_quality_level
from kdb.mining.chat.quality.normalization import normalize_reuse_scope
from kdb.mining.chat.quality.normalization import normalize_string_list
from kdb.mining.chat.quality.normalization import prefer_source_quote_answer_when_safe
from kdb.mining.common.llm.json_output import iter_llm_json_items
from kdb.mining.common.llm.json_output import parse_llm_json_data
import json
import logging
import os
import traceback

def normalize_llm_qa_items(result, extra_info_dict=None, default_platform=None, candidate_source=''):
    extra_info_dict = extra_info_dict or {}
    try:
        data = parse_llm_json_data(result)
    except Exception:
        logging.error('parse direct llm json failed. raw=%s\n%s', result, traceback.format_exc())
        return []

    qa_list = []
    for item, quality_from_bucket in iter_llm_json_items(data):
        if not isinstance(item, dict):
            continue
        qa_info = dict(extra_info_dict)
        raw_q = str(item.get('q') or item.get('question') or '').strip()
        raw_a = str(item.get('a') or item.get('answer') or '').strip()
        q = generalize_reusable_qa_text(raw_q)
        a = raw_a if looks_like_image_reference_answer(raw_a) else generalize_reusable_qa_text(raw_a)
        if not q or not a:
            continue

        model_platform = str(
            item.get('platform') or item.get('marketplace') or item.get('inferred_platform') or ''
        ).strip()
        if model_platform == 'mix':
            model_platform = str(item.get('inferred_platform') or '').strip()
        client_platform = str(default_platform or '').strip() or model_platform or 'unknown'
        marketplace = model_platform if model_platform and model_platform != client_platform else ''

        quality_level = normalize_quality_level(
            item.get('quality_level') or item.get('quality') or quality_from_bucket,
            default='mid'
        )
        reuse_scope = normalize_reuse_scope(item.get('reuse_scope'))

        qa_info.update({
            'q': q,
            'a': a,
            'source': str(item.get('source') or candidate_source or '').strip(),
            'platform': client_platform,
            'client': client_platform,
            'quality_level': quality_level,
            'is_qualified': infer_is_qualified(item, quality_level, reuse_scope),
            'quality_reason': str(item.get('quality_reason') or item.get('reason') or '').strip(),
            'tags': merge_qa_tags(item),
            'reuse_scope': reuse_scope,
            'confidence': normalize_confidence(item.get('confidence')),
            'source_quote': str(item.get('source_quote') or '').strip(),
        })
        if marketplace:
            qa_info['marketplace'] = marketplace
        if model_platform:
            qa_info['model_platform'] = model_platform
        if qa_info['quality_reason']:
            qa_info['reason'] = qa_info['quality_reason']
        qa_info['quality_info'] = normalize_string_list(item.get('quality_info'))
        qa_info = fix_source_bound_qa_text(qa_info)
        qa_info = prefer_source_quote_answer_when_safe(qa_info)
        qa_info = fix_platform_placeholder_qa_text(qa_info)
        qa_info = fix_context_only_bank_detail(qa_info)
        qa_info = fix_unsupported_business_object_terms(qa_info)
        qa_info = fix_overbroad_listing_type_question(qa_info)
        qa_list.append(qa_info)
    return qa_list


def load_jsonl_qa_file(qa_file):
    qa_list = []
    if not qa_file or not os.path.exists(qa_file):
        logging.warning('qa_file not found: %s', qa_file)
        return qa_list

    with open(qa_file, encoding='utf8') as f:
        content = f.read().strip()
    if not content:
        return qa_list

    try:
        data = json.loads(content)
        if isinstance(data, dict):
            if any(key in data for key in ('high', 'mid', 'low')):
                for key in ('high', 'mid', 'low'):
                    for qa_info in data.get(key, []):
                        qa_info = dict(qa_info)
                        qa_info.setdefault('quality_level', key)
                        qa_list.append(qa_info)
                return qa_list
            if isinstance(data.get('items'), list):
                return [item for item in data['items'] if isinstance(item, dict)]
            if data.get('q') and data.get('a'):
                return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    except Exception:
        pass

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            logging.error('parse qa json line failed file=%s line=%s', qa_file, line[:500])
            continue
        if isinstance(item, dict):
            qa_list.append(item)
    return qa_list


def build_quality_bucket_data(qa_list):
    bucket_data = {'high': [], 'mid': [], 'low': []}
    for qa_info in qa_list:
        if not isinstance(qa_info, dict):
            continue
        qa_info = dict(qa_info)
        quality_level = normalize_quality_level(
            qa_info.get('quality_level') or qa_info.get('quality'),
            default='mid'
        )
        qa_info['quality_level'] = quality_level
        bucket_data[quality_level].append(qa_info)
    return bucket_data


def write_quality_bucket_file(input_file, output_file):
    qa_list = load_jsonl_qa_file(input_file)
    bucket_data = build_quality_bucket_data(qa_list)
    with open(output_file, 'w', encoding='utf8') as f:
        json.dump(bucket_data, f, ensure_ascii=False, indent=2)
    logging.info(
        'write direct llm quality bucket file: input=%s output=%s high=%s mid=%s low=%s',
        input_file,
        output_file,
        len(bucket_data['high']),
        len(bucket_data['mid']),
        len(bucket_data['low'])
    )
    return output_file


def build_direct_llm_quality_batch(batch_file, output_batch_file, process_field_num=4,
                                   output_suffix='_direct_llm_quality_and_resplit.txt'):
    """
    直接 LLM 抽取阶段已经返回 quality_level。这里只把 JSONL 抽取文件转换成
    原 Dify 质量评估产物兼容的 {"high": [], "mid": [], "low": []} 文件，
    让后续 schema_trans 和 ES 写入链路保持原口径。
    """
    process_field_num = int(process_field_num)
    with open(batch_file, encoding='utf8') as f, open(output_batch_file, 'w', encoding='utf8') as of:
        for line in f:
            line = line.rstrip('\n')
            if not line:
                continue
            fields = line.split('\t')
            if len(fields) <= process_field_num:
                logging.warning('skip invalid batch line: %s', line)
                continue
            qa_file = fields[process_field_num]
            root, ext = os.path.splitext(qa_file)
            if ext:
                output_file = root + output_suffix
            else:
                output_file = qa_file + output_suffix
            write_quality_bucket_file(qa_file, output_file)
            of.write(line + '\t' + output_file + '\n')
