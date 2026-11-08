#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-08
description:
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
from kdb.mining.common.schema.index_terms import get_fastgpt_index
from kdb.mining.common.schema.index_terms import get_fastgpt_index_cdiscount

def add_attrs_and_indexs(data_file, plat_form='None'):
    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            query, answer = line.split('\t')
            attrs = ''
            if plat_form:
                attrs += f'平台:{plat_form}'
            indexes = get_fastgpt_index(query, answer, plat_form)            
            print('\t'.join([query, answer, attrs, '|'.join(indexes)]))

def process_data_cdiscount(data_file):
    """
    处理数据
    """
    plat_form = 'cdiscount'

    with open(data_file, 'r', encoding='utf-8') as f:
        for line in f:
            attrs = ''
            line = line.strip('\n')
            if not line:
                continue
            fields = line.split('\t')
            if len(fields) != 4:
                continue
            seg_topic, segment, title, topics = line.split('\t')
            
            indexes = get_fastgpt_index_cdiscount(seg_topic, segment, title, topics)
            if plat_form:
                attrs += f'平台:{plat_form}'
            print('\t'.join([seg_topic, segment, attrs, '|'.join(indexes)]))



if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()