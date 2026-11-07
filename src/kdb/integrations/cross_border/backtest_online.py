#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-15
description: 离线批量回测,注意若线上策略修正，则要一块修正
"""
import sys
import os
import json
import logging
import traceback
import csv
import pandas as pd
from commons.dify_tools import DifyChatFlowRequest
from commons.dify_tools import DifyWorkFlowRequest
from commons.common_utils import is_contain_value
from cross_broder_access.data_control import get_chat_history_from_sql_iterator, ChatContextControl


class DifyModel(object):
    def __init__(self, api_base, api_key):
        self.api_base = api_base
        self.api_key = api_key
        self.remote_conversation_ids = {}
        self.dify_client = DifyChatFlowRequest(api_base=api_base, api_key=api_key)

    def query(self, conversation_id, query, **kwargs):
        remote_id = self.remote_conversation_ids.get(conversation_id, '')
        
        response = self.dify_client.request_dify(query, remote_id)
        
        if response and isinstance(response, dict):
            if 'conversation_id' in response:
                self.remote_conversation_ids[conversation_id] = response['conversation_id']
            return response.get('answer', '')
        elif isinstance(response, str):
            return response
        else:
            logging.error(f"query: {query} 无法获取有效响应")
            return "无法获取有效响应"

def get_session_id(data):
    if getattr(data, 'session_id', None):
        return data.session_id
    else:
        if data.is_group:
            session_id = str(data.group_id) + str(data.actual_user_id)
            return session_id
        else:
            session_id = str(data.other_user_id) + str(data.to_user_id)
            return session_id

def build_is_need_reply_prompt(chat_history, query):
    """构建提示词"""
    prompt = ""
    for msg in chat_history:
        role = "robot" if msg["mess_type"] == "assistant" else msg["sender_name"]
        role = role if role else "unknow"
        prompt += f"{role}: {msg['content']}\n"

    prompt += "\n指定语句:\n"
    prompt += query
    return prompt

def get_background(chat_history, msg, front_num=10):
    if not chat_history:
        return []
    end_index = len(chat_history)
    start_index = 0
    for index in range(len(chat_history) - 1, -1, -1):
        if hasattr(chat_history[index], 'msgid') and chat_history[index].msgid == msg.msg_id:
            start_index = max(0, index - front_num)
            end_index = index + 1
            break
    background = chat_history[start_index: end_index]
    return [row._asdict() for row in background]
def backtest_one_sql_data(data_dict, robot_id, context_info, other_inputs, reply_dify_model, is_need_reply_dify_model, search_qa_dify_model):
    """
    单条数据回测，返回(reply_content, is_need_reply_content, qa_content)
    :param data_dict: namedtuple，单条sql数据
    :param context_info: 该session的历史上下文（namedtuple list）
    :param reply_dify_model: chat类型模型
    :param is_need_reply_dify_model: workflow类型模型
    :param search_qa_dify_model: workflow类型模型
    :return: (reply_content, is_need_reply_content, qa_content)
    """
    # 1. reply_content
    def _get_inputs(data):
        inputs = {}
        inputs['robot_name'] = getattr(data, 'user', 'default')
        inputs['robot_id'] = robot_id
        inputs['ic_name'] = getattr(data, 'other_user_nickname', 'default')
        inputs['ic_id'] = getattr(data, 'other_user_id', 'default')
        inputs['session_id'] = get_session_id(data)
        is_group = getattr(data, 'is_group', 0)
        inputs['is_group'] = bool(is_group)
        if not is_group:
            inputs['customer_name'] = getattr(data, 'other_user_nickname', 'default')
            inputs['customer_id'] = getattr(data, 'other_user_id', 'default')
        else:
            inputs['customer_name'] = getattr(data, 'actual_user_nickname', 'default')
            inputs['customer_id'] = getattr(data, 'actual_user_id', 'default')
        inputs.update(other_inputs)
        return inputs
    req_params = dict()
    query = getattr(data_dict, 'send_content', '') or getattr(data_dict, 'content', '')
    reply_inputs = _get_inputs(data_dict)
    req_params['reply_params'] = {
        'query': query,
        'inputs': reply_inputs
    }
    logging.info(f"reply_request params inputs: {reply_inputs} query: {query}")
    try:
        reply_content = reply_dify_model.request_dify(query, inputs=reply_inputs)
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"reply_dify_model error: {e}\n{tb}")
        reply_content = f"reply_dify_model error: {e}"

    # 2. is_need_reply_content


    background = get_background(context_info, data_dict, front_num=2)
    is_need_reply_prompt = build_is_need_reply_prompt(background, query)
    req_params['is_need_reply_params'] = {
        'paragraph': is_need_reply_prompt
    }
    try:
        is_need_reply_content = is_need_reply_dify_model.request_dify(is_need_reply_prompt)
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"is_need_reply_dify_model error: {e}\n{tb}")
        is_need_reply_content = f"is_need_reply_dify_model error: {e}"

    # 3. qa_content
    req_params['qa_params'] = {
        'query': query
    }
    try:
        qa_content = search_qa_dify_model.request_dify(query)
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"search_qa_dify_model error: {e}\n{tb}")
        qa_content = f"search_qa_dify_model error: {e}"

    return reply_content, is_need_reply_content, qa_content, req_params

def get_robot_id(msg_id, context_info):
    for item in context_info:
        if item.msgid == msg_id:
            return getattr(item, 'robot_id', None)
    return None


def batch_backtest_sql(sql_config_path, dify_model_config_path, 
                       customer=None, user=None, limit_num=None, output_prefix=None):
    """
    离线批量回测
    :param sql_config_path: 数据库配置文件路径
    :param dify_model_config_path: dify模型配置文件路径（json，包含所有模型配置） 以及其他运行配置
    :param customer: 客户名
    :param user: 用户名
    :param limit_num: 限制回测数据条数
    :param output_prefix: 输出文件前缀
    """


    # 1. 读取模型配置并初始化模型
    with open(dify_model_config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    # 假设json结构如下（如有不同请补充）：
    # {
    #   "reply_dify_model": {"base_url": "...", "api_key": "..."},
    #   "is_need_reply_dify_model": {"base_url": "...", "api_key": "..."},
    #   "search_qa_dify_model": {"base_url": "...", "api_key": "..."}
    # }
    base_url = config['base_url']
    reply_dify_model = DifyChatFlowRequest(
        api_base=base_url,
        api_key=config['reply_dify_model_api_key']
    )
    is_need_reply_dify_model = DifyWorkFlowRequest(
        api_base=base_url,
        api_key=config['is_need_reply_dify_model_api_key']
    )
    search_qa_dify_model = DifyWorkFlowRequest(
        api_base=base_url,
        api_key=config['search_qa_dify_model_api_key']
    )
    other_inputs = {}
    other_inputs['send_url'] = config['send_url']
    other_inputs['base_url'] = config['base_url']
    other_inputs['wId'] = config['wId']
    other_inputs['wkteam_auth'] = config['wkteam_auth']
    other_inputs['chatwork_auth'] = config.get('chatwork_auth', '') # 仅当chatwork时才有
    if not customer:
        customer = config['customer']
    if not user:
        user = config['user']
    if not limit_num:
        limit_num = config.get('limit_num', 10000)
    if not output_prefix:
        output_prefix = config.get('output_prefix', 'batch_test_result')
    black_word_list = config.get('black_word_list', [])

    logging.info(f"customer: {customer} user: {user} limit_num: {limit_num} output_prefix: {output_prefix}")
    #
    # 2. 获取待测试的所有数据
    data_iter = get_chat_history_from_sql_iterator(sql_config_path, customer, user=user, limit_num=limit_num)
    data_list = list(data_iter)
    if not data_list:
        logging.error("无数据")
        return

    # 3. 获取context控制器
    context_control = ChatContextControl(sql_config_path, catche_num=50)    
    result_rows = []
    # 4. 逐条处理
    for index, data in enumerate(data_list):
        # 获取context
        other_user_name = str(getattr(data, 'other_user_nickname', ''))
        if is_contain_value(other_user_name, black_word_list):
            logging.info(f"other_user_name: {other_user_name} 在黑名单中，跳过")
            continue
        logging.info(f"process {index} data:  {data}")
        msg_id = getattr(data, 'msg_id', '')
        context_session_id = data.group_id if data.is_group else get_session_id(data)
        context_info = context_control.get_session_context(context_session_id)
        logging.info(f"context_info: {context_info}")
        robot_id = get_robot_id(msg_id, context_info)
        backgroud_chat = get_background(context_info, data, front_num=100)
        backgroud_chat_str = [f'{row["sender_name"]}: {row["content"]}' for row in backgroud_chat]
        backgroud_chat_str = '\n'.join(backgroud_chat_str)
    
        logging.info(f"msgid: {msg_id} \tcontext_info: {context_info} \t robot_id: {robot_id}")
        # 调用backtest_one_sql_data
        if data.hot_assistant_result and data.hot_assistant_result.find('no_for_bymerge') == -1:
            reply_content, is_need_reply_content, qa_content, req_params = backtest_one_sql_data(
                data, robot_id, context_info, other_inputs, reply_dify_model, is_need_reply_dify_model, search_qa_dify_model
            )
        else:
            reply_content = ''
            is_need_reply_content = ''
            qa_content = ''
            req_params = {}
        # 合并原始数据和新三列
        req_params = json.dumps(req_params, ensure_ascii=False)
        row = list(data) + [reply_content, is_need_reply_content, qa_content, backgroud_chat_str, req_params]
        result_rows.append(row)

    # 5. 输出为TSV和Excel
    field_names = list(data_list[0]._fields) + ['reply_content', 'is_need_reply_content', 'qa_content', 'backgroud_chat_str', 'all_req_params']
    tsv_file = f"{output_prefix}.tsv"
    excel_file = f"{output_prefix}.xlsx"

    with open(tsv_file, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f, delimiter='\t')
        writer.writerow(field_names)
        writer.writerows(result_rows)
    print(f"TSV文件已保存: {tsv_file}")

    df = pd.DataFrame(result_rows, columns=field_names)
    df.to_excel(excel_file, index=False)
    print(f"Excel文件已保存: {excel_file}")

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
