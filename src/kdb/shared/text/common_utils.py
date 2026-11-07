#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2021 263436967@qq.com, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2022-05-19
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


PURCHASE_FILTER_LIST = ['', ' ', '其他', '其它', '无', '、', ';']

def count_chinese_char(content):
    """
    统计中文个数
    """
    count = 0
    for c in content:
        if is_chinese_char(c):
            count += 1
    return count

def count_alaph_char(content):
    """
    统计英文文个数
    """
    count = 0
    for c in content:
        if is_alapha_char(c):
            count += 1
    return count

def is_chinese_char(char):
    """
    判断是否中文字符
    """
    if not '\u4e00' <= char <= '\u9fa5':
        return False
    return True



def is_alapha_char(char):
    """
    判断是否字母
    """
    if 'A' <= char <= 'z':
        return True
    return False

def filter_chinese(content, filter_chinese=True):
    """
    过滤中文
    """
    filter_content = ''
    for char in content:
        if is_chinese_char(char) == filter_chinese:
            filter_content += char
    return filter_content


def load_set(data_file, f_num=0, sep='\t'):
    """
    load set
    """
    data_set = set()
    with open(data_file, encoding='utf8') as df:
        for line in df:
            line = line.strip()
            fields = line.split(sep)
            data_set.add(fields[f_num])
    return data_set
   

def load_map_dict(data_file, k_field, value_field, sep='\t', dtype=None):
    """
    """
    map_dict = dict()
    with open(data_file, encoding='utf8') as df:
        for line in df:
            line = line.strip('\n')
            fields = line.split(sep)
            k = fields[k_field]
            v = fields[value_field]
            if dtype == 'json':
                try:
                    v = json.loads(v)
                except:
                    logging.error('error load v[%s]', v)
                    v = None
            map_dict[k] = v
    return map_dict


def get_loop_map(map_dict, map_key, key_field=None, max_num=100):
    """
    循环获取映射值
    """
    new_map_key = map_key
    loop_num = 0
    #logging.info('common map_dict[%s]', map_dict)
    while new_map_key is not None and loop_num < max_num:
        map_info = map_dict.get(new_map_key)
        #logging.info('get_map[%s], map_info[%s]', new_map_key, map_info)
        if map_info is None:
            return new_map_key
        else:
            map_key = new_map_key
            if key_field is not None:
                new_map_key = map_info[key_field]
            else:
                new_map_key = map_info
        loop_num += 1
    logging.info('loop_num[%s]', loop_num)
    return map_key
    
def re_split(content, split_char):
    """
    利用正则表达式进行切分
    """
    content_split = re.split(split_char, content)
    return content_split


def is_contain_value(content, seg_list):
    """
    判断是否包含seg_list中的元素
    """
    for seg in seg_list:
        if str(seg) in content:
            #print('hit seg', content, seg)
            return True
    return False

def dice_score(set1, set2):
    """
    计算集合的dice相关性
    """
    if len(set1) == 0 or len(set2) == 0:
        return 0
    cross_set = set1 & set2
    merge_set = set1 | set2 
    sim_score = len(cross_set) / len(merge_set)
    return sim_score

def context_dice(text1, text2):
    """
    计算dice相关性
    """
    if len(text1) == 0 or len(text2) == 0:
        return 0
    cross_str = set(text1) & set(text2)
    merge_str = set(text1) | set(text2)
    sim_score = len(cross_str) / len(merge_str)
    #logging.info('cross_str[%s], corss_len[%s], merge_len[%s], sim_score[%s]', cross_str, len(cross_str), len(merge_str), sim_score)
    return sim_score

def context_dice_min(text1, text2):
    """
    计算dice相关性,分母取最小值
    """
    if len(text1) == 0 or len(text2) == 0:
        return 0
    cross_str = set(text1) & set(text2)
    #merge_str = set(text1) | set(text2)
    sim_score = len(cross_str) / min(len(set(text1)), len(set(text2)))
    #logging.info('cross_str[%s], corss_len[%s], merge_len[%s], sim_score[%s]', cross_str, len(cross_str), len(merge_str), sim_score)
    return sim_score


def clear_attr_v(attr_value):
    """
    清洗属性值
    """
    attr_value = attr_value.strip().lower()
    if '其它_' in attr_value:
        attr_value = attr_value.replace('其它_', '')
    if '其他_' in attr_value:
        attr_value = attr_value.replace('其他_', '')
    if '其它' in attr_value:
        attr_value = attr_value.replace('其它', '')
    if '其他' in attr_value:
        attr_value = attr_value.replace('其他', '')

    return attr_value


def clear_v_list(content, clear_list):
    """
    清洗content内容
    """
    try:
        clear_re_str = '|'.join(clear_list)
        clear_re_str = clear_re_str.replace('(', '\(').replace(')', '\)')
        content = re.sub(clear_re_str, '', content)
    except:
        tb = traceback.format_exc()
        logging.error('tb[%s]', tb)
        logging.error('clear_re[%s], content[%s]', clear_re_str, content)
    return content


def load_attr_map_dict(data_file):
    """
    加载属性映射字典
    """
    map_dict = dict()
    with open(data_file) as df:
        for line in df:
            line = line.strip()
            fields = line.split('\t')
            if len(fields) < 3:
                logging.error('error_line[%s]', line)
                continue
                #exit(1)
            attr_name = fields[0]
            v1 = fields[1]
            v2 = fields[2]
            map_dict.setdefault(attr_name, {})
            map_dict[attr_name][v1] = v2
    return map_dict


def get_atrr_value(attr_name, value_list):
    """
    args:
        attr_name:属性名
        value_list:属性值列表
    """
    for value_info in value_list:
        if value_info['name'] == attr_name:
            value = value_info['value']
            return value
    return None

def get_sex(content):
    """
    获取性别
    """
    sex = 0
    if '男' in content and '女' in content:
        sex = 3
    elif '男' in content:
        sex = 1
    elif '女' in content:
        sex = 2
    return sex


def replace_loop(json_str):
    while True:
        left_index = json_str.find("\"{")
        if left_index < 0:
            break
        begin_index = json_str.rfind(",", 0, left_index)
        right_index = json_str.find("}\"")
        json_str = json_str[:begin_index] + json_str[right_index + 2:]
    return json_str

def parse_java_json(json_str, default_return={}):
    if json_str is None or json_str == "":
        return default_return
    # json_str = json_str.replace("\\", "")
    json_str = replace_loop(json_str)
    try:
        json_dict = json.loads(json_str)
        return json_dict
    except Exception as err:
        print("json parse load: {}, {}".format(err, json_str))
        return default_return


def clear_purchase_attr(name, value_list, need_split=True, split_char=None):
    """'
    清洗属性值
    """
    new_value_set = set()
    if split_char is None:
        split_char = '\t| |；|、|,|，|\+'
    for v_l in value_list:
        if v_l == '':
            continue
        v_split_list = re_split(v_l, split_char)
        for v in v_split_list:
            v = clear_attr_v(v) 
            #if v == '' or v == ' ' or v == '其他' or v == '其它':
            if v in PURCHASE_FILTER_LIST:
                continue
            new_value_set.add(v)
    return list(new_value_set)


def pad_and_cut_sequence(sequence, seq_len, pad_value='[mask]'):
    """
    """
    if len(sequence) < seq_len:
        sequence = sequence + [pad_value] * (seq_len - len(sequence))
    elif len(sequence) > seq_len:
        sequence = sequence[0: seq_len]
    return sequence



def seg_to_char(seg_list):
    """
    将切词转化为字符级别分割, 中文单独一个字，英文一个seg即可
    """
    char_list = list()

    if type(seg_list) == str:
        seg_list = [seg_list]
    for seg in seg_list:
        last_char = ''
        for c in seg:
            if not is_chinese_char(c):
                last_char += c
                continue
            if last_char != '':
                char_list.append(last_char)
            char_list.append(c)
            last_char = ''
        if last_char != '':
            char_list.append(last_char)
    return char_list

                
def count_freq_dict(ele_list):
    """
    统计各元素频率
    """
    count_dict = dict()
    for e in ele_list:
        count_dict[e] = count_dict.get(e, 0) + 1
    return count_dict

def get_pair_key(v_pair):
    """
    获取同义词pair的key
    """
    s_k = ' '.join(sorted(list(v_pair)))
    return s_k


def get_map_name_by_category(name, category, attr_name_map_dict, limit_category=None):
    
    """
    根据类目获取名称映射
    """
    if limit_category is None:
        map_name = attr_name_map_dict.get(category, {}).get(name, name)
    else:
        map_name = attr_name_map_dict.get(category, {}).get(name, {}).get(limit_category, name)
    if map_name != name:
        return map_name

    if limit_category is None:
        map_name = attr_name_map_dict.get('all', {}).get(name, name)
    else:
        map_name = attr_name_map_dict.get('all', {}).get(name, {}).get(limit_category, name)
    return map_name

def normlize_score_dict(score_dict):
    """
    """
    score_sum = sum(score_dict.values())
    new_score_dict = dict()
    for key, score in score_dict.items():
        new_score_dict[key] = score / score_sum
    return new_score_dict


def load_map_file(map_file):
    """
    map_file: key\tvalue
    """
    map_dict = {}
    with open(map_file, 'r') as f:
        for line in f:
            key, value = line.strip().split('\t')
            map_dict[key] = value
    return map_dict

def clear_none_value(data, is_local=False):
    """
    清除字典中的null值，并返回新的字典
    """
    new_data = {}
    for key, value in data.items():
        if value is not None and not is_local:
            new_data[key] = value
    return new_data

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    #context_dice('你是谁', '你好吗')
    #print(clear_attr_v('其他_算'))
    #print(clear_v_list('其他_算_林豪放肥四', ['其他|林豪|f']))
    #print(filter_chinese('你123好啊', True))
    #print(filter_chinese('你123好啊', False))
    print(seg_to_char(['米好', 'fen利空ni', 'fes']))
    print(seg_to_char('fen利空ni'))
    print(seg_to_char('fenni'))

