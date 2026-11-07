#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-15
"""
import sys
import os
import json
import logging
import traceback
def filter_query_by_mark(data_file, flag_field, select_mark='类别1', query_idx=1):
    # 用于存储按 conversion_id 分组的数据
    grouped_data = {}
    
    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            fields = line.strip().split('\t')
            # conversion_id 在第一列
            conv_id = fields[0]
            
            # 按 conversion_id 分组存储数据
            if conv_id not in grouped_data:
                grouped_data[conv_id] = {'data': [], 'has_mark': False}
            
            grouped_data[conv_id]['data'].append(fields)
            # 检查当前行的 mark 是否等于 select_mark
            if fields[int(flag_field)].find(select_mark) != -1:
                grouped_data[conv_id]['has_mark'] = True
    
    # 输出符合条件的组的所有数据
    print_field = query_idx + 1
    for conv_id, group in grouped_data.items():
        if group['has_mark']:
            for fields in group['data']:
                print('\t'.join(fields[0: print_field]))


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()