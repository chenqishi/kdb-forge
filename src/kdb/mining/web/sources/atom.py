#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-09-01
description:
    微信公众号服务
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


import requests
from bs4 import BeautifulSoup


class AtomFeedParser(object):
    def __init__(self):
        #self.base_url = base_url
        pass

    def parse_atom_feed(self, base_url):
       #url = self.base_url + '/feeds/all.atom'
        url = base_url + '/feeds/all.atom'
        response = requests.get(url)
        soup = BeautifulSoup(response.content, 'xml')
        entries = soup.find_all('entry')
        result = []
        for entry in entries:
            try:        
                author_name = None
                for child in entry.author.children:
                    if child.name == 'name':
                        author_name = child.text.strip()
                        break                    
                item = {
                    'title': entry.title.text.strip(),
                    'id': entry.id.text.strip(),
                    'link': entry.link['href'].strip(),
                    'updated': entry.updated.text.strip(),
                    'author': author_name
                }
                result.append(item)
            except Exception as e:
                tb = traceback.format_exc()
                logging.error('tb[%s]', tb)
                logging.error('entry[%s]', entry)
        return result
    
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s %(filename)s[line:%(lineno)d] %(levelname)s %(message)s',
        datefmt='%a, %d %b %Y %H:%M:%S')
    parser = AtomFeedParser()
    print(json.dumps(parser.parse_atom_feed(), ensure_ascii=False, indent=4))
    
















































































