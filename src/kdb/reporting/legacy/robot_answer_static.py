import json
import logging
from collections import defaultdict
from typing import Dict, Set, List, Tuple
from commons import channel_communicate_by_request
from commons.common_utils import is_contain_value
import traceback
from datetime import datetime

NO_ANSWER_KEYWORDS = ['不太清楚', '未能找到直接相关的答案']
def get_message_info(message_info: dict) -> tuple:
    """
    根据消息类型获取群名和用户ID
    
    Args:
        message_info: 消息信息字典
    
    Returns:
        tuple: (group_name, user_id, is_group, is_at)
    """
    msg_type = message_info.get('type')
    
    if msg_type == 'all':
        original_info = message_info.get('original_info', {})
        is_group = original_info.get('is_group', False)
        is_at = original_info.get('is_at', False)
        
        # 获取群名/对话名称
        group_name = original_info.get('other_user_nickname', '')
        if not group_name:
            group_name = original_info.get('other_user_id', '')
            
        # 获取用户ID
        user_id = original_info.get('actual_user_id') if is_group else original_info.get('other_user_id')
        user_name = original_info.get('actual_user_nickname') if is_group else original_info.get('other_user_nickname')
        
    elif msg_type == 'reply':
        # reply类型消息从原始消息中获取信息
        is_group = message_info.get('is_group', False)
        is_at = message_info.get('is_at', False)
        
        # 获取群名/对话名称
        group_name = message_info.get('other_user_nickname', '')
        if not group_name:
            group_name = message_info.get('other_user_id', '')
            
        # 获取用户ID
        user_id = message_info.get('actual_user_id') if is_group else message_info.get('other_user_id')
        user_name = message_info.get('actual_user_nickname') if is_group else message_info.get('other_user_nickname')
        
    else:
        # 其他类型消息，尝试从顶层字段获取
        is_group = message_info.get('is_group', False)
        is_at = message_info.get('is_at', False)
        group_name = message_info.get('other_user_nickname', '') or message_info.get('other_user_id', '')
        user_id = message_info.get('actual_user_id') if is_group else message_info.get('other_user_id')
        user_name = message_info.get('actual_user_nickname') if is_group else message_info.get('other_user_nickname')
    return group_name, user_id, user_name, is_group, is_at

def gen_one_robot_static_report(data_file: str, start_time: str, end_time: str, black_groups: set = None) -> Dict:
    """
    生成单个机器人的统计报告
    
    Args:
        data_file: 输入数据文件路径
        start_time: 开始时间，格式 YYYYMMDDHHmmSS
        end_time: 结束时间，格式 YYYYMMDDHHmmSS
        black_groups: 黑名单群组集合，群名包含这些字符串的将被过滤
    
    Returns:
        Dict: 包含统计结果的字典
    """
    # 转换时间格式为时间戳
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

    # 初始化黑名单集合
    black_groups = black_groups or set()

    # 初始化统计结果
    stats = {
        'group_normal': {  # is_group=True, is_at=False
            'messages': set(),  # 存储msg_id
            'users': set(),
            'contents': set(),
            'replied_contents': set(),  # 存储被回复的内容
            'valid_replied_contents': set(),  # 存储有效回复的内容
            'replied_users': set(),  # 存储被回复的用户
            'valid_replied_users': set()  # 存储有效回复的用户
        },
        'others': {  # 其他情况
            'messages': set(),
            'users': set(),
            'contents': set(),
            'replied_contents': set(),
            'valid_replied_contents': set(),
            'replied_users': set(),
            'valid_replied_users': set(),
            'accept_users': set()  # 存储元组 (fromusername, fromnickname)
        }
    }
    
    try:
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
                
                # 获取群组信息和用户ID
                group_name, user_id, user_name, is_group, is_at = get_message_info(message_info)
                
                # 检查群名是否在黑名单中
                #if any(black_str in group_name for black_str in black_groups) or any(black_str in user_name for black_str in black_groups):
                if is_contain_value(str(group_name), black_groups) or is_contain_value(str(user_name), black_groups):
                    logging.debug(f"消息被过滤，msgid: {message_info.get('msg_id')}  群名 {group_name} 在黑名单中")
                    continue
                
                if not user_id:
                    logging.debug(f"消息被过滤，msgid: {message_info}  没有user_id")
                    continue
                
                # 获取内容
                content = message_info.get('content', '')
                if not content:
                    content = message_info.get('conent', '')  # 处理可能的拼写错误
                
                # 根据条件分类统计
                category = 'group_normal' if is_group and not is_at else 'others'
                
                # 处理好友请求消息
                if message_info.get('ctype') == 'ACCEPT_FRIEND':
                    content_obj = message_info.get('content', {})
                    if isinstance(content_obj, dict):
                        friend_username = content_obj.get('fromusername')
                        friend_nickname = content_obj.get('fromnickname', '')
                        if friend_username and friend_nickname:
                            stats['others']['accept_users'].add((friend_username, friend_nickname))
                    continue  # 跳过后续的内容统计
                
                # 基础消息统计（使用msg_id去重）
                if msg_id not in stats[category]['messages']:
                    stats[category]['messages'].add(msg_id)
                    stats[category]['users'].add(user_id)
                
                    # 内容统计
                    if content and isinstance(content, str):
                        stats[category]['contents'].add(content)
                
                # 回复统计（独立处理）
                if 'reply' in message_info:
                    stats[category]['replied_contents'].add(content)
                    stats[category]['replied_users'].add(user_id)
                    # 检查是否是有效回复（不包含"不太清楚"）
                    reply_content = message_info['reply'].get('content', '') or message_info['reply'].get('conent', '')
                    if reply_content and not is_contain_value(reply_content, NO_ANSWER_KEYWORDS):
                        stats[category]['valid_replied_contents'].add(content)
                        stats[category]['valid_replied_users'].add(user_id)
                            
    except Exception as e:
        logging.error(f"处理文件时发生错误: {str(e)}")
        raise
        
    # 将统计结果转换为可序列化的格式
    result = {
        'group_normal': {
            'message_count': len(stats['group_normal']['messages']),
            'unique_user_count': len(stats['group_normal']['users']),
            'unique_content_count': len(stats['group_normal']['contents']),
            'replied_content_count': len(stats['group_normal']['replied_contents']),
            'valid_replied_content_count': len(stats['group_normal']['valid_replied_contents']),
            'replied_user_count': len(stats['group_normal']['replied_users']),
            'valid_replied_user_count': len(stats['group_normal']['valid_replied_users']),
            # 保留原始集合数据
            'contents': list(stats['group_normal']['contents']),
            'replied_contents': list(stats['group_normal']['replied_contents']),
            'valid_replied_contents': list(stats['group_normal']['valid_replied_contents']),
            'replied_users': list(stats['group_normal']['replied_users']),
            'valid_replied_users': list(stats['group_normal']['valid_replied_users'])
        },
        'others': {
            'message_count': len(stats['others']['messages']),
            'unique_user_count': len(stats['others']['users']),
            'unique_content_count': len(stats['others']['contents']),
            'replied_content_count': len(stats['others']['replied_contents']),
            'valid_replied_content_count': len(stats['others']['valid_replied_contents']),
            'replied_user_count': len(stats['others']['replied_users']),
            'valid_replied_user_count': len(stats['others']['valid_replied_users']),
            'accept_user_count': len(stats['others']['accept_users']),  # 新增字段
            # 保留原始集合数据
            'contents': list(stats['others']['contents']),
            'replied_contents': list(stats['others']['replied_contents']),
            'valid_replied_contents': list(stats['others']['valid_replied_contents']),
            'replied_users': list(stats['others']['replied_users']),
            'valid_replied_users': list(stats['others']['valid_replied_users']),
            'accept_users': list(stats['others']['accept_users'])  # 新增字段，保存原始数据
        }
    }
    
    return result

def format_report_message(robot_name: str, platform: str, report_data: Dict, start_time: str, end_time: str) -> str:
    """
    将统计报告格式化为消息字符串
    """
    start_time_dt = datetime.strptime(start_time, '%Y%m%d%H%M%S')
    end_time_dt = datetime.strptime(end_time, '%Y%m%d%H%M%S')
    start_time_str = start_time_dt.strftime('%Y-%m-%d %H:%M:%S')
    end_time_str = end_time_dt.strftime('%Y-%m-%d %H:%M:%S')
    msg = f"机器人[{robot_name}]({platform})统计报告, 统计时间段为:{start_time_str} ~ {end_time_str }:\n"
    
    
    # 直接咨询消息统计
    others_data = report_data['others']
    total_content = others_data['unique_content_count']
    total_users = others_data['unique_user_count']
    content_reply_ratio = round(others_data['replied_content_count'] / total_content * 100, 2) if total_content > 0 else 0
    content_valid_reply_ratio = round(others_data['valid_replied_content_count'] / total_content * 100, 2) if total_content > 0 else 0
    user_reply_ratio = round(others_data['replied_user_count'] / total_users * 100, 2) if total_users > 0 else 0
    user_valid_reply_ratio = round(others_data['valid_replied_user_count'] / total_users * 100, 2) if total_users > 0 else 0
    
    msg += "\n直接咨询消息统计(私聊/群里@):\n"
    msg += f"- 总消息数: {others_data['message_count']}\n"
    msg += f"- 不重复用户数: {others_data['unique_user_count']}\n"
    msg += f"- 不重复内容数: {others_data['unique_content_count']}\n"
    msg += f"- 被回复内容数: {others_data['replied_content_count']} ({content_reply_ratio}%)\n"
    msg += f"- 有效回复内容数(即回复内容非'不太清楚'): {others_data['valid_replied_content_count']} ({content_valid_reply_ratio}%)\n"
    msg += f"- 被回复用户数: {others_data['replied_user_count']} ({user_reply_ratio}%)\n"
    msg += f"- 有效回复用户数(即回复内容非'不太清楚'): {others_data['valid_replied_user_count']} ({user_valid_reply_ratio}%)\n"
    msg += f"- 接受好友请求数: {others_data['accept_user_count']}\n"
    if others_data['accept_user_count'] > 0:
        msg += "  接受的好友列表:\n"
        for _, nickname in sorted(others_data['accept_users']):  # 按昵称排序
            msg += f"  * {nickname}\n"
    
    # 普通群消息统计
    group_data = report_data['group_normal']
    total_content = group_data['unique_content_count']
    total_users = group_data['unique_user_count']
    content_reply_ratio = round(group_data['replied_content_count'] / total_content * 100, 2) if total_content > 0 else 0
    content_valid_reply_ratio = round(group_data['valid_replied_content_count'] / total_content * 100, 2) if total_content > 0 else 0
    user_reply_ratio = round(group_data['replied_user_count'] / total_users * 100, 2) if total_users > 0 else 0
    user_valid_reply_ratio = round(group_data['valid_replied_user_count'] / total_users * 100, 2) if total_users > 0 else 0
    
    msg += "\n非直接消息统计(通过热心助手回答):\n"
    msg += f"- 总消息数: {group_data['message_count']}\n"
    msg += f"- 不重复用户数: {group_data['unique_user_count']}\n"
    msg += f"- 不重复内容数: {group_data['unique_content_count']}\n"
    msg += f"- 被回复内容数: {group_data['replied_content_count']} ({content_reply_ratio}%)\n"
    msg += f"- 有效回复内容数(即回复内容非'不太清楚'): {group_data['valid_replied_content_count']} ({content_valid_reply_ratio}%)\n"
    msg += f"- 被回复用户数: {group_data['replied_user_count']} ({user_reply_ratio}%)\n"
    msg += f"- 有效回复用户数(即回复内容非'不太清楚'): {group_data['valid_replied_user_count']} ({user_valid_reply_ratio}%)\n"

    
    return msg

def run_batch_robot_static_report(input_file: str, start_time: str, end_time: str, 
                                data_field: int = 5, output_file: str = None, 
                                black_groups_file: str = None):
    """
    批量处理机器人统计报告
    
    Args:
        input_file: 输入文件路径，格式：机器人\t类型\t平台\t通知id\t发送url\t数据地址
        start_time: 开始时间，格式：YYYYMMDDHHmmSS
        end_time: 结束时间，格式：YYYYMMDDHHmmSS
        data_field: 数据地址在输入文件中的字段位置（从0开始）
        output_file: 输出文件路径
        black_groups_file: 黑名单群组文件路径
    """
    # 处理黑名单参数
    black_groups_set = set()
    if black_groups_file:
        with open(black_groups_file, encoding='utf8') as f:
            for line in f:
                black_groups_set.add(line.strip())
    
    try:
        if isinstance(start_time, int):
            start_time = str(start_time)
        if isinstance(end_time, int):
            end_time = str(end_time)
        with open(input_file, encoding='utf8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                
                try:
                    fields = line.split('\t')
                    robot_name = fields[0]
                    robot_type = fields[1]
                    platform = fields[2]
                    notify_id = fields[3]
                    send_url = fields[4]
                    data_file = fields[data_field]
                    sender = channel_communicate_by_request.ChannelRequestCommunicate(base_url=send_url)
                    
                    # 生成统计报告
                    report_data = gen_one_robot_static_report(
                        data_file, 
                        start_time, 
                        end_time,
                        black_groups=black_groups_set
                    )
                    
                    # 输出详细信息
                    detail_info = {
                        'base_info': line,
                        'report_data': report_data,
                        'invalid_replies': {
                            'group_normal': {
                                'contents': [c for c in report_data['group_normal']['replied_contents'] 
                                            if c not in report_data['group_normal']['valid_replied_contents']],
                                'users': [u for u in report_data['group_normal']['replied_users'] 
                                         if u not in report_data['group_normal']['valid_replied_users']]
                            },
                            'others': {
                                'contents': [c for c in report_data['others']['replied_contents'] 
                                            if c not in report_data['others']['valid_replied_contents']],
                                'users': [u for u in report_data['others']['replied_users'] 
                                         if u not in report_data['others']['valid_replied_users']]
                            }
                        }
                    }
                    
                    with open(output_file, 'a', encoding='utf8') as f:
                        f.write(f"{json.dumps(detail_info, ensure_ascii=False)}\n")
                    
                    # 发送通知部分保持不变
                    notify_ids = notify_id.split('|')
                    for notify_id in notify_ids:
                        notify_id, is_group = notify_id.split(':')
                        is_group = int(is_group)
                        message = format_report_message(robot_name, platform, report_data, start_time, end_time)
                        logging.info(f"发送通知: {message}, notify_id: {notify_id}, is_group: {is_group}")
                        sender.send_wx(
                            content=message,
                            receiver=notify_id,
                            is_group=is_group
                        )
                        
                except Exception as e:
                    logging.error(f"处理机器人[{robot_name}]时发生错误: {str(e)}")
                    logging.error(traceback.format_exc())
                    continue
                    
    except Exception as e:
        logging.error(f"处理文件时发生错误: {str(e)}")
        logging.error(traceback.format_exc())
        raise

def static_norm_query_report(input_file: str, output_file: str):
    """统计标准化查询报告
    
    Args:
        input_file: 输入文件路径
        output_file: 输出文件路径
    """
    # 统计数据存储
    total_stats = {
        'at_and_nogroup': {
            'messages': set(),
            'users': set(),
            'contents': set(),
            'replied_contents': set(),
            'valid_replied_contents': set(),
            'replied_users': set(),
            'valid_replied_users': set()
        },
        'group_normal': {
            'messages': set(),
            'users': set(),
            'contents': set(),
            'replied_contents': set(),
            'valid_replied_contents': set(),
            'replied_users': set(),
            'valid_replied_users': set()
        }
    }
    
    # query_norm维度的统计
    norm_stats = {}  # 以query_norm为key的统计
    
    # 修改query_norm统计的数据结构，增加queries列表
    query_norm_stats = {}  # query_norm的统计
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            fields = line.strip().split('\t')
            if len(fields) != 13:
                continue
            create_time = fields[0]
            user_id = fields[1]
            user_name = fields[2]
            msg_id = fields[4]
            category = fields[9]
            content = fields[10]
            query_norm = fields[11]
            reply_content = fields[12]
            
            # 1. 直接统计
            total_stats[category]['messages'].add(msg_id)
            total_stats[category]['users'].add(user_id)
            total_stats[category]['contents'].add(content)
            
            if reply_content != "no_reply":
                total_stats[category]['replied_contents'].add(content)
                total_stats[category]['replied_users'].add(user_id)
                if not any(kw in reply_content for kw in ['不太清楚', '未能找到直接相关的答案']):
                    total_stats[category]['valid_replied_contents'].add(content)
                    total_stats[category]['valid_replied_users'].add(user_id)
            
            # 2. query_norm维度统计
            key = f"{query_norm}_{category}"
            if key not in norm_stats:
                norm_stats[key] = {
                    'messages': set(),
                    'users': set(),
                    'contents': set(),
                    'replied_contents': set(),
                    'valid_replied_contents': set(),
                    'replied_users': set(),
                    'valid_replied_users': set(),
                    'category': category
                }
            
            stats = norm_stats[key]
            stats['messages'].add(msg_id)
            stats['users'].add(user_id)
            stats['contents'].add(content)
            
            if reply_content != "no_reply":
                stats['replied_contents'].add(content)
                stats['replied_users'].add(user_id)
                if not any(kw in reply_content for kw in ['不太清楚', '未能找到直接相关的答案', '无法获取有效相应']):
                    stats['valid_replied_contents'].add(content)
                    stats['valid_replied_users'].add(user_id)
            
            # 添加query_norm统计
            if query_norm not in query_norm_stats:
                query_norm_stats[query_norm] = {
                    "total": 0,
                    "valid_replies": 0,
                    "queries": set()  # 使用set去重
                }
            query_norm_stats[query_norm]["total"] += 1
            query_norm_stats[query_norm]["queries"].add(content)  # 添加原始query
            if reply_content != "no_reply" and not any(kw in reply_content for kw in ['不太清楚', '未能找到直接相关的答案']):
                query_norm_stats[query_norm]["valid_replies"] += 1
    
    # 写入统计结果
    with open(output_file, 'w', encoding='utf-8') as f:
        # 1. 直接统计结果
        f.write("1. 直接统计结果:\n")
        for category in ['at_and_nogroup', 'group_normal']:
            stats = total_stats[category]
            category_name = '私聊/群里@' if category == 'at_and_nogroup' else '群消息'
            f.write(f"\n{category_name}统计:\n")
            f.write(f"- 总消息数: {len(stats['messages'])}\n")
            f.write(f"- 不重复用户数: {len(stats['users'])}\n")
            f.write(f"- 不重复内容数: {len(stats['contents'])}\n")
            content_reply_ratio = len(stats['replied_contents']) / len(stats['contents']) * 100 if stats['contents'] else 0
            content_valid_reply_ratio = len(stats['valid_replied_contents']) / len(stats['contents']) * 100 if stats['contents'] else 0
            user_reply_ratio = len(stats['replied_users']) / len(stats['users']) * 100 if stats['users'] else 0
            user_valid_reply_ratio = len(stats['valid_replied_users']) / len(stats['users']) * 100 if stats['users'] else 0
            f.write(f"- 被回复内容数: {len(stats['replied_contents'])} ({content_reply_ratio:.2f}%)\n")
            f.write(f"- 有效回复内容数: {len(stats['valid_replied_contents'])} ({content_valid_reply_ratio:.2f}%)\n")
            f.write(f"- 被回复用户数: {len(stats['replied_users'])} ({user_reply_ratio:.2f}%)\n")
            f.write(f"- 有效回复用户数: {len(stats['valid_replied_users'])} ({user_valid_reply_ratio:.2f}%)\n")
        
        # 2. query_norm维度去重统计
        f.write("\n2. query_norm去重统计结果:\n")
        category_stats = {'at_and_nogroup': {'messages': set(), 'users': set(), 'contents': set(), 'replied_contents': set(), 
                         'valid_replied_contents': set(), 'replied_users': set(), 'valid_replied_users': set()},
                         'group_normal': {'messages': set(), 'users': set(), 'contents': set(), 'replied_contents': set(),
                         'valid_replied_contents': set(), 'replied_users': set(), 'valid_replied_users': set()}}
        
        for norm_stat in norm_stats.values():
            cat = norm_stat['category']
            for key in ['messages', 'users', 'contents', 'replied_contents', 'valid_replied_contents', 
                       'replied_users', 'valid_replied_users']:
                category_stats[cat][key].update(norm_stat[key])
        
        for category, stats in category_stats.items():
            category_name = '私聊/群里@' if category == 'at_and_nogroup' else '群消息'
            f.write(f"\n{category_name}统计:\n")
            f.write(f"- 总消息数: {len(stats['messages'])}\n")
            f.write(f"- 不重复用户数: {len(stats['users'])}\n")
            f.write(f"- 不重复内容数: {len(stats['contents'])}\n")
            content_reply_ratio = len(stats['replied_contents']) / len(stats['contents']) * 100 if stats['contents'] else 0
            content_valid_reply_ratio = len(stats['valid_replied_contents']) / len(stats['contents']) * 100 if stats['contents'] else 0
            user_reply_ratio = len(stats['replied_users']) / len(stats['users']) * 100 if stats['users'] else 0
            user_valid_reply_ratio = len(stats['valid_replied_users']) / len(stats['users']) * 100 if stats['users'] else 0
            f.write(f"- 被回复内容数: {len(stats['replied_contents'])} ({content_reply_ratio:.2f}%)\n")
            f.write(f"- 有效回复内容数: {len(stats['valid_replied_contents'])} ({content_valid_reply_ratio:.2f}%)\n")
            f.write(f"- 被回复用户数: {len(stats['replied_users'])} ({user_reply_ratio:.2f}%)\n")
            f.write(f"- 有效回复用户数: {len(stats['valid_replied_users'])} ({user_valid_reply_ratio:.2f}%)\n")
        
        # 3. query_norm详细统计
        f.write("\n3. query_norm详细统计结果:\n")
        f.write("query_norm\t出现次数\t占比\t有效回答率\t相关query示例\n")
        
        total_messages = sum(stats["total"] for stats in query_norm_stats.values())
        
        # 按照出现次数排序
        sorted_stats = sorted(
            query_norm_stats.items(),
            key=lambda x: x[1]["total"],
            reverse=True
        )
        
        for query_norm, stats in sorted_stats:
            ratio = stats["total"] / total_messages * 100
            reply_ratio = stats["valid_replies"] / stats["total"] * 100 if stats["total"] > 0 else 0
            # 取前10个query示例
            if len(stats["queries"]) > 10:
                query_examples = list(stats["queries"])[:10]
            else:
                query_examples = list(stats["queries"])
            query_examples_str = "|".join(query_examples)
            query_examples_str = query_examples_str.replace('\n', ' ')
            query_norm = query_norm.replace('\n', ' ')
            f.write(f"{query_norm}\t{stats['total']}\t{ratio:.2f}%\t{reply_ratio:.2f}%\t{query_examples_str}\n")

if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    import fire
    fire.Fire({
        'gen_one_robot_static_report': gen_one_robot_static_report,
        'run_batch_robot_static_report': run_batch_robot_static_report,
        'static_norm_query_report': static_norm_query_report
    })



