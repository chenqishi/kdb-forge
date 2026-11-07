#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-19
"""
from kdb.shared.config.private_values import private_value as _private_value
import json
import os
import re
import logging
import requests
import sys
import traceback
import time
import copy
#from knowledge_clear_tool.tools import schema_trans
#from quality_tools.qa_quality_tools import deduplicate_qa_list
from commons import common_utils
from config_tools.config import GLOBAL_CONFIG

class KnowledgeCleaner:
    def __init__(self, api_base=None, api_key=None, max_retries=3):
        self.api_base = api_base
        self.api_key = api_key
        self.max_retries = max_retries

    def request_dify(self, paragraph):
        headers = {
            'Authorization': f"Bearer {self.api_key}",
            'Content-Type': 'application/json'
        }
        
        payload = {
            'inputs': {
                'paragraph': paragraph
            },
            "response_mode": "blocking",
            "user": "test"
        }
        
        for attempt in range(self.max_retries):
            try:
                logging.info(f"正在调用Dify API，请求内容: {payload}")
                response = requests.post(f"{self.api_base}/workflows/run", headers=headers, json=payload, timeout=600)
                
                if response.status_code != 200:
                    logging.error(f"API返回非200状态码: {response.status_code}")
                    logging.error(f"响应内容: {response.text}")
                    continue
                
                result = response.json()
                if result['data']['status'] == 'failed':
                    logging.error(f"Dify请求失败: {result['data']['error']} api_key: {self.api_key}")
                    if attempt < self.max_retries - 1:
                        logging.info(f"正在进行第{attempt + 2}次重试...")
                        time.sleep(5)  # 在重试之前等待5秒
                        continue
                    else:
                        return None
                
                return result['data']['outputs']['Final']
            except KeyError as e:
                logging.error(f"响应中缺少字段: {str(e)}")
                logging.error(f"完整响应内容: {response.text}")
            except requests.exceptions.Timeout:
                logging.error("请求超时（10分钟）")
            except requests.exceptions.RequestException as e:
                logging.error(f"请求异常: {str(e)}")
                logging.error(f"请求URL: {self.api_base}/workflows/run")
                logging.error(f"请求头: {headers}")
                logging.error(f"请求体: {payload}")
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('tb[%s]', tb)
                logging.error(f"调用Dify API时发生错误: {str(e)}")
            
            if attempt < self.max_retries - 1:
                logging.info(f"正在进行第{attempt + 2}次重试...")
                time.sleep(5)  # 在重试之前等待5秒
            else:
                logging.error("已达到最大重试次数,请求失败")
        
        return None

def save_all_document_content(pdf_json_file, output_file):
    """
    保存整个文档的内容到输出文件。
    
    :param pdf_json_file: 包含PDF内容的JSON文件路径
    :param output_file: 保存整个文档内容的输出文件路径
    """
    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = merge_segment_content(data_json, {'pages': [1, len(data_json)]}, need_add_page_num=True)
    
    with open(output_file, 'w', encoding='utf-8') as out_f:
        out_f.write(document_content)

def clear_pdf_json_content(pdf_json_file, output_file, dify_segment, dify_subtract, from_file_name):
    """
    处理PDF JSON文件，提取问答对并保存结果。
    
    :param pdf_json_file: 输入的PDF JSON文件路径
    :param output_file: 输出文件路径
    :param dify_segment: 用于分段的Dify模型实例
    :param dify_subtract: 用于提取QA的Dify模型实例
    :param from_file_name: 源文件名
    :return: 提取的问答对列表
    """
    data_json = json.load(open(pdf_json_file, 'r', encoding='utf-8'))
    document_content = merge_segment_content(data_json, {'pages': [1, len(data_json)]}, need_add_page_num=False)
    json_list = []
    
    if len(document_content) < 2000:
        answer = dify_subtract.request_dify(document_content)
        logging.info(f"段落内容: {document_content}\t答案: {answer}")
        json_list.extend(parse_answer(answer, from_file_name, [1, len(data_json)]))
    else:
        logging.info(f'段落内容长度大于2000字符，进行段落分割')
        for_seg_document_content = merge_segment_content(data_json, {'pages': [1, len(data_json)]}, need_add_page_num=True)
        segment_answer = dify_segment.request_dify(for_seg_document_content)
        segments = parse_dify_segment(segment_answer)
        logging.info(f'ori_segment_answer: {segment_answer},parse_dify_segment: {segments}')
        logging.info(f'段落切分原始结果:{segment_answer}\t切分结果: {segments}')
        for segment in segments:
            segment_content = merge_segment_content(data_json, segment, need_add_page_num=False)
            answer = dify_subtract.request_dify(segment_content)
            parse_result = parse_answer(answer, from_file_name, segment['pages'])
            logging.info(f"段落内容: {segment_content}\t段落长度: {len(segment_content)}\t答案: {answer}\t解析结果: {parse_result}")
            json_list.extend(parse_result)

    with open(output_file, 'w', encoding='utf-8') as out_f:
        json.dump(json_list, out_f, ensure_ascii=False, indent=4)
    return json_list

def merge_segment_content(data_json, segment, need_add_page_num=False):
    """
    合并指定页面范围内的文本内容。
    
    :param data_json: 包含所有页面内容的JSON数据
    :param segment: 包含页面范围的字典
    :param need_add_page_num: 是否需要添加页码信息
    :return: 合并后的文本内容
    """
    start_page, end_page = segment['pages']
    segment_content = ''
    
    for page_num in range(start_page, end_page + 1):
        page_values = data_json.get(str(page_num), [])
        one_page_content = ''
        for one_value in page_values:
            if one_value.get('type') == 'text':
                one_segment_content = one_value.get('text_content', '')
                one_page_content = one_page_content + '\n' + one_segment_content if one_page_content else one_segment_content
        
        if one_page_content:
            if need_add_page_num:
                one_page_content = f'第{page_num}页内容如下:\n{one_page_content}'
            segment_content = segment_content + '\n' + one_page_content if segment_content else one_page_content
    
    return segment_content

def parse_answer(answer, from_file_name, pages):
    """
    解析Dify模型返回的答案，提取问答对。
    
    :param answer: Dify模型返回的答案文本
    :param from_file_name: 源文件名
    :param pages: 问答对所在的页面范围
    :return: 解析后的问答对列表
    """
    json_list = []
    qa_pairs = answer.split('###') if '###' in answer else [answer]
    for qa_pair in qa_pairs:
        qa_pair = qa_pair.strip()
        if not qa_pair:
            continue
        matches = re.findall(r'问题:(.*?)答案:(.*?)(?=问题:|$)', qa_pair, re.DOTALL)
        if matches:
            for q, a in matches:
                json_list.append({
                    'q': q.strip(),
                    'a': a.strip(),
                    'from_file_name': from_file_name,
                    'from_page': pages
                })
        else:
            # 如果没有找到匹配的问答对，记录日志
            logging.warning(f"无法解析问答对: {qa_pair}")
    return json_list

def run_batch_clear_pdf_json_content(pdf_json_batch_file, flag='', from_file_name_field_num=0):
    """
    批量处理PDF JSON文件，取问答对并添加质量信息。
    
    :param pdf_json_batch_file: 包含多个PDF JSON文件路径的批处理文件
    :param flag: 用于生成输出文件名的标志
    """
    api_base = GLOBAL_CONFIG['dify_api_base']
    dify_segment = KnowledgeCleaner(api_base=api_base, api_key=_private_value('f977bc3666b179d2eb50e78e'), max_retries=3)

    #dify_subtract = KnowledgeCleaner(api_base=api_base, api_key='[PRIVATE_CREDENTIAL_REDACTED]', max_retries=3)
    dify_subtract = KnowledgeCleaner(api_base=api_base, api_key=_private_value('7d35ec476b1bc4c5629d083d'), max_retries=3)
    dify_qa_filter = KnowledgeCleaner(api_base=api_base, api_key=_private_value('8a387fb43f3e0dc7311303f0'), max_retries=3)

    
    with open(pdf_json_batch_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            fields = line.split('\t')
            pdf_json_file = fields[-1]
            logging.info(f'开始处理文件: {pdf_json_file}')
            
            # 使用 flag 参数来生成输出文件名
            if flag:
                file_path = pdf_json_file.replace('.json', f'_qa_{flag}.txt')
                add_quality_file = pdf_json_file.replace('.json', f'_qa_add_quality_{flag}.txt')
            else:
                file_path = pdf_json_file.replace('.json', '_qa.txt')
                add_quality_file = pdf_json_file.replace('.json', '_qa_add_quality.txt')
            output_file = file_path
            from_file_name = fields[from_file_name_field_num]
            
            # 保存整个文档内容
            all_content_file = pdf_json_file.replace('.json', '_all_content.txt')
            save_all_document_content(pdf_json_file, all_content_file)
            
            qa_extract_json_list = clear_pdf_json_content(pdf_json_file, output_file, dify_segment, dify_subtract, from_file_name)
            
            # 添加质量信息并分类
            quality_result = add_quality_info_to_qa_json(copy.deepcopy(qa_extract_json_list), dify_qa_filter)
            
            # 将更新后的qa列表写回文件
            with open(add_quality_file, 'w', encoding='utf-8') as out_f:
                json.dump(quality_result, out_f, ensure_ascii=False, indent=4)
            
            fields.append(file_path)
            fields.append(all_content_file)
            fields.append(add_quality_file)
            print('\t'.join(fields))

def parse_dify_segment(segment_answer):
    """
    解析Dify分段模型的返回结果。
    
    :param segment_answer: Dify分段模型的返回文本
    :return: 解析后的段落信息列表
    """
    segments = []
    # 使用正则表达式匹配段落信息
    pattern = re.compile(r'(.+?)\s+第(\d+)页\s+第(\d+)页')
    for match in pattern.finditer(segment_answer):
        title = match.group(1).strip()
        start_page = int(match.group(2))
        end_page = int(match.group(3))
        segments.append({
            'title': title,
            'pages': [start_page, end_page]
        })
    return segments

def parse_quality_result(quality_result):
    """
    解析质量评估结果。
    
    :param quality_result: Dify质量评估模型的返回文本
    :return: 解析后的质量信息字典
    """
    quality_info = {}
    qa_pairs = quality_result.split('###') if '###' in quality_result else [quality_result]
    index = 1 
    for qa_pair in qa_pairs:
        qa_pair = qa_pair.strip()
        if not qa_pair:
            continue
        
        matches = re.findall(r'问题:(.*?)答案:(.*?)(?=问题:|$)', qa_pair, re.DOTALL)
        for match in matches:
            question, answer = match
            question = question.strip()
            answer = answer.strip()
            
            # 从答案中提取标签
            tags, answer_without_tags = extract_tags(answer)
            duplicate_index = find_duplicate_index(tags)
            logging.info(f'问题: {question}\torianswer:{answer}, 索引: {index}\t答���: {answer_without_tags}\t标签: {tags}\t重复索引: {duplicate_index}')
            
            quality_info[index] = {
                'question': question,
                'answer': answer_without_tags,
                'tags': tags,
                'duplicate_index': duplicate_index
            }
            
            logging.info(f'索引: {index}\t问题: {question}\t答案: {answer_without_tags}\t标签: {tags}\t重复索引: {duplicate_index}')
            index += 1
    
    return quality_info

def extract_tags(answer):
    """
    从答案中提取标签。
    
    :param answer: 包含标签的��案文本
    :return: ��签列表和不包含标签的答案
    """
    tags = []
    answer_without_tags = answer
    
    # 查找答案末尾的标签
    tag_match = re.search(r'(#[^#\s]+)+$', answer)
    if tag_match:
        tag_string = tag_match.group()
        tags = tag_string.split('#')[1:]  # 去掉空字符串
        answer_without_tags = answer[:tag_match.start()].strip()
    
    return tags, answer_without_tags

def find_duplicate_index(tags):
    """
    在标签中查找重复索引。
    
    :param tags: 标签列表
    :return: 重复索引,如果没有找到则返回None
    """
    for tag in tags:
        if tag.startswith('重复-'):
            try:
                return int(tag.split('-')[1])
            except ValueError:
                logging.warning(f"无效的重复标签格式: {tag}")
    return None

def add_quality_info_to_qa_json(qa_json_list, dify_qa_filter):
    """
    为问答对添加质量信息，统计每组的QA数量，并将其分为高质量和中等质量两类。
    
    :param qa_json_list: 原始问答对列表
    :param dify_qa_filter: 用于质量评估的Dify模型实例
    :return: 包含高质量和中等质量问答对的字典
    """
    dedup_qa_info_list = deduplicate_qa_list(qa_json_list)
    logging.info(f'before dedup_len {len(qa_json_list)} afterlen {len(dedup_qa_info_list)} deduplicate_qa_list: {dedup_qa_info_list}')
    qa_json_list = dedup_qa_info_list
    qa_text = schema_trans.qajson_to_line_text(qa_json_list, add_index=True)
    
    quality_result = dify_qa_filter.request_dify(qa_text)
    
    if quality_result is None:
        logging.error("无法获取质量评估结果")
        return {'high': [], 'mid': qa_json_list}
    
    quality_info = parse_quality_result(quality_result)
    logging.info(f'ori_quality_result: {quality_result}, parse_quality_result: {quality_info}')
    
    group_counter = 0
    group_mapping = {}
    group_qa_count = {}
    
    # 第一次遍历：分配组号和统计每组的QA数量
    for i, qa_item in enumerate(qa_json_list):
        if i + 1 in quality_info:
            qa_info = quality_info[i + 1]
            qa_content1 = qa_item['q'] + '\n' + qa_item['a']
            qa_content2 = qa_info['question'] + '\n' + qa_info['answer']
            if common_utils.context_dice(qa_content1, qa_content2) < 0.9:
                logging.info('index %s not simility, not match skip, content1: %s, content2: %s', i + 1, qa_content1, qa_content2)
                continue
            qa_item['quality_info'] = qa_info['tags']
            qa_item['duplicate_index'] = qa_info['duplicate_index'] or (i + 1)
            if qa_item['duplicate_index'] == i + 1:
                group_counter += 1
                group_mapping[i + 1] = group_counter
                qa_item['group'] = group_counter
                group_qa_count[group_counter] = 1
            else:
                qa_item['group'] = group_mapping.get(qa_item['duplicate_index'], group_counter)
                group_qa_count[qa_item['group']] = group_qa_count.get(qa_item['group'], 0) + 1
        else:
            qa_item['quality_info'] = []
            qa_item['duplicate_index'] = i + 1
            group_counter += 1
            qa_item['group'] = group_counter
            group_qa_count[group_counter] = 1
    
    # 第二次遍历：添加每组的QA数量到每个QA项
    for qa_item in qa_json_list:
        qa_item['group_qa_count'] = group_qa_count[qa_item['group']]
    
    high_quality_qa_list = []
    mid_quality_qa_list = []
    
    for qa_item in qa_json_list:
        if '优质' in qa_item['quality_info'] and qa_item['group_qa_count'] == 1:
            high_quality_qa_list.append(qa_item)
        else:
            mid_quality_qa_list.append(qa_item)
    
    high_quality_qa_list.sort(key=lambda x: x['group'])
    mid_quality_qa_list.sort(key=lambda x: x['group'])
    
    return {'high': high_quality_qa_list, 'mid': mid_quality_qa_list}


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    import fire
    fire.Fire({
        'run_batch_clear_pdf_json_content': run_batch_clear_pdf_json_content,
    })

