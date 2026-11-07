#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2021 263436967@qq.com, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-11-13
description: qa类知识文本解析工具
"""

import re
import logging

def extract_tags(answer):
    """
    从答案中提取标签。
    
    :param answer: 包含标签的答案文本
    :return: 标签列表和不包含标签的答案
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

def parse_qa_answer(answer, extra_info_dict=None, sep='###'):
    """
    解析Dify模型返回的答案，提取问答对。
    支持以下格式：
    1. 问题:...答案:...
    2. Q:...A:... (大小写不敏感)
    
    :param answer: Dify模型返回的答案文本
    :param extra_info_dict: 额外信息字典，会合并到每个问答对中
    :param sep: 问答对之间的分隔符，默认为'###'
    :return: 解析后的问答对列表
    """
    json_list = []
    answer = answer.replace('：', ':')
    qa_pairs = answer.split(sep) if sep in answer else [answer]
    for qa_pair in qa_pairs:
        qa_pair = qa_pair.strip()
        if not qa_pair:
            continue
        
        # 尝试匹配 问题:...答案:... 格式
        matches = re.findall(r'问题:(.*?)答案:(.*?)(?=问题:|$)', qa_pair, re.DOTALL)
        if matches:
            for q, a in matches:
                souce =  re.search(r'\n来源:\s*\[(.*?)\]', a, re.DOTALL)
                a = re.sub(r'\n来源:\s*\[(.*?)\]', '', a)
                a = re.sub(r'\[(.*?)\]', '', a)
                if souce:
                    souce = souce.group(1)
                else:
                    souce = ''
                
                qa_info = {
                    'q': q.strip(),
                    'a': a.strip(),
                    'source': souce
                }
                if extra_info_dict:
                    qa_info.update(extra_info_dict)
                qa_info['source'] = souce
                json_list.append(qa_info)
        else:
            # 尝试匹配 Q:/q: 和 A:/a: 模式（大小写不敏感）
            qa_matches = re.findall(r'\bq\s*:\s*(.*?)\ba\s*:\s*(.*?)(?=\bq\s*:|$)', qa_pair, re.DOTALL | re.IGNORECASE)
            if qa_matches:
                for q, a in qa_matches:
                    # 提取来源信息（如果有）
                    souce = re.search(r'\n来源:\s*\[(.*?)\]', a, re.DOTALL)
                    a = re.sub(r'\n来源:\s*\[(.*?)\]', '', a)
                    if souce:
                        souce = souce.group(1)
                    else:
                        souce = ''
                    
                    qa_info = {
                        'q': q.strip(),
                        'a': a.strip(),
                        'source': souce
                    }
                    if extra_info_dict:
                        qa_info.update(extra_info_dict)
                    qa_info['source'] = souce
                    json_list.append(qa_info)
            else:
                # 如果没有找到匹配的问答对，记录日志
                logging.warning(f"无法解析问答对: {qa_pair}")
    return json_list


def parse_qa_with_attrs(answer, extra_info_dict=None, sep='###', attrs_sep='#属性:'):
    """
    解析Dify模型返回的答案，提取问答对。
    """
    answer = answer.replace('：', ':')
    qa_list = parse_qa_answer(answer, extra_info_dict, sep)
    for qa_info in qa_list:
        a = qa_info['a']
        split_text = a.split(attrs_sep)
        attr_dict = dict()
        if len(split_text) > 1:
            a = split_text[0]
            attr_str = split_text[1]
            attrs = attr_str.split(',')
            for attr_v in attrs:
                attr_kv = attr_v.split(':')
                if len(attr_kv) == 2:
                    attr_dict[attr_kv[0]] = attr_kv[1]
        qa_info['attrs'] = attr_dict
    return qa_list



def parse_qa_quality_result(quality_result):
    """
    解析质量评估结果。
    
    :param quality_result: Dify质量评估模型的返回文本
    :return: 解析后的质量信息字典
    """
    quality_info = {}
    quality_result = quality_result.replace('：', ':')
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
            logging.info(f'问题: {question}\torianswer:{answer}, 索引: {index}\t答案: {answer_without_tags}\t标签: {tags}\t重复索引: {duplicate_index}')
            
            quality_info[index] = {
                'question': question,
                'answer': answer_without_tags,
                'tags': tags,
                'duplicate_index': duplicate_index
            }
            
            logging.info(f'索引: {index}\t问题: {question}\t答案: {answer_without_tags}\t标签: {tags}\t重复索引: {duplicate_index}')
            index += 1
    
    return quality_info



