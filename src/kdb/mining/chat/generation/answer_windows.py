from kdb.mining.chat.generation.output import normalize_llm_qa_items
from kdb.mining.chat.identity import _normalize_name
from kdb.mining.chat.message_cleaning import parse_message_time_ts
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.prompts import build_group_prompt_header
from kdb.mining.chat.prompts import format_chat_message_for_model
from kdb.mining.chat.prompts import get_message_identity_info
from kdb.mining.chat.prompts import merge_message_supplements
from kdb.mining.chat.prompts import merge_supplement_dicts
from kdb.mining.chat.quality.answer_sources import filter_qa_by_candidate_answer
from kdb.mining.chat.quality.answer_sources import get_supplement_image_mapping_error
from kdb.mining.chat.quality.qa import clean_and_dedupe_qa_list
from kdb.mining.chat.quality.reusability import filter_unreusable_model_misextracts
from kdb.mining.chat.quality.reusability import is_answer_source_message
import logging
import re

def extract_leading_mention_key(content):
    content = sanitize_chat_content(content)
    match = re.match(r'^\s*@+([^\s\u2005:：，,。；;]+)', content)
    if not match:
        return ''
    return _normalize_name(match.group(1))


def should_merge_answer_source_message(current_turn, message_info, max_gap_seconds=180):
    if not current_turn:
        return False
    previous_message = current_turn['target_messages'][-1]
    previous_speaker = previous_message.get('send_user_id') or previous_message.get('send_user')
    current_speaker = message_info.get('send_user_id') or message_info.get('send_user')
    if previous_speaker != current_speaker:
        return False
    previous_ts = parse_message_time_ts(previous_message.get('message_time'))
    current_ts = parse_message_time_ts(message_info.get('message_time'))
    if previous_ts is None or current_ts is None:
        return False
    previous_mention = extract_leading_mention_key(previous_message.get('content', ''))
    current_mention = extract_leading_mention_key(message_info.get('content', ''))
    if previous_mention and current_mention and previous_mention != current_mention:
        return False
    return 0 <= current_ts - previous_ts <= max_gap_seconds


def build_answer_source_turns(group_chat_list, white_name_list=None, answer_source_names=None,
                              platform=None, identity_lookup=None):
    """
    以 leader/同事消息作为候选答案目标；连续同一人的候选答案合并为一个 answer turn。
    """
    turns = []
    current_turn = None
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for index, message_info in enumerate(group_chat_list):
        if is_answer_source_message(
            message_info,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        ):
            if should_merge_answer_source_message(current_turn, message_info):
                current_turn['target_messages'].append(message_info)
                current_turn['end_index'] = index
            else:
                if current_turn:
                    turns.append(current_turn)
                current_turn = {
                    'start_index': index,
                    'end_index': index,
                    'target_messages': [message_info],
                }
            continue

        if current_turn:
            turns.append(current_turn)
            current_turn = None
    if current_turn:
        turns.append(current_turn)
    return turns


def build_answer_window_prompt(group_name, group_chat_list, answer_turn, white_name_list=None,
                               answer_source_names=None, platform=None, identity_lookup=None,
                               context_message_limit=50):
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    start_index = answer_turn['start_index']
    context_messages = group_chat_list[max(0, start_index - context_message_limit):start_index]
    context_lines = [
        format_chat_message_for_model(
            message_info,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        )
        for message_info in context_messages
    ]
    target_lines = [
        format_chat_message_for_model(
            message_info,
            white_name_list=white_name_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup,
            marker='current_answer'
        )
        for message_info in answer_turn['target_messages']
    ]
    context_text = '\n'.join(context_lines) if context_lines else '无'
    target_text = '\n'.join(target_lines)
    prompt_text = (
        build_group_prompt_header(group_name, platform, answer_source_names, mode='answer_window')
        + "【上方50句上下文】\n"
        + context_text
        + "\n\n【当前待评估答案】\n"
        + target_text
    )
    return prompt_text


def request_llm_for_answer_windows(group_name, platform, group_chat_list, group_white_list, llm_model,
                                   answer_source_names=None, identity_lookup=None):
    result_qa_list = []
    answer_turns = build_answer_source_turns(
        group_chat_list,
        white_name_list=group_white_list,
        answer_source_names=answer_source_names,
        platform=platform,
        identity_lookup=identity_lookup
    )
    logging.info('group_name:%s answer_source_turns:%s', group_name, len(answer_turns))
    for answer_turn in answer_turns:
        prompt_str = build_answer_window_prompt(
            group_name,
            group_chat_list,
            answer_turn,
            white_name_list=group_white_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup
        )
        logging.info(f'answer_window_prompt:\n{prompt_str}\n')
        target_message = answer_turn['target_messages'][0]
        sorted_group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
        window_supplement = merge_message_supplements(
            sorted_group_chat_list[max(0, answer_turn['start_index'] - 50):answer_turn['start_index']]
            + answer_turn['target_messages']
        )
        target_supplement = merge_message_supplements(answer_turn['target_messages'])
        extra_info_dict = {
            'from_file_name': group_name,
            'from_user': target_message.get('send_user', ''),
            'group_name': group_name,
            'candidate_answer_time': target_message.get('message_time', ''),
            'from_chat_history': prompt_str,
        }
        source_identity, source_identity_reason = get_message_identity_info(
            target_message,
            white_name_list=group_white_list,
            answer_source_names=answer_source_names,
            platform=platform,
            identity_lookup=identity_lookup,
        )
        source_message_ids = [
            str(message.get('msg_id')).strip()
            for message in answer_turn['target_messages']
            if message.get('msg_id') not in (None, '')
        ]
        extra_info_dict.update({
            'source_user_id': target_message.get('send_user_id', ''),
            'source_message_ids': source_message_ids,
            'source_identity': source_identity,
            'source_identity_reason': source_identity_reason,
        })
        result = llm_model.request_json(prompt_str)
        qa_list = normalize_llm_qa_items(
            result,
            extra_info_dict=extra_info_dict,
            default_platform=platform,
            candidate_source=target_message.get('send_user', '')
        )
        qa_list = filter_unreusable_model_misextracts(qa_list)
        qa_list = filter_qa_by_candidate_answer(qa_list, answer_turn)
        qa_list = clean_and_dedupe_qa_list(qa_list)
        for qa_info in qa_list:
            if target_supplement:
                qa_info['supplement'] = merge_supplement_dicts(qa_info.get('supplement'), target_supplement)
                mapping_error = get_supplement_image_mapping_error(target_supplement)
                if mapping_error and not qa_info.get('supplement_mapping_error'):
                    qa_info['supplement_mapping_error'] = mapping_error
            qa_info['from_chat_history'] = prompt_str
        logging.info(f'direct_llm_answer_window_result:\n{result}\nqa_list:\n{qa_list}\n')
        result_qa_list.extend(qa_list)
    return clean_and_dedupe_qa_list(result_qa_list)
