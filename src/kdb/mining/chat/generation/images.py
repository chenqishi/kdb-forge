from kdb.mining.chat.sources.robot_files import load_white_list_dict
from kdb.shared.config.global_config import GLOBAL_CONFIG as config
from kdb.shared.text.common_utils import load_attr_map_dict as load_3file_dict
import json
import kdb.shared.clients.dify_tools as dify_tools
import logging
import os
import sys
import traceback

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
            if group == 'all':
                if len(fields) > 4:
                    black_group = set(fields[4].split('|'))
            else:
                black_group = set()
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


def load_and_reorg_one_robot_data(robot_name, data_file, room_type_config, 
                                  robot_room_process_record,  need_robot_reply=False):
    """
    加载并重组单个机器人的数据
    """
    has_process_content = dict()
    reorga_chat_dict = dict() # 重组后的对话数据，key为群名，value为对话数据list
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
                    send_user = message_info['send_name']
                    send_content = message_info['conent'] # 原始数据文件打错了
                    ctype = message_info['original_info']['ctype']
                elif message_info.get('type') == 'reply': # 该数据是机器人回复数据
                    if not need_robot_reply:
                        continue
                    send_user = robot_name
                    send_content = message_info['reply']['conent']
                    ctype = message_info['reply']['type']
                else:
                    continue
                new_message_info = {'send_user': send_user, 'content': send_content, 'ctype': ctype}
                new_message_info['message_time'] = message_time
                if ctype == 'IMAGE':
                    new_message_info['is_image_download'] = message_info.get('is_image_download', False)

                reorga_chat_dict.setdefault(group_name, []).append(new_message_info)
            except:            
                tb = traceback.format_exc()
                logging.error(f'error_tb:{tb}')
                logging.error(f'error_line:{line}')
                exit(1)
    return reorga_chat_dict


def get_forword_group_bigmodel_prompt(group_name, group_chat_list, sep='\n------\n'):
    """
    获取转发群的大模型prompt
    """
    prompt_list = []
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for message_info in group_chat_list:
        prompt_list.append(f"{message_info['content']}")
    prompt_str = sep.join(prompt_list)
    return prompt_str


def get_normal_group_bigmodel_prompt(group_name, group_chat_list, white_name_list, sep='\n------\n'):
    """
    获取普通群的大模型prompt
    """
    prompt_list = []
    group_chat_list = sorted(group_chat_list, key=lambda x: x['message_time'])
    for message_info in group_chat_list:
        prompt_list.append(f"{message_info['send_user']}: {message_info['content']}")
    prompt_str = sep.join(prompt_list)
    if white_name_list:
        prompt_str = f"专家用户：{','.join(white_name_list)}\n{prompt_str}"
    return prompt_str


def get_image_group_chat_data(group_name, chat_list, image_neighbor_nums):
    """
    获取图片群的对话数据，将图片消息及其前后相邻的消息组织在一起
    
    Args:
        group_name: 群组名称
        chat_list: 聊天消息列表
        image_neighbor_nums: 图片消息前后需要收集的消息数量
    
    Returns:
        dict: key为图片路径，value为包含图片消息及其上下文的字典
    """
    # 按时间排序
    sorted_chat_list = sorted(chat_list, key=lambda x: x['message_time'])
    
    # 初始化结果字典
    image_org_data = {}
    
    # 遍历查找图片消息
    for i, message in enumerate(sorted_chat_list):
        # 检查是否为图片消息且已下载
        if (message.get('ctype') == 'IMAGE' and 
            message.get('is_image_download', False)):
            
            image_path = message.get('content', '')
            if not image_path:
                logging.info(f'image_path is empty, message_info:\n{message}\n')
                continue
                
            # 收集图片消息前面的文本消息
            pre_messages = []
            count = 0
            idx = i - 1
            while count < image_neighbor_nums and idx >= 0:
                if sorted_chat_list[idx].get('ctype') == 'TEXT':
                    pre_messages.append(sorted_chat_list[idx])
                    count += 1
                idx -= 1
            pre_messages.reverse()  # 保持时间顺序
            
            # 收集图片消息后面的文本消息
            post_messages = []
            count = 0
            idx = i + 1
            while count < image_neighbor_nums and idx < len(sorted_chat_list):
                if sorted_chat_list[idx].get('ctype') == 'TEXT':
                    post_messages.append(sorted_chat_list[idx])
                    count += 1
                idx += 1
            
            # 组织数据
            image_org_data[image_path] = {
                'image_message': message,
                'pre_image_chats': pre_messages,
                'post_image_chats': post_messages
            }
    
    return image_org_data


def get_image_chats_prompt(image_data, group_type, group_name, white_name_list=None):
    """
    生成图片相关对话的prompt
    
    Args:
        image_data: 包含图片前后文本消息的字典
        group_type: 群组类型(forward/normal)
        group_name: 群组名称
        white_name_list: 白名单用户列表(普通群需要)
    
    Returns:
        str: 组织好的prompt
    """
    pre_chats = image_data['pre_image_chats']
    post_chats = image_data['post_image_chats']
    
    if group_type == 'forward':
        pre_prompt = get_forword_group_bigmodel_prompt(group_name, pre_chats)
        post_prompt = get_forword_group_bigmodel_prompt(group_name, post_chats)
    else:
        pre_prompt = get_normal_group_bigmodel_prompt(group_name, pre_chats, white_name_list)
        post_prompt = get_normal_group_bigmodel_prompt(group_name, post_chats, white_name_list)
    
    final_prompt = f"图片前数据:{pre_prompt}\n图片后数据:{post_prompt}"
    return final_prompt


def process_forward_group_data(group_name, platform, group_chat_list, group_white_list, dify_model):
    """
    处理转发群的数据
    """
    result_qa_list = []
    user_chatlist_dict = dict()
    
    # 按用户分组聊天记录
    
    for message_info in group_chat_list:
        user_chatlist_dict.setdefault(message_info['send_user'], []).append(message_info)
    logging.info(f'user_chatlist_dict:\t{len(user_chatlist_dict)}\t{len(list(user_chatlist_dict.values())[0])}')
    # 处理每个用户的聊天记录
    for user, chat_list in user_chatlist_dict.items():
        # 处理图片数据
        has_image_num = len(list(filter(lambda x: x.get('ctype') == 'IMAGE' and x.get('is_image_download', False), chat_list)))
        image_org_data = get_image_group_chat_data(group_name, chat_list, 20)  # 获取图片上下文
        
        logging.info(f'user_chat_list_len:{len(chat_list)}, has_image_num:{has_image_num}, image_org_data:\t{len(image_org_data)}\n')
        for image_path, image_context in image_org_data.items():
            prompt_str = get_image_chats_prompt(image_context, 'forward', group_name)
            logging.info(f'image prompt_str:\n{prompt_str}\n')
            
            # 调用多模态模型处理图片
            result = dify_model.request_dify(prompt_str, input_file=image_path)
            if result:
                image_qa = {
                    'image_path': image_path,
                    'image_understanding_knowledge': result,
                    'from_file_name': group_name,
                    'from_user': user,
                    'group_name': group_name,
                    'platform': platform if platform != 'mix' else 'unknown'
                }
                result_qa_list.append(image_qa)
                
    return result_qa_list


def process_normal_group_data(group_name, platform, group_chat_list, group_white_list, dify_model):
    """
    处理普通群的数据
    """
    result_qa_list = []
    
    # 处理图片数据
    image_org_data = get_image_group_chat_data(group_name, group_chat_list, 3)  # 获取图片上下文
    for image_path, image_context in image_org_data.items():
        prompt_str = get_image_chats_prompt(image_context, 'normal', group_name, group_white_list)
        logging.info(f'image prompt_str:\n{prompt_str}\n')
        
        # 调用多模态模型处理图片
        result = dify_model.request_dify(prompt_str, input_file=image_path)
        if result:
            image_qa = {
                'image_path': image_path,
                'image_understanding_knowledge': result,
                'from_file_name': group_name,
                'group_name': group_name,
                'platform': platform if platform != 'mix' else 'unknown'
            }
            result_qa_list.append(image_qa)
            
    return result_qa_list


def process_one_group_data(group_name, group_chat_list, group_type, 
                           group_white_list, platform, forward_dify_model, norm_dify_model):
    """
    处理单个群的数据
    """
    if group_type == 'forward':
        return process_forward_group_data(group_name, platform, group_chat_list, group_white_list,  forward_dify_model)
    elif group_type == 'normal':
        return process_normal_group_data(group_name, platform, group_chat_list, group_white_list, norm_dify_model)

    else:
        raise ValueError(f"群类型错误: {group_type}")


def process_one_robot_group_data(robot_name, data_file, 
                                robot_room_type_config, robot_room_process_record, 
                                robot_white_list_dict, need_robot_reply=False):
    """
    处理单个机器人的数据
    """
    logging.info(f'process robot_name:{robot_name} data_file:{data_file}')
    reorga_chat_dict = load_and_reorg_one_robot_data(robot_name, data_file, robot_room_type_config.get(robot_name, {}), 
                                                     robot_room_process_record, need_robot_reply)
    
    logging.info(f'robot_name:{robot_name} reorga_chat_dict:\n{reorga_chat_dict}\n')
    
    # 使用多模态模型替换原来的模型
    forward_dify_model_nomix = dify_tools.DIfyWorkFlowMlutiVisionRequest(api_base=config['dify_api_base'], 
                                                             api_key=config['dify_api_key_mluti_vision_forward_nomix'])
    forward_dify_model_mix = dify_tools.DIfyWorkFlowMlutiVisionRequest(api_base=config['dify_api_base'], 
                                                           api_key=config['dify_api_key_mluti_vision_forward_mix'])
    norm_dify_model_nomix = dify_tools.DIfyWorkFlowMlutiVisionRequest(api_base=config['dify_api_base'], 
                                                          api_key=config['dify_api_key_mluti_vision_normal_nomix'])
    norm_dify_model_mix = dify_tools.DIfyWorkFlowMlutiVisionRequest(api_base=config['dify_api_base'], 
                                                        api_key=config['dify_api_key_mluti_vision_normal_mix'])
    
    all_qa_list = []
    group_type_config = robot_room_type_config.get(robot_name, {})
    logging.info(f'group_type_config:\n{group_type_config}\n')
    logging.info(f'reorga_chat_dict:\n{len(reorga_chat_dict)}\n')
    for group_name, group_chat_list in reorga_chat_dict.items():
        if group_name in group_type_config:
            group_type = group_type_config[group_name].get('type', 'unknown')
            platform = group_type_config[group_name].get('platform', 'unknown')
        elif 'all' in group_type_config:
            # 命中黑名单
            logging.info('group_name[%s], black_name_set[%s], is_hit[%s]', group_name, group_type_config['all'].get('black_group', set()), group_name in group_type_config['all'].get('black_group', set()))
            if group_name in group_type_config['all'].get('black_group', set()):
                continue
            group_type = group_type_config['all'].get('type', 'unknown')
            platform = group_type_config['all'].get('platform', 'unknown')
        else:
            logging.info(f'group_name[{group_name}] not in group_type_config and not has all')
            continue
        logging.info(f'group_name:{group_name} group_type:{group_type} platform:{platform}, chatlist_len:{len(group_chat_list)}')
        white_list = robot_white_list_dict.get(robot_name, {}).get(group_name, [])
        if platform == 'mix':
            norm_dify_model = norm_dify_model_mix
            forward_dify_model = forward_dify_model_mix
        else:
            norm_dify_model = norm_dify_model_nomix
            forward_dify_model = forward_dify_model_nomix
        qa_list = process_one_group_data(group_name, group_chat_list, group_type, 
                                        white_list, platform, 
                                        forward_dify_model, norm_dify_model)
        all_qa_list.extend(qa_list)
        max_process_time = list(sorted(group_chat_list, key=lambda x: x['message_time']))[-1]['message_time']
        robot_room_process_record.setdefault(robot_name, {})
        robot_room_process_record[robot_name][group_name] = max_process_time
    return all_qa_list


def run_batch_robot_chat_data(data_file, output_dir, 
                              robot_room_type_config_file, robot_process_record_file, 
                              robot_white_list_file, need_robot_reply=False, data_file_field_num=2, filter_group_name='all', flag=''):
    """
    批量处理机器人的数据
    """
    robot_room_type_config = load_robot_room_type(robot_room_type_config_file, filter_group_name)
    
    if os.path.exists(robot_process_record_file):
        robot_process_record = load_3file_dict(robot_process_record_file)
    else:
        robot_process_record = dict()
    robot_white_list_dict = load_white_list_dict(robot_white_list_file)
    logging.info(f'robot_whit:\n{robot_white_list_dict}\n')
    with open(data_file, encoding='utf8') as f:
        for line in f:
            line = line.strip('\n')
            if not line:
                continue
            fields = line.split('\t')
            robot_name = fields[0]
            platform = fields[1]
            data_file = fields[data_file_field_num]
            logging.info(f'robot_name:{robot_name} platform:{platform} data_file:{data_file}')
            qa_list = process_one_robot_group_data(robot_name, data_file, robot_room_type_config, robot_process_record, 
            robot_white_list_dict, need_robot_reply)
            qa_save_file = f"{output_dir}/{robot_name}_{platform}_json_{flag}.txt"
            with open(qa_save_file, 'w', encoding='utf8') as f:
                for qa_info in qa_list:
                    f.write(json.dumps(qa_info, ensure_ascii=False) + '\n')
            print(f'{line}\t{qa_save_file}')
    save_3file_dict(robot_process_record_file, robot_process_record)


if __name__ == '__main__':
    logging.basicConfig(
        stream=sys.stderr,
        level=logging.INFO,
        format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
    )
    import fire
    fire.Fire({
        'run_batch_robot_chat_data': run_batch_robot_chat_data,
    })
