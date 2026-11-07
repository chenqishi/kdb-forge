#!/usr/bin/env python
# -*- coding:utf8 -*-

import logging
import requests
import time
import traceback
import sys
import json

def parse_wx_name_id(file_path):
    data_json = json.load(open(file_path, 'r', encoding='utf-8'))
    users_info_dict = data_json['id_to_user_info']
    for uid, user_infos in users_info_dict.items():
        user_info = user_infos[0]
        if "is_room" not in user_info:
            if "@chatroom" not in uid:
                is_room = 0
            else: 
                is_room = 1
        else:
            is_room = int(user_info['is_room'])
        print(f"{uid}\t{user_info['nickName']}\t{is_room}")

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')      
    import fire
    fire.Fire({
        'parse_wx_name_id': parse_wx_name_id,
    })
    
