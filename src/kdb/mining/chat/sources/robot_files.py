from kdb.mining.chat.media import build_image_message_content_and_supplement
from kdb.mining.chat.media import build_mixed_image_text_content_and_supplement
from kdb.mining.chat.media import format_supplement_image_placeholders
from kdb.mining.chat.media import is_image_placeholder_or_address
from kdb.mining.chat.message_cleaning import is_image_message_type
from kdb.mining.chat.message_cleaning import is_image_mixed_message_type
from kdb.mining.chat.message_cleaning import is_text_message_type
from kdb.mining.chat.message_cleaning import parse_message_time_ts
from kdb.mining.chat.message_cleaning import sanitize_chat_content
from kdb.mining.chat.quality.noise import is_noise_chat_content
from kdb.mining.chat.quality.noise import should_keep_image_payload_when_text_is_noise
from kdb.shared.text.common_utils import load_attr_map_dict as load_3file_dict
import json
import logging
import traceback

def load_white_list_dict(white_list_file):
    """
    加载白名单字典
    """
    white_list_dict = load_3file_dict(white_list_file)
    for robot, group_dict in white_list_dict.items():
        for group, white_list in group_dict.items():
            group_dict[group] = white_list.split(',')
    return white_list_dict


def load_robot_room_type(line_config_file, filter_group_name='all'):
    """
    config_file:#机器人\t群名\t平台\t类型(转发/普通群)
    """
    config = dict()
    with open(line_config_file, encoding='utf8') as f:
        for line in f:
            line = line.strip('\n')
            if not line:
                continue
            fields = line.split('\t')
            robot = fields[0]
            group = fields[1]
            platform = fields[2]
            room_type = fields[3]
            if filter_group_name != 'all' and group != filter_group_name:
                continue
            if robot not in config:
                config[robot] = {}
            black_group = set()
            if group == 'all':
                if len(fields) > 4:
                    black_group = set(item for item in fields[4].split('|') if item)
            config[robot][group] = {
                'platform': platform,
                'type': room_type,
                'black_group': black_group
            }
    return config


def save_3file_dict(save_file, data_dict):
    """
    保存3级字典
    """
    with open(save_file, 'w', encoding='utf8') as f:
        for robot, group_dict in data_dict.items():
            for group, value in group_dict.items():
                f.write(f"{robot}\t{group}\t{value}\n")


def get_message_speaker(message_info, fallback_send_name, robot_name=None):
    original_info = message_info.get('original_info', {}) or {}
    if message_info.get('type') == 'reply':
        return robot_name or fallback_send_name, '', '', '', '', ''

    actual_user_id = original_info.get('actual_user_id', '')
    actual_user_nickname = original_info.get('actual_user_nickname', '')
    from_user_id = original_info.get('from_user_id', '')
    from_user_nickname = original_info.get('from_user_nickname', '')
    send_user_id = actual_user_id or from_user_id
    send_user = (
        actual_user_nickname
        or from_user_nickname
        or message_info.get('send_name')
        or fallback_send_name
        or send_user_id
    )
    return send_user, send_user_id, actual_user_id, actual_user_nickname, from_user_id, from_user_nickname


def load_and_reorg_one_robot_data(robot_name, data_file, room_type_config,
                                  robot_room_process_record,  need_robot_reply=False):
    """
    加载并重组单个机器人的数据
    """
    has_process_content = dict()
    reorga_chat_dict = dict() # 重组后的对话数据，key为群名，value为对话数据list
    image_count_by_group = dict()
    with open(data_file, encoding='utf8') as f:
        for line in f:
            try:
                line = line.strip('\n')
                if not line:
                    continue
                send_name, message_time, message_info_str = line.split('\t')
                message_info = json.loads(message_info_str)

                if not message_info.get('original_info', {}).get('is_group', False):  # 不处理单聊信息
                    continue
                group_name = message_info.get('original_info', {}).get('other_user_nickname', '')
                group_name = group_name if group_name else message_info.get('original_info', {}).get('other_user_id', '')
                #if group_name not in room_type_config:
                #    continue
                # 如果该数据已经处理过，则跳过
                processed_time = robot_room_process_record.get(robot_name, {}).get(group_name, '0000-00-00 00:00:00')
                if message_time <= processed_time:
                    continue
                if 'conent' in message_info: # 原始数据文件打错了,需要修正
                    message_info['content'] = message_info['conent']
                if message_info.get('type') == 'all':
                    ctype = message_info['original_info']['ctype']
                    send_content = message_info.get('content', '')
                    speaker_info = get_message_speaker(message_info, send_name, robot_name=robot_name)
                elif message_info.get('type') == 'reply': # 该数据是机器人回复数据
                    if not need_robot_reply:
                        continue
                    send_content = message_info['reply']['conent']
                    ctype = message_info['reply']['type']
                    speaker_info = get_message_speaker(message_info, send_name, robot_name=robot_name)
                else:
                    continue
                supplement = {}
                if is_text_message_type(ctype):
                    send_content = sanitize_chat_content(send_content)
                    if is_image_placeholder_or_address(send_content):
                        image_count_by_group[group_name] = image_count_by_group.get(group_name, 0) + 1
                        image_label = f"图片{image_count_by_group[group_name]}"
                        send_content, supplement = build_image_message_content_and_supplement(
                            message_info,
                            send_content,
                            'IMAGE_FROM_TEXT',
                            image_label
                        )
                        ctype = 'IMAGE_FROM_TEXT'
                    elif is_noise_chat_content(send_content):
                        continue
                elif is_image_mixed_message_type(ctype):
                    next_image_index = image_count_by_group.get(group_name, 0) + 1
                    send_content, supplement, used_image_count = build_mixed_image_text_content_and_supplement(
                        message_info,
                        send_content,
                        ctype,
                        next_image_index
                    )
                    if used_image_count:
                        image_count_by_group[group_name] = image_count_by_group.get(group_name, 0) + used_image_count
                    send_content = sanitize_chat_content(send_content)
                    if supplement and is_noise_chat_content(send_content):
                        if should_keep_image_payload_when_text_is_noise(send_content):
                            send_content = format_supplement_image_placeholders(supplement)
                        else:
                            continue
                    if not send_content or (not supplement and is_noise_chat_content(send_content)):
                        continue
                elif is_image_message_type(ctype):
                    image_count_by_group[group_name] = image_count_by_group.get(group_name, 0) + 1
                    image_label = f"图片{image_count_by_group[group_name]}"
                    send_content, supplement = build_image_message_content_and_supplement(
                        message_info,
                        send_content,
                        ctype,
                        image_label
                    )
                else:
                    continue
                send_user, send_user_id, actual_user_id, actual_user_nickname, from_user_id, from_user_nickname = speaker_info
                dedupe_key = (group_name, send_user_id or send_user, send_content)
                current_ts = parse_message_time_ts(message_time)
                last_ts = has_process_content.get(dedupe_key)
                if last_ts is not None and current_ts is not None and abs(current_ts - last_ts) <= 120:
                    continue
                if last_ts is not None and current_ts is None:
                    continue
                has_process_content[dedupe_key] = current_ts
                new_message_info = {
                    'msg_id': message_info.get('original_info', {}).get('msg_id', ''),
                    'send_user': send_user,
                    'send_user_id': send_user_id,
                    'actual_user_id': actual_user_id,
                    'actual_user_nickname': actual_user_nickname,
                    'from_user_id': from_user_id,
                    'from_user_nickname': from_user_nickname,
                    'group_id': message_info.get('original_info', {}).get('other_user_id', ''),
                    'group_name': group_name,
                    'content': send_content,
                    'ctype': ctype,
                    'message_time': message_time,
                }
                if supplement:
                    new_message_info['supplement'] = supplement
                reorga_chat_dict.setdefault(group_name, []).append(new_message_info)
            except:
                tb = traceback.format_exc()
                logging.error(f'error_tb:{tb}')
                logging.error(f'error_line:{line}')
                #exit(1)
                continue
    return reorga_chat_dict
