#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-10-20
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

import time 
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
# Main Function 
if __name__ == '__main__': 

    options = webdriver.ChromeOptions() 
    options.add_argument("--start-maximized") 
    options.add_argument('--log-level=3') 

# Provide the path of chromedriver present on your system. 
    service = Service('/usr/local/bin/chromedriver')
    driver = webdriver.Chrome(service=service)

# Send a get request to the url 
# 创建浏览器对象

# 打开网页
    #url = "https://university.qoo10.jp/faq/?utm_source=mail&utm_medium=request&utm_campaign=qoo10university"
    url = "https://www.onbuy.com/gb/sell/#faqs"
    driver.get(url)

# 获取页面源代码
    page_source = driver.page_source

# 关闭浏览器
    driver.quit()

    print(page_source)
