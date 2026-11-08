import json
import logging
import os
from collections import defaultdict
from typing import Dict
from typing import Set
from typing import List
from typing import Tuple
import kdb.shared.clients.channel_communicate_by_request as channel_communicate_by_request
from kdb.shared.text.common_utils import is_contain_value
import traceback
from datetime import datetime
import shutil
import sys
import time
from kdb.shared.config.global_config import GLOBAL_CONFIG
def convert_time_format(time_str: str) -> str:
    """
    检查时间格式并转换为标准格式 (YYYY-MM-DD HH:MM:SS)
    
    Args:
        time_str: 输入的时间字符串
        
    Returns:
        标准格式的时间字符串
    """
    # 尝试不同的时间格式
    formats = [
        "%Y-%m-%d %H:%M:%S",  # 2025-03-05 10:52:11
        "%Y/%m/%d %H:%M:%S",  # 2025/03/05 10:52:11
        "%Y-%m-%d",           # 2025-03-05
        "%Y/%m/%d",           # 2025/03/05
        "%Y%m%d%H%M%S",       # 20250305105211
        "%Y%m%d"              # 20250305
    ]
    if isinstance(time_str, int):
        time_str = str(time_str)
    for fmt in formats:
        try:
            # 尝试解析时间字符串
            dt = datetime.strptime(time_str, fmt)
            # 转换为标准格式
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    
    # 如果所有格式都不匹配，抛出异常
    raise ValueError(f"无法识别的时间格式: {time_str}")


def gen_text_qa_detail_report(json_data_file: str,  start_time: str, end_time: str):
    """
    生成text_qa详情报告
    """
    # 标准化时间格式
    report = ''
    qa_list = []
    with open(json_data_file, 'r') as f:
        index = 1
        for line in f:
            data = json.loads(line)
            if data['insert_time'] < start_time or data['insert_time'] > end_time:
                continue
            is_valid = (data.get('quality_level', 'mid') == 'high' and data.get('audit_result', -1) != 0) or data.get('audit_result', -1) == 1 
            if not is_valid:
                qa = f'{index}.问题:{data["title"]}\n答案:{data["content"]}\n该问题未在线上起作用，若错误可忽略'
            else:
                qa = f'{index}.问题:{data["title"]}\n答案:{data["content"]}\n该问题在线上起作用, 若有问题请及时告知'
            qa_list.append(qa)
            index += 1
    report = []
    if qa_list:
        report.append(f"以下为{start_time}到{end_time}的学习到的知识，请检查")
        report.extend(qa_list)
        has_new_knowledge = True
        
    else:
        report.append(f"在{start_time}到{end_time}期间没有新的知识")
        has_new_knowledge = False
    return report, has_new_knowledge

def gen_chatknowledge_report(json_data_file: str, excel_file_path: str, receiver: str, send_url: str, start_time: str, end_time: str):
    """
    生成chatknowledge报告
    """
    # 标准化时间格式
    start_time = convert_time_format(start_time)
    end_time = convert_time_format(end_time)    
    sender = channel_communicate_by_request.ChannelRequestCommunicate(base_url=send_url)
    report, has_new_knowledge = gen_text_qa_detail_report(json_data_file, start_time, end_time)

    # 处理Excel文件
    excel_file_url = None
    if has_new_knowledge and excel_file_path:
        try:
            
            excel_file_name = os.path.basename(excel_file_path)
            target_path = f'/root/remote_dir_file/data/{excel_file_name}'
            shutil.copy2(excel_file_path, target_path)
            excel_file_url = f"{GLOBAL_CONFIG['data_file_base_url']}/data/{excel_file_name}"
        except Exception as e:
            logging.error(f"复制Excel文件失败: {str(e)}")
            excel_file_url = None
        
    receiver = receiver.split('&&&')
    for r in receiver:
        if r.endswith(':group'):
            logging.info(f"原始数据:{r}")
            is_group = True
            r  = r.strip(':group')
            logging.info(f"发送给{r}，是否群发:{is_group}")
        else:
            is_group = False
        for one in report:
            sender.send_wx(one, r, is_group)
            time.sleep(1)
        if has_new_knowledge and excel_file_url:
            sender.send_wx(excel_file_url, r, is_group, 'FILE')


    
    

if __name__ == '__main__':
    import logging
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')   
    import fire
    fire.Fire({
        'gen_chatknowledge_report': gen_chatknowledge_report
    })

    

