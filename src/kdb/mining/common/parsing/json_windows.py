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

def process_json_file(file_path, data_type="str"):
    write_f = open(re.sub('\..*?','',file_path) + '_处理结果.txt', 'w')
    with open(file_path, "r") as f:
        data_list = json.load(f)
        for data_info in data_list:
            title = data_info.get("title")
            title = '+' + title 
            title = title.replace('ESG跨境', '').replace('ESG', '')
            content = data_info['html'].replace('ESG跨境', '')
            #content = re.sub('推荐阅读.*', '', content)
            content = content.split('推荐阅读', )[0]
            content = content.split('特别声明', )[0]
            content = re.sub('[点赞|收藏]', '', content)
            if data_type == "str":
                content = content.replace('\n', '\\n')
            if data_type == "str":
                    
                write_f.write(f'{title}\n')
                write_f.write(f'{content}\n')
                write_f.write(f'\n\n')
            elif data_type == "json":
                new_data_info = {}
                new_data_info["title"] = title
                new_data_info["content"] = content
                print_line = json.dumps(new_data_info, ensure_ascii=False)
                write_f.write(print_line + '\n')
    write_f.close()
           



        

def select_file():
    root = tk.Tk()
    root.withdraw()  # 隐藏主窗口
    file_path = filedialog.askopenfilename(title="Select a JSON file", filetypes=[("JSON files", "*.json")])
    if file_path:
        process_json_file(file_path, 'json')
    else:
        print("No file selected")


if __name__ == "__main__":
    select_file()
    #os.system("pause")
