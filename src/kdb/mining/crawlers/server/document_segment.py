#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-08-19
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
def split_onecontent(file_content, separator=r'\n\s*\+', clear_blank=r'\n\s*-'):
            
    #contents = open(, encoding="utf-8").read()
    #contents = contents.split(separator)
    contents = re.split(separator, file_content)
    new_contents = []
    for index, content in enumerate(contents):
        if index != 0:
            #content = content.lstrip('+')
            content = '+' + content.strip()
            
        #content = re.sub(clear_blank, '\n', content.strip())
        if not content:
            continue
        #content = f'{content}\t{len(content)}'
        new_contents.append(content)
    return new_contents

def segment_one_document(file_path, save_path, black_word_file=None, separator=r'\n\s*\+', clear_blank=r'\n\s*-'):
    """
    segment one document
    """
    if black_word_file is not None:
        black_word = open(black_word_file, encoding="utf-8").read().split('\n')
        black_word = [w.strip() for w in black_word if w]
    else:
        black_word = []

    content = open(file_path, encoding="utf-8").read()
    contents = split_onecontent(content, separator=separator, clear_blank=clear_blank)
    new_contents = []
    for content in contents:
        if black_word and any([w in content for w in black_word]):
            continue
        new_contents.append(content)
    new_content = '\n------\n'.join(new_contents)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(new_content)
    
def process_files(directory_path, black_word_file=None):
    for root, dirs, files in os.walk(directory_path):
        for file in files:
            file_path = os.path.join(root, file)
            file_name, file_extension = os.path.splitext(file)
            logging.info('process file: %s',  file_name)
            if file_name.startswith(r'.'):
                continue
            new_file_name = file_name + '_reclear.txt'
        
            new_file_path = os.path.join(root, new_file_name)
            logging.info('start process file: %s, new_file %s',  file_path, new_file_path)
            segment_one_document(file_path, new_file_path, black_word_file=black_word_file)


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')
    import fire
    fire.Fire()
    

