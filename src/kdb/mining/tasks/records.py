from datetime import datetime
from kdb.shared.database.mysql import MySQLConnector
from mysql.connector import Error
import json
import kdb.mining.tasks.state as runtime_state
import logging
import os

def init_mysql_connector():
    """初始化MySQL连接"""

    config_path = os.path.join(runtime_state.script_base_dir, 'config', 'mysql_conn_config.json')
    runtime_state.mysql_connector = MySQLConnector(config_path)
    logging.info("MySQL连接初始化完成")


def insert_task_record(task_id, task_type, task_info):
    """插入任务记录到数据库"""
    connection = runtime_state.mysql_connector.get_connection()
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
        runtime_state.mysql_connector.close_connection(connection, cursor)


def update_task_status(task_id, run_status, task_stage=None, pid=None):
    """更新任务状态"""
    connection = runtime_state.mysql_connector.get_connection()
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
        runtime_state.mysql_connector.close_connection(connection, cursor)


def get_task_info(task_id):
    """获取任务信息"""
    connection = runtime_state.mysql_connector.get_connection()
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
        runtime_state.mysql_connector.close_connection(connection, cursor)


def get_task_full_info(task_id):
    """获取任务完整信息（包括task_info）"""
    connection = runtime_state.mysql_connector.get_connection()
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
        runtime_state.mysql_connector.close_connection(connection, cursor)


def reset_task_status(task_id):
    """重置任务状态，准备重新启动"""
    connection = runtime_state.mysql_connector.get_connection()
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
        runtime_state.mysql_connector.close_connection(connection, cursor)
