from kdb.compat.layout import legacy_package_path as _legacy_package_path
#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-01-01
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('control_service/off_task_control_service.py')
import sys
import os
import json
import time
import logging
import hashlib
import threading
import subprocess
import psutil
from datetime import datetime
from queue import Queue, Empty
from collections import defaultdict

from flask import Flask, request, jsonify
from mysql.connector import Error
import traceback

# 添加项目根目录到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))
from commons.mysql_connector import MySQLConnector
from data_preprocess.document_clear_price_access import asscess_document_clear_price

app = Flask(__name__, root_path=_legacy_package_path('control_service/off_task_control_service.py'))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
           '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
)

# 全局变量
mysql_connector = None
task_pid_mapping = {}  # 存储task_id到pid的映射
monitoring_thread = None
should_monitor = True
script_base_dir = None  # 脚本基础目录

# 任务队列相关变量
task_queue = Queue()  # 任务队列
task_worker_thread = None  # 任务工作线程
should_process_tasks = True  # 控制任务处理线程
task_resource_usage = {}  # 每类任务的资源占用配置
max_total_concurrency = 10  # 总并发数限制
current_resource_usage = 0  # 当前资源使用量
resource_lock = threading.Lock()  # 资源使用量锁

def init_script_base_dir(provided_dir=None):
    """初始化脚本基础目录"""
    global script_base_dir
    if provided_dir:
        # 使用提供的目录路径
        script_base_dir = os.path.abspath(provided_dir)
    else:
        # 默认使用当前服务脚本的上级目录
        script_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__)))
    
    logging.info(f"脚本基础目录设置为: {script_base_dir}")
    
    # 检查脚本目录是否存在
    script_dir = os.path.join(script_base_dir, 'control_service')
    if not os.path.exists(script_dir):
        logging.warning(f"脚本目录不存在: {script_dir}")
    else:
        logging.info(f"脚本目录确认存在: {script_dir}")

def init_mysql_connector():
    """初始化MySQL连接"""
    global mysql_connector
    config_path = os.path.join(script_base_dir, 'config', 'mysql_conn_config.json')
    mysql_connector = MySQLConnector(config_path)
    logging.info("MySQL连接初始化完成")

def load_task_resource_config(config_file=None):
    """加载任务资源占用配置文件"""
    global task_resource_usage, max_total_concurrency
    
    if config_file is None:
        config_file = os.path.join(script_base_dir, 'config', 'task_resource_config.json')
    
    try:
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                task_resource_usage = config.get('task_resource_usage', {})
                max_total_concurrency = config.get('max_total_concurrency', 10)
                logging.info(f"任务资源配置加载成功: {config_file}")
                logging.info(f"总并发数限制: {max_total_concurrency}")
                logging.info(f"任务资源占用配置: {task_resource_usage}")
        else:
            # 使用默认配置
            task_resource_usage = {
                'document_qa_mining': 1,
                'document_qa_segment_mining': 1,
                'chat_qa_mining': 1,
                'html_qa_segment_mining': 1,
                'excel_qa_segment_upload': 1
            }
            max_total_concurrency = 10
            logging.info("使用默认任务资源配置")
    except Exception as e:
        logging.error(f"加载任务资源配置失败: {e}")
        # 使用默认配置
        task_resource_usage = {
            'document_qa_mining': 1,
            'document_qa_segment_mining': 1,
            'chat_qa_mining': 1,
            'html_qa_segment_mining': 1,
            'excel_qa_segment_upload': 1
        }
        max_total_concurrency = 10
        logging.info("使用默认任务资源配置")

def get_task_resource_usage(task_type):
    """获取任务类型的资源占用量"""
    return task_resource_usage.get(task_type, 1)

def task_worker():
    """任务工作线程，从队列中取出任务并执行"""
    global current_resource_usage
    
    while should_process_tasks:
        try:
            # 从队列中获取任务，超时1秒
            task_data = task_queue.get(timeout=1)
            
            task_id = task_data['task_id']
            task_type = task_data['task_type']
            task_info = task_data['task_info']
            
            logging.info(f"从队列中取出任务: {task_id}, 类型: {task_type}")
            
            # 检查资源是否足够
            required_resources = get_task_resource_usage(task_type)
            
            with resource_lock:
                if current_resource_usage + required_resources > max_total_concurrency:
                    # 资源不足，将任务重新放回队列
                    task_queue.put(task_data)
                    logging.info(f"资源不足，任务 {task_id} 重新入队。当前使用: {current_resource_usage}, 需要: {required_resources}, 最大: {max_total_concurrency}")
                    time.sleep(5)  # 等待5秒后重试
                    continue
                
                # 资源足够，占用资源
                current_resource_usage += required_resources
                logging.info(f"任务 {task_id} 开始执行，占用资源: {required_resources}, 当前总使用: {current_resource_usage}")
            
            # 更新任务状态为运行中（状态编码：2-运行中）
            update_task_status(task_id, 2, "运行中")
            
            # 启动任务
            pid = start_mining_task(task_type, task_info, task_id)
            if pid is None:
                # 启动失败，释放资源并更新状态（状态编码：1-异常）
                with resource_lock:
                    current_resource_usage -= required_resources
                update_task_status(task_id, 1, "启动失败")
                logging.error(f"任务 {task_id} 启动失败")
            else:
                # 启动成功，记录PID映射
                task_pid_mapping[task_id] = pid
                logging.info(f"任务 {task_id} 启动成功，PID: {pid}")
            
            # 标记任务完成
            task_queue.task_done()
            
        except Empty:
            # 队列为空，继续循环
            continue
        except Exception as e:
            logging.error(f"任务工作线程处理任务时出错: {e}")
            # 如果任务数据存在，标记完成以避免队列阻塞
            if 'task_data' in locals():
                task_queue.task_done()
            time.sleep(1)

def add_task_to_queue(task_id, task_type, task_info):
    """将任务添加到队列中"""
    task_data = {
        'task_id': task_id,
        'task_type': task_type,
        'task_info': task_info
    }
    task_queue.put(task_data)
    # 更新任务状态为排队中（状态编码：4-等待）
    update_task_status(task_id, 4, "排队中")
    logging.info(f"任务 {task_id} 已添加到队列，队列大小: {task_queue.qsize()}")

def start_task_worker():
    """启动任务工作线程"""
    global task_worker_thread
    if task_worker_thread is None or not task_worker_thread.is_alive():
        task_worker_thread = threading.Thread(target=task_worker, daemon=True)
        task_worker_thread.start()
        logging.info("任务工作线程启动成功")

def stop_task_worker():
    """停止任务工作线程"""
    global should_process_tasks
    should_process_tasks = False
    logging.info("任务工作线程停止")

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

def insert_task_record(task_id, task_type, task_info):
    """插入任务记录到数据库"""
    connection = mysql_connector.get_connection()
    if connection is None:
        return False
    
    try:
        cursor = connection.cursor()
        # 从task_info中获取client和user，允许为空
        client = task_info.get('client')
        user = task_info.get('user')
        # 生成当前时间作为create_time和update_time
        current_time = datetime.now()
        
        sql = """
        INSERT INTO rufitai.dops_task_kggen_info 
        (task_id, task_type, task_info, task_stage, task_process_rate, run_status, related_pid, client, user, create_time, update_time)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            task_id,
            task_type,
            json.dumps(task_info, ensure_ascii=False),
            "未运行",
            "",
            0,
            "",
            client,
            user,
            current_time,
            current_time
        )
        cursor.execute(sql, values)
        connection.commit()
        logging.info(f"任务记录插入成功: {task_id}")
        return True
    except Error as e:
        logging.error(f"插入任务记录失败: {e}")
        connection.rollback()
        return False
    finally:
        mysql_connector.close_connection(connection, cursor)

def update_task_status(task_id, run_status, task_stage=None, pid=None):
    """更新任务状态"""
    connection = mysql_connector.get_connection()
    if connection is None:
        return False
    
    try:
        cursor = connection.cursor()
        
        # 构建更新语句，每次更新都自动更新update_time
        update_fields = ["run_status = %s", "update_time = %s"]
        current_time = datetime.now()
        values = [run_status, current_time]
        
        if task_stage:
            update_fields.append("task_stage = %s")
            values.append(task_stage)
        
        if pid:
            update_fields.append("related_pid = %s")
            values.append(str(pid))
        
        values.append(task_id)
        
        sql = f"""
        UPDATE rufitai.dops_task_kggen_info 
        SET {', '.join(update_fields)}
        WHERE task_id = %s
        """
        
        cursor.execute(sql, values)
        connection.commit()
        logging.info(f"任务状态更新成功: {task_id}, status: {run_status}")
        return True
    except Error as e:
        logging.error(f"更新任务状态失败: {e}")
        connection.rollback()
        return False
    finally:
        mysql_connector.close_connection(connection, cursor)

def get_task_info(task_id):
    """获取任务信息"""
    connection = mysql_connector.get_connection()
    if connection is None:
        return None
    
    try:
        cursor = connection.cursor(dictionary=True)
        sql = """
        SELECT task_id, task_type, task_stage, task_process_rate, run_status, task_result
        FROM rufitai.dops_task_kggen_info 
        WHERE task_id = %s
        """
        cursor.execute(sql, (task_id,))
        results = cursor.fetchall()
        
        if len(results) == 0:
            return None
        elif len(results) > 1:
            logging.error(f"发现多个任务记录: {task_id}")
            return None
        final_result = results[0]
        if final_result.get('task_result'):
            final_result['task_result'] = json.loads(final_result['task_result'])
        else:
            final_result['task_result'] = {}
        return final_result
    except Error as e:
        logging.error(f"查询任务信息失败: {e}")
        return None
    finally:
        mysql_connector.close_connection(connection, cursor)

def get_task_full_info(task_id):
    """获取任务完整信息（包括task_info）"""
    connection = mysql_connector.get_connection()
    if connection is None:
        return None
    
    try:
        cursor = connection.cursor(dictionary=True)
        sql = """
        SELECT task_id, task_type, task_info, task_stage, task_process_rate, 
               run_status, related_pid, task_result, client, user
        FROM rufitai.dops_task_kggen_info 
        WHERE task_id = %s
        """
        cursor.execute(sql, (task_id,))
        results = cursor.fetchall()
        
        if len(results) == 0:
            return None
        elif len(results) > 1:
            logging.error(f"发现多个任务记录: {task_id}")
            return None
        
        final_result = results[0]
        
        # 解析JSON字段
        if final_result.get('task_info'):
            try:
                final_result['task_info'] = json.loads(final_result['task_info'])
            except json.JSONDecodeError as e:
                logging.error(f"解析task_info失败: {e}")
                final_result['task_info'] = {}
        else:
            final_result['task_info'] = {}
        
        if final_result.get('task_result'):
            try:
                final_result['task_result'] = json.loads(final_result['task_result'])
            except json.JSONDecodeError as e:
                logging.error(f"解析task_result失败: {e}")
                final_result['task_result'] = {}
        else:
            final_result['task_result'] = {}
        
        return final_result
    except Error as e:
        logging.error(f"查询任务完整信息失败: {e}")
        return None
    finally:
        mysql_connector.close_connection(connection, cursor)

def reset_task_status(task_id):
    """重置任务状态，准备重新启动"""
    connection = mysql_connector.get_connection()
    if connection is None:
        return False
    
    try:
        cursor = connection.cursor()
        current_time = datetime.now()
        
        # 重置状态：run_status=0（未运行），task_stage=未运行，清空related_pid
        sql = """
        UPDATE rufitai.dops_task_kggen_info 
        SET run_status = %s, 
            task_stage = %s, 
            task_process_rate = %s,
            related_pid = %s,
            update_time = %s
        WHERE task_id = %s
        """
        values = (0, "未运行", "", "", current_time, task_id)
        
        cursor.execute(sql, values)
        connection.commit()
        logging.info(f"任务状态重置成功: {task_id}")
        return True
    except Error as e:
        logging.error(f"重置任务状态失败: {e}")
        connection.rollback()
        return False
    finally:
        mysql_connector.close_connection(connection, cursor)

def start_mining_task(task_type, task_info, task_id):
    """启动挖掘任务"""
    if task_type == "document_qa_mining":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = os.path.join(script_base_dir, 'control_service', 'document_qa_mining_task_control.py')
        task_info_json = json.dumps(task_info, ensure_ascii=False)
        
        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"挖掘脚本不存在: {script_path}")
                return None
            
            # 创建任务日志目录
            task_log_dir = os.path.join(script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)
            
            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')
            
            # 构建正确的命令行参数
            cmd = [
                sys.executable, script_path,
                '--script-dir', script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]
            
            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')
            
            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()
            
            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=script_base_dir,  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )
            
            logging.info(f"任务启动成功，执行命令: {' '.join(cmd)}")
            logging.info(f"文档QA挖掘任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}")
            
            return process.pid
        except FileNotFoundError:
            logging.error(f"挖掘脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None
    
    elif task_type == "document_qa_segment_mining":
        script_path = os.path.join(script_base_dir, 'control_service', 'document_qa_segment_mining.py')
        task_info_json = json.dumps(task_info, ensure_ascii=False)

        try:
            if not os.path.exists(script_path):
                logging.error(f"文档段落QA挖掘脚本不存在: {script_path}")
                return None

            task_log_dir = os.path.join(script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)

            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')

            cmd = [
                sys.executable, script_path,
                '--script-dir', script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]

            log_file = open(task_log_file, 'w', encoding='utf-8')

            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()

            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=script_base_dir,
                text=True,
                bufsize=1
            )

            logging.info(f"文档段落QA挖掘任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}")

            return process.pid
        except FileNotFoundError:
            logging.error(f"文档段落QA挖掘脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None

    elif task_type == "chat_qa_mining":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = os.path.join(script_base_dir, 'control_service', 'chat_qa_mining_task_control.py')
        task_info_json = json.dumps(task_info, ensure_ascii=False)
        
        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"聊天QA挖掘脚本不存在: {script_path}")
                return None
            
            # 创建任务日志目录
            task_log_dir = os.path.join(script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)
            
            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')
            
            # 构建正确的命令行参数
            cmd = [
                sys.executable, script_path,
                '--script-dir', script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]
            
            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')
            
            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {script_base_dir}\n")
            log_file.write(f"任务信息: 客户={task_info.get('client', '未知')}, 用户={task_info.get('user', '未知')}, 索引={task_info.get('index', task_info.get('client', '未知'))}, 应用ID={task_info.get('app_id', '未知')}\n")
            log_file.write(f"时间范围: {task_info.get('start_time', '未知')} - {task_info.get('end_time', '未知')}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()
            
            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=script_base_dir,  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )
            
            logging.info(f"聊天QA挖掘任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 客户={task_info.get('client', '未知')}, 用户={task_info.get('user', '未知')}, 索引={task_info.get('index', task_info.get('client', '未知'))}, 应用ID={task_info.get('app_id', '未知')}")
            logging.info(f"时间范围: {task_info.get('start_time', '未知')} - {task_info.get('end_time', '未知')}")
            
            return process.pid
        except FileNotFoundError:
            logging.error(f"聊天QA挖掘脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None
    
    elif task_type == "html_qa_segment_mining":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = os.path.join(script_base_dir, 'control_service', 'html_kg_gen_task_control.py')
        task_info_json = json.dumps(task_info, ensure_ascii=False)
        
        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"HTML知识生成脚本不存在: {script_path}")
                return None
            
            # 创建任务日志目录
            task_log_dir = os.path.join(script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)
            
            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')
            
            # 构建正确的命令行参数
            cmd = [
                sys.executable, script_path,
                '--script-dir', script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]
            
            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')
            
            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, URL数量={len(task_info.get('url_infos', []))}\n")
            log_file.write(f"客户: {task_info.get('client', '未知')}\n")
            log_file.write(f"使用Firecrawl: {task_info.get('is_use_firecrawl', False)}\n")
            log_file.write(f"需要翻译: {task_info.get('is_need_translated', False)}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()
            
            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=script_base_dir,  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )
            
            logging.info(f"HTML知识生成任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, URL数量={len(task_info.get('url_infos', []))}")
            logging.info(f"客户: {task_info.get('client', '未知')}")
            logging.info(f"使用Firecrawl: {task_info.get('is_use_firecrawl', False)}")
            logging.info(f"需要翻译: {task_info.get('is_need_translated', False)}")
            
            return process.pid
        except FileNotFoundError:
            logging.error(f"HTML知识生成脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None
    
    elif task_type == "excel_qa_segment_upload":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = os.path.join(script_base_dir, 'control_service', 'excel_qa_segment_upload_control.py')
        task_info_json = json.dumps(task_info, ensure_ascii=False)
        
        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"Excel QA上传脚本不存在: {script_path}")
                return None
            
            # 创建任务日志目录
            task_log_dir = os.path.join(script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)
            
            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')
            
            # 构建正确的命令行参数
            cmd = [
                sys.executable, script_path,
                '--script-dir', script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]
            
            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')
            
            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}\n")
            log_file.write(f"客户: {task_info.get('client', '未知')}\n")
            log_file.write(f"类目: {task_info.get('category_name', '未知')} (ID: {task_info.get('category_id', '未知')})\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()
            
            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=script_base_dir,  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )
            
            logging.info(f"Excel QA上传任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}")
            logging.info(f"客户: {task_info.get('client', '未知')}")
            logging.info(f"类目: {task_info.get('category_name', '未知')} (ID: {task_info.get('category_id', '未知')})")
            
            return process.pid
        except FileNotFoundError:
            logging.error(f"Excel QA上传脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None
    
    else:
        logging.error(f"不支持的任务类型: {task_type}")
        return None

def monitor_tasks():
    """监控任务运行状态"""
    while should_monitor:
        try:
            # 检查所有正在运行的任务
            for task_id, pid in list(task_pid_mapping.items()):
                try:
                    # 检查进程是否还存在
                    if psutil.pid_exists(pid):
                        process = psutil.Process(pid)
                        process_status = process.status()
                        
                        # 如果进程是僵尸进程，说明已经结束
                        if process_status == psutil.STATUS_ZOMBIE:
                            # 获取退出码
                            try:
                                returncode = process.wait(timeout=1)  # 等待1秒获取退出码
                            except psutil.TimeoutExpired:
                                returncode = None
                            
                            # 从映射中移除
                            task_pid_mapping.pop(task_id, None)
                            
                            # 释放资源
                            release_task_resources(task_id)
                            
                            # 根据退出码判断成功或失败
                            if returncode == 0:
                                update_task_status(task_id, 3, "运行完成")
                                logging.info(f"任务 {task_id} (PID: {pid}) 运行完成，退出码: {returncode}")
                            else:
                                update_task_status(task_id, 1, "运行错误")
                                logging.error(f"任务 {task_id} (PID: {pid}) 运行错误，退出码: {returncode}")
                        
                        # 如果进程状态正常，继续监控
                        elif process_status in [psutil.STATUS_RUNNING, psutil.STATUS_SLEEPING]:
                            # 进程正在运行，无需操作，继续监控
                            pass
                        else:
                            # 其他异常状态
                            logging.warning(f"任务 {task_id} (PID: {pid}) 进程状态异常: {process_status}")
                    
                    else:
                        # 进程不存在，先检查数据库中的任务状态
                        task_info = get_task_info(task_id)
                        if task_info:
                            current_status = task_info.get('run_status')
                            # 如果任务已经是结束状态（3完成, 1异常），则不需要修改
                            if current_status in [3, 1]:
                                task_pid_mapping.pop(task_id, None)
                                release_task_resources(task_id)
                                logging.info(f"任务 {task_id} (PID: {pid}) 进程不存在，数据库状态已为结束状态: {current_status}")
                            elif current_status == 4:
                                # 任务状态为等待（排队中），不应该在task_pid_mapping中，清理映射
                                task_pid_mapping.pop(task_id, None)
                                release_task_resources(task_id)
                                logging.warning(f"任务 {task_id} (PID: {pid}) 进程不存在但状态为等待，清理映射")
                            else:
                                # 任务还在运行状态（状态为2），但进程不存在，标记为异常
                                task_pid_mapping.pop(task_id, None)
                                release_task_resources(task_id)
                                update_task_status(task_id, 1, "运行错误")
                                logging.warning(f"任务 {task_id} (PID: {pid}) 进程不存在但状态为运行中，标记为异常")
                        else:
                            # 无法获取任务信息，释放资源
                            task_pid_mapping.pop(task_id, None)
                            release_task_resources(task_id)
                            logging.warning(f"任务 {task_id} (PID: {pid}) 进程不存在且无法获取任务信息")
                
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # 进程已经结束或无权限访问
                    task_pid_mapping.pop(task_id, None)
                    # 释放资源
                    release_task_resources(task_id)
                    update_task_status(task_id, 3, "运行完成")
                    logging.info(f"任务 {task_id} (PID: {pid}) 进程已结束")
                
                except Exception as task_error:
                    logging.error(f"监控任务 {task_id} (PID: {pid}) 时出错: {task_error}")
            
            # 休眠10秒再检查
            time.sleep(10)
        except Exception as e:
            logging.error(f"监控任务时出错: {e}")
            time.sleep(10)

def release_task_resources(task_id):
    """释放任务占用的资源"""
    global current_resource_usage
    
    # 从数据库获取任务信息以确定任务类型
    task_info = get_task_info(task_id)
    if task_info:
        task_type = task_info.get('task_type')
        if task_type:
            required_resources = get_task_resource_usage(task_type)
            with resource_lock:
                current_resource_usage -= required_resources
                if current_resource_usage < 0:
                    current_resource_usage = 0  # 防止负数
                logging.info(f"任务 {task_id} 释放资源: {required_resources}, 当前总使用: {current_resource_usage}")

@app.route('/start_task', methods=['POST'])
def start_task():
    """启动任务API"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空"}), 400
        
        task_type = data.get('task_type')
        task_info = data.get('task_info')
        
        if not task_type or not task_info:
            return jsonify({"code": 400, "msg": "task_type和task_info参数不能为空"}), 400
        
        # 验证task_type
        if task_type not in ['document_qa_mining', 'document_qa_segment_mining', 'chat_qa_mining', 'html_qa_segment_mining', 'excel_qa_segment_upload']:
            return jsonify({"code": 400, "msg": f"不支持的任务类型: {task_type}"}), 400
        
        # 验证task_info格式
        if task_type in ['document_qa_mining', 'document_qa_segment_mining', 'excel_qa_segment_upload']:
            if 'files' not in task_info or 'index_name' not in task_info:
                return jsonify({"code": 400, "msg": f"{task_type}类型需要files和index_name参数"}), 400
        elif task_type == 'chat_qa_mining':
            required_fields = ['client', 'user', 'app_id', 'start_time', 'end_time']
            missing_fields = [field for field in required_fields if field not in task_info]
            if missing_fields:
                return jsonify({"code": 400, "msg": f"chat_qa_mining类型需要以下参数: {', '.join(missing_fields)}"}), 400
        
        # 生成task_id
        task_id = generate_task_id(task_type, task_info)
        
        # 检查任务是否已存在
        existing_task = get_task_info(task_id)
        if existing_task:
            return jsonify({
                "code": 409, 
                "msg": "任务已存在", 
                "data": {"task_id": task_id}
            }), 409
        
        # 插入任务记录
        if not insert_task_record(task_id, task_type, task_info):
            return jsonify({"code": 500, "msg": "创建任务记录失败"}), 500
        
        # 将任务添加到队列中
        add_task_to_queue(task_id, task_type, task_info)
        
        return jsonify({
            "code": 0, 
            "msg": "任务已加入队列", 
            "data": {
                "task_id": task_id,
                "queue_size": task_queue.qsize(),
                "current_resource_usage": current_resource_usage,
                "max_concurrency": max_total_concurrency
            }
        })
    
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"启动任务时出错: {e}")
        logging.error(f"错误堆栈: {tb}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500

@app.route('/task_info', methods=['GET', 'POST'])
def query_task_info():
    """查询任务信息API - 支持GET和POST请求"""
    try:
        # 根据请求方法获取参数
        if request.method == 'GET':
            task_id = request.args.get('task_id')
        else:  # POST请求
            data = request.get_json()
            if not data:
                return jsonify({"code": 400, "msg": "POST请求参数不能为空"}), 400
            task_id = data.get('task_id')
        
        if not task_id:
            return jsonify({"code": 400, "msg": "task_id参数不能为空"}), 400
        
        # 查询任务信息
        task_info = get_task_info(task_id)
        if task_info is None:
            return jsonify({"code": 404, "msg": "任务不存在"}), 404
        
        return jsonify({
            "code": 0, 
            "msg": "查询成功", 
            "data": task_info
        })
    
    except Exception as e:
        logging.error(f"查询任务信息时出错: {e}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500

@app.route('/stop_task', methods=['POST'])
def stop_task():
    """停止任务API"""
    try:
        # force=True允许不同Content-Type，silent=True在解析失败时返回None而不抛出异常
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空或JSON格式错误"}), 400
        
        task_id = data.get('task_id')
        if not task_id:
            return jsonify({"code": 400, "msg": "task_id参数不能为空"}), 400
        
        # 检查任务是否存在
        if task_id not in task_pid_mapping:
            return jsonify({"code": 404, "msg": "任务不存在或未在运行"}), 404
        
        pid = task_pid_mapping[task_id]
        
        try:
            # 检查进程是否存在
            if psutil.pid_exists(pid):
                process = psutil.Process(pid)
                
                # 首先尝试优雅停止
                process.terminate()
                
                # 等待3秒，如果进程仍然存在则强制杀死
                try:
                    process.wait(timeout=3)
                except psutil.TimeoutExpired:
                    process.kill()
                    logging.warning(f"任务 {task_id} (PID: {pid}) 强制终止")
                
                # 从映射中移除
                task_pid_mapping.pop(task_id, None)
                
                # 释放资源
                release_task_resources(task_id)
                
                # 更新数据库状态（状态编码：1-异常）
                update_task_status(task_id, 1, "手动停止")
                
                logging.info(f"任务 {task_id} (PID: {pid}) 已停止")
                return jsonify({
                    "code": 0,
                    "msg": "任务停止成功",
                    "data": {"task_id": task_id}
                })
            else:
                # 进程不存在，清理映射
                task_pid_mapping.pop(task_id, None)
                return jsonify({"code": 404, "msg": "进程不存在"}), 404
                
        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            # 进程已经结束或无权限
            task_pid_mapping.pop(task_id, None)
            return jsonify({"code": 404, "msg": f"无法访问进程: {str(e)}"}), 404
    
    except Exception as e:
        logging.error(f"停止任务时出错: {e}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500

@app.route('/restart_task', methods=['POST'])
def restart_task():
    """重启任务API"""
    try:
        # 获取请求参数
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空或JSON格式错误"}), 400
        
        task_id = data.get('task_id')
        if not task_id:
            return jsonify({"code": 400, "msg": "task_id参数不能为空"}), 400
        
        logging.info(f"开始重启任务: {task_id}")
        
        # 1. 从数据库获取任务完整信息
        task_full_info = get_task_full_info(task_id)
        if task_full_info is None:
            return jsonify({"code": 404, "msg": "任务不存在"}), 404
        
        task_type = task_full_info.get('task_type')
        task_info = task_full_info.get('task_info')
        
        if not task_type or not task_info:
            return jsonify({"code": 400, "msg": "任务信息不完整，缺少task_type或task_info"}), 400
        
        logging.info(f"任务信息获取成功: task_type={task_type}")
        
        # 检查任务是否正在运行
        if task_id in task_pid_mapping:
            pid = task_pid_mapping[task_id]
            if psutil.pid_exists(pid):
                return jsonify({
                    "code": 409, 
                    "msg": "任务正在运行中，无法重启。请先停止任务。",
                    "data": {"task_id": task_id, "pid": pid}
                }), 409
            else:
                # 进程不存在但在映射中，清理映射
                task_pid_mapping.pop(task_id, None)
                release_task_resources(task_id)
        
        # 2. 重置任务状态
        if not reset_task_status(task_id):
            return jsonify({"code": 500, "msg": "重置任务状态失败"}), 500
        
        logging.info(f"任务状态重置成功: {task_id}")
        
        # 3. 将任务加入队列
        add_task_to_queue(task_id, task_type, task_info)
        
        logging.info(f"任务已重新加入队列: {task_id}")
        
        return jsonify({
            "code": 0,
            "msg": "任务重启成功，已加入队列",
            "data": {
                "task_id": task_id,
                "task_type": task_type,
                "queue_size": task_queue.qsize(),
                "current_resource_usage": current_resource_usage,
                "max_concurrency": max_total_concurrency
            }
        })
    
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"重启任务时出错: {e}")
        logging.error(f"错误堆栈: {tb}")
        return jsonify({"code": 500, "msg": f"内部服务器错误: {str(e)}"}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """健康检查API"""
    return jsonify({
        "code": 0,
        "msg": "服务正常",
        "data": {
            "timestamp": datetime.now().isoformat(),
            "active_tasks": len(task_pid_mapping),
            "queue_size": task_queue.qsize(),
            "current_resource_usage": current_resource_usage,
            "max_concurrency": max_total_concurrency,
            "resource_utilization": f"{(current_resource_usage / max_total_concurrency * 100):.1f}%" if max_total_concurrency > 0 else "0%"
        }
    })

@app.route('/task_access', methods=['POST'])
def task_access():
    """任务成本评估API"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空"}), 400
        
        task_type = data.get('task_type')
        task_info = data.get('task_info')
        
        if not task_type or not task_info:
            return jsonify({"code": 400, "msg": "task_type和task_info参数不能为空"}), 400
        
        # 目前只实现document_qa_segment_mining的估算
        if task_type == 'document_qa_segment_mining':
            # 验证task_info中是否包含files参数
            if 'files' not in task_info:
                return jsonify({"code": 400, "msg": "task_info中缺少files参数"}), 400
            
            files = task_info.get('files', [])
            if not isinstance(files, list):
                return jsonify({"code": 400, "msg": "files参数必须是列表类型"}), 400
            
            if len(files) == 0:
                return jsonify({"code": 400, "msg": "files列表不能为空"}), 400
            
            # 获取图片大小阈值（可选参数，默认1KB）
            image_size_limit = task_info.get('image_size_limit', 1024)
            
            logging.info(f"开始评估任务成本: task_type={task_type}, 文件数量={len(files)}")
            
            # 调用文档成本评估函数
            try:
                result = asscess_document_clear_price(files, image_size_limit)
                
                logging.info(f"任务成本评估完成: 总积分={result['total_credits']:.2f}, "
                           f"总字符数={result['total_chars']}, 总Token数={result['total_tokens']}, "
                           f"总图片数={result['total_images']}")
                
                return jsonify({
                    "code": 0,
                    "msg": "评估成功",
                    "data": {
                        "task_type": task_type,
                        "total_credits": round(result['total_credits'], 2),
                        "total_chars": result['total_chars'],
                        "total_tokens": result['total_tokens'],
                        "total_images": result['total_images'],
                        "detail_info": result['detail_info'],
                        "error_files": result['error_files'],
                        "success_count": len(result['detail_info']),
                        "error_count": len(result['error_files'])
                    }
                })
                
            except Exception as e:
                tb = traceback.format_exc()
                logging.error(f"评估任务成本时出错: {e}")
                logging.error(f"错误堆栈: {tb}")
                return jsonify({
                    "code": 500, 
                    "msg": f"评估失败: {str(e)}"
                }), 500
        
        else:
            # 其他任务类型暂不支持
            return jsonify({
                "code": 400, 
                "msg": f"暂不支持评估的任务类型: {task_type}，目前只支持document_qa_segment_mining"
            }), 400
    
    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"处理task_access请求时出错: {e}")
        logging.error(f"错误堆栈: {tb}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500

def start_monitoring():
    """启动监控线程"""
    global monitoring_thread
    if monitoring_thread is None or not monitoring_thread.is_alive():
        monitoring_thread = threading.Thread(target=monitor_tasks, daemon=True)
        monitoring_thread.start()
        logging.info("任务监控线程启动成功")

def stop_monitoring():
    """停止监控线程"""
    global should_monitor
    should_monitor = False
    logging.info("任务监控线程停止")

def parse_args():
    """解析命令行参数"""
    import argparse
    parser = argparse.ArgumentParser(description='任务控制服务')
    parser.add_argument('--script-dir', 
                       help='脚本基础目录路径（不指定则使用服务脚本所在目录的上级目录）',
                       default=None)
    parser.add_argument('--port', 
                       type=int,
                       help='服务端口号',  
                       default=6000)
    parser.add_argument('--host',
                       help='服务监听地址',
                       default='0.0.0.0')
    parser.add_argument('--resource-config',
                       help='任务资源配置文件路径',
                       default=None)
    parser.add_argument('--max-concurrency',
                       type=int,
                       help='最大并发数',
                       default=10)
    return parser.parse_args()

if __name__ == '__main__':
    # 解析命令行参数
    args = parse_args()
    
    # 初始化脚本基础目录
    init_script_base_dir(args.script_dir)
    
    # 设置最大并发数
    if args.max_concurrency:
        max_total_concurrency = args.max_concurrency
    
    # 加载任务资源配置
    load_task_resource_config(args.resource_config)
    
    # 初始化MySQL连接
    init_mysql_connector()
    
    # 启动任务工作线程
    start_task_worker()
    
    # 启动监控线程
    start_monitoring()
    
    try:
        logging.info(f"启动任务控制服务，监听地址: {args.host}:{args.port}")
        logging.info(f"最大并发数: {max_total_concurrency}")
        logging.info(f"任务资源占用配置: {task_resource_usage}")
        # 启动Flask应用
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
    except KeyboardInterrupt:
        logging.info("接收到中断信号，正在关闭服务...")
        stop_task_worker()
        stop_monitoring()
    except Exception as e:
        logging.error(f"启动服务时出错: {e}")
        stop_task_worker()
        stop_monitoring() 