#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-08-30
"""
import json
import tkinter as tk
from tkinter import filedialog
import os
import re

class ContentClearer(object):
    def clear_one_json(self, data_info):
        """
        """
        title = data_info.get("title")
        title = '+' + title 
        title = title.replace('ESG跨境', '')
        content = self.clear_content(data_info['content'])
        new_data_info = {}
        new_data_info["title"] = title
        new_data_info["content"] = content
        print_line = json.dumps(new_data_info, ensure_ascii=False)

        return new_data_info
    def clear_content(self, content: str):
        """
        """
        content =content.replace('ESG跨境', '').replace('ESG', '')
        #content = re.sub('推荐阅读.*', '', content)
        content = content.split('推荐阅读', )[0]
        content = content.split('特别声明', )[0]
        content = re.sub('[点赞|收藏]', '', content)
        return content

    
        

           

if __name__ == "__main__":
    pass
    #os.system("pause")
