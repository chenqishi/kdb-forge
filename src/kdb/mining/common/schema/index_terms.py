#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-14
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

import jieba
import jieba.analyse


def get_keyword_list(text, topK=5):    
    keywords = jieba.analyse.extract_tags(text, topK=topK)
    return keywords
# 纯本地索引词生成，与远端平台无关；仅调整名称，保留原关键词规则。
def build_qa_index_terms(query, answer, plat_form=None):
    """
    """
    indexes = []
    if query:
        indexes.append(query)
        if plat_form:
            indexes.append(f'{plat_form} {query}')    
    if answer:  
        keywords = jieba.analyse.extract_tags(answer, topK=10)
        keywords = ','.join(keywords)
        indexes.append(keywords)        
    return indexes

def build_cdiscount_index_terms(seg_topic, segment, title, topics):
    """
    """
    indexes = []
    if seg_topic:
        indexes.append(seg_topic)
    if title:
        indexes.append(title)
        indexes.append(f'cdiscount {title}')
    segment = segment.replace('\\n', '\n')    
    topics = topics.split(",")
    keywords = get_keyword_list(segment)
    keywords = ','.join(keywords)
    indexes.append(keywords)
    return indexes
