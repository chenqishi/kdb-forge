from kdb.mining.tasks.records import get_task_info
import json
import kdb.mining.tasks.state as runtime_state
import logging
import os

def load_task_resource_config(config_file=None):
    """加载任务资源占用配置文件"""


    if config_file is None:
        config_file = os.path.join(runtime_state.script_base_dir, 'config', 'task_resource_config.json')

    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                runtime_state.task_resource_usage = config.get('task_resource_usage', {})
                runtime_state.max_total_concurrency = config.get('max_total_concurrency', 10)
                logging.info(f"任务资源配置加载成功: {config_file}")
                logging.info(f"总并发数限制: {runtime_state.max_total_concurrency}")
                logging.info(f"任务资源占用配置: {runtime_state.task_resource_usage}")
        else:
            # 使用默认配置
            runtime_state.task_resource_usage = {
                'document_qa_mining': 1,
                'document_qa_segment_mining': 1,
                'chat_qa_mining': 1,
                'html_qa_segment_mining': 1,
                'excel_qa_segment_upload': 1
            }
            runtime_state.max_total_concurrency = 10
            logging.info("使用默认任务资源配置")
    except Exception as e:
        logging.error(f"加载任务资源配置失败: {e}")
        # 使用默认配置
        runtime_state.task_resource_usage = {
            'document_qa_mining': 1,
            'document_qa_segment_mining': 1,
            'chat_qa_mining': 1,
            'html_qa_segment_mining': 1,
            'excel_qa_segment_upload': 1
        }
        runtime_state.max_total_concurrency = 10
        logging.info("使用默认任务资源配置")


def get_task_resource_usage(task_type):
    """获取任务类型的资源占用量"""
    return runtime_state.task_resource_usage.get(task_type, 1)


def release_task_resources(task_id):
    """释放任务占用的资源"""


    # 从数据库获取任务信息以确定任务类型
    task_info = get_task_info(task_id)
    if task_info:
        task_type = task_info.get('task_type')
        if task_type:
            required_resources = get_task_resource_usage(task_type)
            with runtime_state.resource_lock:
                runtime_state.current_resource_usage -= required_resources
                if runtime_state.current_resource_usage < 0:
                    runtime_state.current_resource_usage = 0  # 防止负数
                logging.info(f"任务 {task_id} 释放资源: {required_resources}, 当前总使用: {runtime_state.current_resource_usage}")
