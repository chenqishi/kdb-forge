from datetime import datetime
import hashlib
import json

def generate_task_id(task_type, task_info):
    """根据task_type和task_info生成task_id"""
    # 将task_info转换为字符串
    task_info_str = json.dumps(task_info, sort_keys=True)
    #允许同一任务重启，所以需要加上时间戳
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    # 生成MD5哈希
    task_string = f"{task_type}_{task_info_str}_{timestamp}"
    task_id = hashlib.md5(task_string.encode('utf-8')).hexdigest()
    return task_id
