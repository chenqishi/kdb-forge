from kdb.shared.config.paths import source_path as _source_path
#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2023 tencent.com, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(qishichen.tencent.com)
Date: 2024-07-14
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

import random
from flask import Flask
from flask import request
from flask import jsonify
from pydantic import BaseModel

import kdb.mining.web.workflows.rss as controller
app = Flask(__name__, root_path=str(_source_path('kdb', 'services', 'crawler')))

logic_processer = controller.ProcessLogitic(update_time=(datetime.now() + timedelta(days=-1)).strftime('%Y-%m-%d %H:%M:%S'), data_dir="./data")  




@app.route("/process_params", methods=["POST"])
def process_params():
    #params = InputParams(**request.json)
    #params = request.json 
    params = request.get_json()
    logging.info('receive params: {}'.format(params))
    mp_list_url = params['wewe_base_url'] 
    #crawler_and_analysis_url = params.get('dify_url', )
    #api_key = params['api_key']
    save_file = params['save_file']
    #is_build_dataset = params['is_build_dataset']

    result_json = logic_processer.main_process(params)


    return jsonify({"code": 0,  'data': result_json, "msg": "success"})

if __name__ == "__main__":
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')    
    app.run(host="0.0.0.0", port=6001, debug=True)


