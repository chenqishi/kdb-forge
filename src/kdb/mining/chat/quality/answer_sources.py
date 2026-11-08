from kdb.mining.chat.identity import _is_name_match
from kdb.mining.chat.media import format_supplement_image_placeholders
from kdb.mining.chat.media import is_generic_image_answer_text
from kdb.mining.chat.media import is_image_only_placeholder_content
from kdb.mining.chat.message_cleaning import looks_like_image_reference_answer
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.prompts import append_unique_image_info
from kdb.mining.chat.prompts import merge_message_supplements
from kdb.mining.chat.prompts import merge_supplement_dicts
from kdb.mining.chat.quality.normalization import generalize_reusable_qa_text
from kdb.mining.chat.quality.qa import is_null_answer
from kdb.mining.chat.quality.qa import is_weak_generated_answer
from kdb.mining.chat.quality.qa import text_overlap_ratio
import re

def extract_numbered_image_labels(text):
    labels = []
    for match in re.finditer(
        r'(?:图片|截图|image|img|photo|picture)\s*(\d+)',
        str(text or ''),
        flags=re.I
    ):
        label = f"图片{match.group(1)}"
        if label not in labels:
            labels.append(label)
    return labels


def get_supplement_image_labels(supplement):
    labels = []
    if not isinstance(supplement, dict):
        return labels
    for index, image_info in enumerate(supplement.get('images') or [], start=1):
        if not isinstance(image_info, dict):
            continue
        label = str(image_info.get('label', '') or '').strip()
        if not label:
            label = f"图片{index}"
        if label not in labels:
            labels.append(label)
    return labels


def get_image_reference_values(image_info):
    values = set()
    if not isinstance(image_info, dict):
        return values
    for key in [
        'label',
        'address',
        'backend_url',
        'backend_path',
        'backend_file_path',
        'public_url',
        'url',
        'path',
        'file_url',
        'image_url',
        'image_path',
    ]:
        value = str(image_info.get(key) or '').strip()
        if value:
            values.add(value)
    for value in image_info.get('addresses') or []:
        value = str(value or '').strip()
        if value:
            values.add(value)
    return values


def image_info_matches(candidate_image, qa_image):
    candidate_values = get_image_reference_values(candidate_image)
    qa_values = get_image_reference_values(qa_image)
    return bool(candidate_values and qa_values and candidate_values.intersection(qa_values))


def get_matching_candidate_images(candidate_supplement, qa_supplement):
    if not isinstance(candidate_supplement, dict) or not isinstance(qa_supplement, dict):
        return []
    matches = []
    candidate_images = candidate_supplement.get('images') or []
    qa_images = qa_supplement.get('images') or []
    for candidate_image in candidate_images:
        for qa_image in qa_images:
            if image_info_matches(candidate_image, qa_image):
                append_unique_image_info(matches, candidate_image)
                break
    return matches


def format_image_answer_from_images(images):
    answer_parts = []
    for image_info in images or []:
        if not isinstance(image_info, dict):
            continue
        for key in ['backend_url', 'public_url', 'url', 'backend_file_path', 'backend_path', 'address']:
            value = str(image_info.get(key) or '').strip()
            if value and value not in answer_parts:
                answer_parts.append(value)
                break
    return '\n'.join(answer_parts).strip()


def get_supplement_image_mapping_error(supplement):
    if not isinstance(supplement, dict):
        return ''
    missing_labels = []
    for index, image_info in enumerate(supplement.get('images') or [], start=1):
        if not isinstance(image_info, dict):
            missing_labels.append(f"图片{index}")
            continue
        has_reference = any(
            str(image_info.get(key) or '').strip()
            for key in ['backend_url', 'public_url', 'url', 'backend_file_path', 'backend_path', 'address']
        )
        if not has_reference:
            missing_labels.append(str(image_info.get('label') or f"图片{index}"))
    if missing_labels:
        return 'image_mapping_missing_reference: ' + ','.join(missing_labels)
    return ''


def restore_answer_from_source_quote_if_needed(qa_info, candidate_answer, min_overlap=0.45):
    answer = str(qa_info.get('a', '') or '').strip()
    if not answer or looks_like_image_reference_answer(answer):
        return qa_info
    if text_overlap_ratio(answer, candidate_answer) >= min_overlap:
        return qa_info

    source_quote = str(qa_info.get('source_quote') or '').strip()
    if not source_quote or is_weak_generated_answer(source_quote):
        return qa_info
    if text_overlap_ratio(source_quote, candidate_answer) < min_overlap:
        return qa_info

    qa_info = dict(qa_info)
    qa_info['a'] = (
        source_quote
        if looks_like_image_reference_answer(source_quote)
        else generalize_reusable_qa_text(source_quote)
    )
    return qa_info


def is_image_only_candidate_turn(candidate_answer, candidate_supplement):
    if not candidate_supplement.get('images') and not is_image_only_placeholder_content(candidate_answer):
        return False
    content_without_images = re.sub(
        r'[\[【(（]?\s*(?:图片|image|img|photo|picture)\s*\d*\s*[\]】)）]?',
        '',
        sanitize_chat_content(candidate_answer),
        flags=re.I
    )
    return not content_without_images.strip()


def filter_qa_by_candidate_answer(qa_list, answer_turn):
    """
    防止模型从上方50句上下文偷抽其他答案：答案和来源都必须能回到候选答案。
    """
    candidate_messages = answer_turn.get('target_messages', [])
    candidate_answer = '\n'.join(str(message.get('content', '') or '') for message in candidate_messages)
    candidate_speakers = [str(message.get('send_user', '') or '').strip() for message in candidate_messages]
    candidate_supplement = merge_message_supplements(candidate_messages)
    candidate_has_image = bool(candidate_supplement.get('images')) or is_image_only_placeholder_content(candidate_answer)
    candidate_image_only = is_image_only_candidate_turn(candidate_answer, candidate_supplement)
    filtered = []
    for qa_info in qa_list:
        answer = str(qa_info.get('a', '') or '').strip()
        if is_null_answer(answer) or is_weak_generated_answer(answer):
            continue
        source = str(qa_info.get('source', '') or '').strip().strip('[]')
        if source and candidate_speakers and not any(
            _is_name_match(source, [speaker]) or _is_name_match(speaker, [source])
            for speaker in candidate_speakers
        ):
            continue
        if candidate_has_image:
            if candidate_image_only:
                source_quote = str(qa_info.get('source_quote') or '').strip()
                if not (
                    is_generic_image_answer_text(answer)
                    or is_generic_image_answer_text(source_quote)
                ):
                    continue
                qa_info = dict(qa_info)
                if candidate_supplement.get('images'):
                    qa_info['supplement'] = merge_supplement_dicts(qa_info.get('supplement'), candidate_supplement)
                    qa_info['a'] = (
                        format_image_answer_from_images(candidate_supplement.get('images'))
                        or format_supplement_image_placeholders(candidate_supplement)
                        or '图片答案'
                    )
                    mapping_error = get_supplement_image_mapping_error(candidate_supplement)
                    if mapping_error:
                        qa_info['supplement_mapping_error'] = mapping_error
                else:
                    qa_info['a'] = candidate_answer or answer or '图片答案'
                    qa_info['supplement_mapping_error'] = 'image_mapping_missing_metadata'
            else:
                qa_info = restore_answer_from_source_quote_if_needed(qa_info, candidate_answer, min_overlap=0.35)
                answer = str(qa_info.get('a', '') or '').strip()
                if not looks_like_image_reference_answer(answer) and text_overlap_ratio(answer, candidate_answer) < 0.35:
                    continue
            filtered.append(qa_info)
            continue
        qa_info = restore_answer_from_source_quote_if_needed(qa_info, candidate_answer)
        answer = str(qa_info.get('a', '') or '').strip()
        if text_overlap_ratio(answer, candidate_answer) < 0.45:
            continue
        filtered.append(qa_info)
    return filtered
