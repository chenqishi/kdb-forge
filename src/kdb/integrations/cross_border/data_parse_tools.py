#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-11-21
"""
import string
import sys
import os
import re
import json
import time
import math
import logging
import copy
import traceback
import codecs
from datetime import datetime
from datetime import timedelta

from kdb.reporting.robot_answer_static import get_message_info
from kdb.shared.text.common_utils import is_contain_value

def gen_query_form_chat_history(data_file, filter_time=None, query_len_limit=5):
    """
    从聊天历史中提取query，并清除@用户名
    """
    dedup_dict = dict()

    with open(data_file, encoding='utf8') as df:
        for line in df:
            line = line.strip()
            fields = line.split('\t')
            data_time = fields[1]
            if filter_time and data_time < filter_time:
                continue
            chat_info = json.loads(fields[-1])
            if chat_info['type'] != 'reply':
                continue        
            if chat_info['ctype'] != 'TEXT':
                continue
            query = chat_info['content']
            #logging.info(f'{query}')
            # 清除@用户名的pattern
            query = re.sub(r'@\S+\s+', '', query)
            
            if len(query) < query_len_limit:
                continue
            query = query.replace('\n', ' ')
            
            if query in dedup_dict:
                continue
            dedup_dict[query] = 1
            conversion_id = chat_info['session_id']
            chat_name = chat_info['from_user_nickname']
            print(f'{conversion_id}\t{query}\t{chat_name}')
            

def gen_query_form_chat_history_noat(data_file):
    """
    从聊天历史中提取query，并清除@用户名
    """
    dedup_dict = dict()
    black_words = ['[图片]', '邀请', '这是我们的ai小助手']
    with open(data_file, encoding='utf8') as df:
        for line in df:
            line = line.strip()
            fields = line.split('\t')
            chat_info = json.loads(fields[-1])
            if 'original_info' not in chat_info:
                continue
            if not chat_info['original_info']['is_group'] or chat_info['original_info'].get('is_at'):
                continue

   
            query = chat_info['content'] if 'content' in chat_info else chat_info['original_info']['content']
            if any(word in query for word in black_words):
                continue    
            # 清除@用户名的pattern
            query = re.sub(r'@\S+\s+', '', query)
            
            if len(query) < 3:
                continue
            query = query.replace('\n', ' ')
            clear_query = query = re.sub(r'\[[^\]]*\]', '', query)
            if not clear_query:
                continue
            
            if query in dedup_dict:
                continue
            dedup_dict[query] = 1
            conversion_id = chat_info['session_id'] if 'session_id' in chat_info else chat_info['original_info']['actual_user_id']
            send_name = chat_info['original_info'].get('actual_user_nickname')
            send_name = send_name if send_name else chat_info['original_info'].get('from_user_nickname')
            if send_name.find('GV小助理') != -1:
                continue
            conversion_id = conversion_id if conversion_id else send_name
            print(f'{send_name}\t{conversion_id}\t{query}\t')


def gen_query_form_chat_history_all(data_file, json_field):
    """
    从聊天历史中提取query，并清除@用户名
    """
    dedup_dict = dict()
    black_words = ['邀请', '这是我们的ai小助手', '路飞智能', '路飞跨境军团', 'Luke', '石', '杨若愚']
    with open(data_file, encoding='utf8') as df:
        for line in df:
            line = line.strip()
            fields = line.split('\t')
            chat_info = json.loads(fields[json_field])
            if 'original_info' not in chat_info:
                continue
            #后面需要去掉
            #if not chat_info['original_info']['is_group']:
            #     continue

            send_name = chat_info['original_info'].get('actual_user_nickname')
            send_name = send_name if send_name else chat_info['original_info'].get('from_user_nickname')            
            query = chat_info['content'] if 'content' in chat_info else chat_info['original_info']['content']
        
            if chat_info['original_info']['ctype'] == 'IMAGE':
                if not os.path.exists(query):
                    continue
            filter_content = query + fields[0] + send_name
            if any(word in filter_content for word in black_words):
                continue    

            # 清除@用户名的pattern
            query = re.sub(r'@\S+\s+', '', query)
            
            if len(query) < 3:
                continue
            query = query.replace('\n', ' ')
            clear_query = query = re.sub(r'\[[^\]]*\]', '', query)
            if not clear_query:
                continue            
            if query in dedup_dict:
                continue
            dedup_dict[query] = 1
            conversion_id = chat_info['session_id'] if 'session_id' in chat_info else (chat_info['original_info'].get('other_user_id', '') + chat_info['original_info']['actual_user_id'])

            if send_name.find('GV小助理') != -1:
                continue
            conversion_id = conversion_id if conversion_id else send_name
            print(f'{send_name}\t{conversion_id}\t{query}')


def gen_query_and_answer_form_chat_history(data_file,  black_file, start_time, end_time):
    """
    从聊天历史中提取query和answer
    """
    start_time = str(start_time)
    end_time = str(end_time)
    try:
        start_time_dt = datetime.strptime(start_time, '%Y%m%d%H%M%S')
        end_time_dt = datetime.strptime(end_time, '%Y%m%d%H%M%S')
        start_time_timestamp = int(start_time_dt.timestamp())
        end_time_timestamp = int(end_time_dt.timestamp())
        logging.info(f"时间范围: {start_time_dt} ~ {end_time_dt}")
        logging.info(f"时间戳范围: {start_time_timestamp} ~ {end_time_timestamp}")
    except ValueError as e:
        logging.error(f"时间格式转换错误: {str(e)}")
        raise    
    black_name_words = set()
    with open(black_file, encoding='utf8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            black_name_words.add(line)
    
    msg_info_dict = dict()
    with open(data_file, encoding='utf8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fields = line.strip().split('\t')
            if len(fields) < 3:
                continue
            send_name, message_time, message_info_str = line.split('\t')
                
            message_info = json.loads(message_info_str)
            
            # 获取时间并记录日志
            create_time = message_info.get('create_time')
            if create_time is None:
                original_info = message_info.get('original_info', {})
                create_time = original_info.get('create_time', 0)
            
            # 添加调试日志
            logging.debug(f"消息时间戳: {create_time}, 消息ID: {message_info.get('msg_id')}")
            
            if create_time < start_time_timestamp or create_time > end_time_timestamp:
                logging.debug(f"消息被过滤，msgid: {message_info}  时间戳 {create_time} 不在范围 [{start_time_timestamp}, {end_time_timestamp}] 内")
                continue
            
            # 获取消息ID
            
            msg_id = message_info.get('msg_id')
            if not msg_id:
                original_info = message_info.get('original_info', {})
                msg_id = original_info.get('msg_id')
            if not msg_id:
                logging.debug(f"消息被过滤，msgid: {message_info}  没有msg_id")
                continue
            #if msg_id in dedup_dict:
            #    continue
            
            
            # 获取群组信息和用户ID
            group_name, user_id, user_name, is_group, is_at = get_message_info(message_info)            
            # 检查群名是否在黑名单中
            if is_contain_value(str(group_name), black_name_words) or is_contain_value(str(user_name), black_name_words):
                logging.debug(f"消息被过滤，msgid: {message_info.get('msg_id')}  群名 {group_name} 或 发送者 {send_name} 在黑名单中")
                continue
            
            if not user_id:
                logging.debug(f"消息被过滤，msgid: {message_info}  没有user_id")
                continue
            
            # 获取内容
            content = message_info.get('content', '')
            if not content:
                content = message_info.get('conent', '')  # 处理可能的拼写错误


            if isinstance(content, dict):
                content = json.dumps(content, ensure_ascii=False)
            # 根据条件分类统计, group_normal 群聊正常消息,  others 其他消息包括群聊私聊和群at消息
            category = 'group_normal' if is_group and not is_at else 'at_and_nogroup'
            if message_info.get('ctype') == 'ACCEPT_FRIEND':
                logging.debug(f"消息被过滤，msgid: {message_info.get('msg_id')}  不是单独发送的消息")
                continue  # 跳过后续的内容统计     
            if 'reply' in message_info:
                reply_content = message_info['reply'].get('content', '') or message_info['reply'].get('conent', '')
            else:
                reply_content = 'no_reply'
            conversion_id = message_info['session_id'] if 'session_id' in message_info else (str(message_info['original_info'].get('other_user_id', '')) + str(message_info['original_info']['actual_user_id']))
            if send_name.find('GV小助理') != -1:
                logging.debug(f"消息被过滤，msgid: {message_info.get('msg_id')}  发送者 {send_name} 是GV小助理")
                continue
            
            if content.find('<?xml') != -1:
                logging.debug(f"消息被过滤，msgid: {message_info.get('msg_id')}  内容包含xml")
                continue
            conversion_id = conversion_id if conversion_id else send_name  
            is_reply =  'reply' in message_info
            msg_data_type = message_info.get('ctype') if  is_reply else message_info.get('original_info', {}).get('ctype')
            msg_info_dict.setdefault(msg_id, {})
            msg_info_dict[msg_id]['user_id'] = user_id if user_id else msg_info_dict[msg_id].get('user_id', '')
            msg_info_dict[msg_id]['group_name'] = group_name if group_name else msg_info_dict[msg_id].get('group_name', '')
            msg_info_dict[msg_id]['conversion_id'] = conversion_id if conversion_id else msg_info_dict[msg_id].get('conversion_id', '')
            msg_info_dict[msg_id]['is_group'] = is_group if is_group else msg_info_dict[msg_id].get('is_group', False)
            msg_info_dict[msg_id]['is_at'] = is_at if is_at else msg_info_dict[msg_id].get('is_at', False)
            msg_info_dict[msg_id]['category'] = category if category else msg_info_dict[msg_id].get('category', '')
            msg_info_dict[msg_id]['content'] = content if content else msg_info_dict[msg_id].get('content', '')
            msg_info_dict[msg_id]['reply_content'] = reply_content if reply_content else msg_info_dict[msg_id].get('reply_content', '')
            msg_info_dict[msg_id]['msg_data_type'] = msg_data_type if msg_data_type else msg_info_dict[msg_id].get('msg_data_type', '')
            msg_info_dict[msg_id]['send_name'] = send_name if send_name else msg_info_dict[msg_id].get('send_name', '')
            msg_info_dict[msg_id]['user_name'] = user_name if user_name else msg_info_dict[msg_id].get('user_name', '')
            create_time_str = datetime.fromtimestamp(create_time).strftime('%Y-%m-%d %H:%M:%S')
            msg_info_dict[msg_id]['create_time'] = create_time_str if create_time_str else msg_info_dict[msg_id].get('create_time', '')
    print("create_time\tuser_id\tuser_name\tgroup_name\tmsg_id\tconversion_id\tis_group\tis_at\tmsg_data_type\tcategory\tcontent\treply_content")        
    for msg_id, msg_info in msg_info_dict.items():
        msg_info['content'] = msg_info['content'].replace('\n', ' ') if msg_info['content'] else ''
        msg_info['reply_content'] = msg_info['reply_content'].replace('\n', ' ') if msg_info['reply_content'] else ''
        msg_info['is_group'] = int(msg_info['is_group'])
        msg_info['is_at'] = int(msg_info['is_at'])
        print(f'{msg_info["create_time"]}\t{msg_info["user_id"]}\t{msg_info["user_name"]}\t{msg_info["group_name"]}\t{msg_id}\t{msg_info["conversion_id"]}\t{msg_info["is_group"]}\t{msg_info["is_at"]}\t{msg_info["msg_data_type"]}\t{msg_info["category"]}\t{msg_info["content"]}\t{msg_info["reply_content"]}')

 
def run_batch_gen_query_form_chat_history_all(data_file, data_field):
    with open(data_file, encoding='utf8') as df:
        for line in df:
            line = line.strip()
            fields = line.split('\t')
            wait_process_file = fields[data_field]
            gen_query_form_chat_history_all(wait_process_file, -1)

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
