#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
批量运行聊天QA挖掘请求脚本
通过API请求的方式批量启动聊天QA挖掘任务

任务状态定义：
- 1: 异常
- 2: 运行中
- 3: 完成
- 4: 等待
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('control_script/batch_run_chatqa_request.py')
import sys
import os
import json
import time
import logging
import requests
from datetime import datetime, timedelta

# 添加项目根目录到sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__legacy_source_file__))))
from commons.mysql_connector import MySQLConnector

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(asctime)s] [%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
)

class BatchChatQARequestRunner:
    """批量聊天QA请求运行器"""

    def __init__(self, appid_record_file, mysql_config_file, start_time, end_time, flag):
        self.appid_record_file = appid_record_file
        self.mysql_config_file = mysql_config_file
        self.start_time = start_time
        self.end_time = end_time
        self.flag = flag
        
        # 初始化MySQL连接
        self.mysql_connector = MySQLConnector(mysql_config_file)
        
        # API服务地址（假设在本地运行）
        self.api_base_url = "http://localhost:6000"
        
        # 任务状态跟踪
        self.running_tasks = {}
        self.status_request_timeout_seconds = self._positive_int_env(
            'CHAT_QA_STATUS_REQUEST_TIMEOUT_SECONDS', 10
        )
        self.poll_interval_seconds = self._positive_int_env(
            'CHAT_QA_POLL_INTERVAL_SECONDS', 10
        )
        self.poll_timeout_seconds = self._positive_int_env(
            'CHAT_QA_POLL_TIMEOUT_SECONDS', 6 * 60 * 60
        )

    @staticmethod
    def _positive_int_env(name, default):
        raw_value = os.environ.get(name, default)
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            logging.warning("%s=%r 非法，使用默认值 %s", name, raw_value, default)
            return default
        if value <= 0:
            logging.warning("%s=%r 必须大于 0，使用默认值 %s", name, raw_value, default)
            return default
        return value
        
    def load_appid_records(self):
        """加载appid记录文件，读取每个appid的最新时间"""
        appid_records = {}
        
        if os.path.exists(self.appid_record_file):
            try:
                with open(self.appid_record_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if line and '\t' in line:
                            parts = line.split('\t')
                            if len(parts) >= 2:
                                app_id = parts[0]
                                last_run_time = parts[1]
                                # 如果同一个app_id有多次记录，保留最新的时间
                                if app_id not in appid_records or last_run_time > appid_records[app_id]:
                                    appid_records[app_id] = last_run_time
                
                logging.info(f"加载了 {len(appid_records)} 个appid的最新记录")
            except Exception as e:
                logging.error(f"加载appid记录文件失败: {e}")
        else:
            logging.warning(f"appid记录文件不存在: {self.appid_record_file}")
        
        return appid_records

    # get_data_from_sql.py 只识别 group/single 两个场景词。非法值不能静默放大为
    # 群聊和单聊全量挖掘，因此统一回退到历史默认 group。
    VALID_SCENE_TYPES = {'group', 'single', 'group,single'}

    def _normalize_scene_type(self, scene_type, app_id):
        if not scene_type:
            return 'group'

        parts = [part.strip().lower() for part in str(scene_type).split(',') if part.strip()]
        normalized = ','.join(scene for scene in ('group', 'single') if scene in parts)
        if normalized not in self.VALID_SCENE_TYPES:
            logging.warning(
                "appid %s 的 chat_mining_scene_type 取值非法: %r，退回 group",
                app_id,
                scene_type
            )
            return 'group'
        return normalized

    def get_enabled_appids(self):
        """从数据库获取启用的appid列表"""
        connection = self.mysql_connector.get_connection()
        if connection is None:
            logging.error("无法连接到数据库")
            return []
        
        try:
            cursor = connection.cursor()
            # chat QA 定时开关和应用在线服务开关是两个独立控制面。
            # 默认仍要求应用启用；只有显式配置 chat_mining_allow_disabled_app=1 的
            # 账号，才允许在 rf_app_info.is_enabled=0 时继续执行知识抽取。
            sql = """
            SELECT DISTINCT
                rc.app_id,
                ai.customer as client,
                ai.application_name as user,
                (SELECT sc.config_value
                 FROM rufitai.rf_ai_role_config sc
                 WHERE sc.app_id = rc.app_id
                 AND sc.config_key = 'chat_mining_scene_type'
                 AND IFNULL(sc.is_enabled, 1) = 1
                 AND IFNULL(sc.del_flag, 0) != 1
                 ORDER BY sc.id DESC LIMIT 1) as scene_type
            FROM rufitai.rf_ai_role_config rc
            INNER JOIN rufitai.rf_app_info ai ON rc.app_id = ai.id
            WHERE rc.config_key = 'timing_run_chat_mining'
            AND rc.config_value = '1'
            AND IFNULL(rc.is_enabled, 1) = 1
            AND IFNULL(rc.del_flag, 0) != 1
            AND rc.app_id IS NOT NULL
            AND (
                IFNULL(ai.is_enabled, 1) = 1
                OR EXISTS (
                    SELECT 1
                    FROM rufitai.rf_ai_role_config allow_disabled
                    WHERE allow_disabled.app_id = rc.app_id
                    AND allow_disabled.client = ai.customer
                    AND allow_disabled.config_key = 'chat_mining_allow_disabled_app'
                    AND allow_disabled.config_value = '1'
                    AND IFNULL(allow_disabled.is_enabled, 1) = 1
                    AND IFNULL(allow_disabled.del_flag, 0) != 1
                )
            )
            AND IFNULL(ai.del_flag, 0) != 1
            """

            cursor.execute(sql)
            results = cursor.fetchall()

            appid_list = []
            for row in results:
                app_id, client, user, scene_type = row
                if not client or not user:
                    logging.error(
                        "跳过缺少客户归属的 appid: app_id=%s client=%r user=%r",
                        app_id,
                        client,
                        user
                    )
                    continue
                appid_list.append({
                    'app_id': str(app_id),
                    'client': client,
                    'user': user,
                    'scene_type': self._normalize_scene_type(scene_type, app_id)
                })
            
            logging.info(f"从数据库获取到 {len(appid_list)} 个启用的appid")
            return appid_list
            
        except Exception as e:
            logging.error(f"查询启用的appid失败: {e}")
            return []
        finally:
            self.mysql_connector.close_connection(connection, cursor)
    
    def get_default_start_time(self):
        """获取默认开始时间（一个月前）"""
        try:
            # 将start_time转换为datetime对象
            start_dt = datetime.strptime(self.start_time, "%Y%m%d%H%M%S")
            return start_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            # 如果解析失败，使用一个月前的时间
            one_month_ago = datetime.now() - timedelta(days=30)
            return one_month_ago.strftime("%Y-%m-%d %H:%M:%S")
    
    def get_end_time_formatted(self):
        """获取格式化的结束时间"""
        try:
            # 将end_time转换为datetime对象
            end_dt = datetime.strptime(self.end_time, "%Y%m%d%H%M%S")
            return end_dt.strftime("%Y-%m-%d %H:%M:%S")
        except:
            # 如果解析失败，使用当前时间
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    def create_task_request(self, app_info, appid_records):
        """创建任务请求"""
        app_id = app_info['app_id']
        client = app_info['client']
        user = app_info['user']
        
        # 获取该appid的最后运行时间
        last_run_time = appid_records.get(app_id, self.get_default_start_time())
        
        # 构造请求数据
        task_info = {
            "client": client,
            "user": user,  # 使用application_name作为user
            "index": client,  # 使用client作为index
            "app_id": app_id,
            "start_time": last_run_time,
            "end_time": self.get_end_time_formatted(),
            "black_nick_name": "",  # 可选
            "need_process_name": "all",  # 可选，默认为all
            "mining_type": "normal",  # 可选，默认为norm
            "scene_type": app_info.get('scene_type', 'group')
        }
        
        return task_info
    
    def send_task_request(self, task_info):
        """发送任务请求"""
        try:
            url = f"{self.api_base_url}/start_task"
            payload = {
                "task_type": "chat_qa_mining",
                "task_info": task_info
            }
            
            logging.info(f"发送任务请求: {json.dumps(payload, ensure_ascii=False)}")
            
            response = requests.post(url, json=payload, timeout=90)
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') == 0:
                task_id = result.get('data', {}).get('task_id')
                logging.info(f"任务启动成功，task_id: {task_id}")
                return task_id
            else:
                logging.error(f"任务启动失败: {result.get('msg', '未知错误')}")
                return None
                
        except requests.exceptions.RequestException as e:
            logging.error(f"发送请求失败: {e}")
            return None
        except Exception as e:
            logging.error(f"发送任务请求时发生异常: {e}")
            return None
    
    def check_task_status(self, task_id):
        """检查任务状态"""
        try:
            url = f"{self.api_base_url}/task_info"
            params = {"task_id": task_id}
            
            response = requests.get(
                url,
                params=params,
                timeout=getattr(self, 'status_request_timeout_seconds', 10)
            )
            response.raise_for_status()
            
            result = response.json()
            if result.get('code') == 0:
                task_info = result.get('data', {})
                return task_info.get('run_status'), task_info.get('task_stage')
            else:
                logging.error(f"查询任务状态失败: {result.get('msg', '未知错误')}")
                return None, None
                
        except requests.exceptions.RequestException as e:
            logging.error(f"查询任务状态失败: {e}")
            return None, None
        except Exception as e:
            logging.error(f"查询任务状态时发生异常: {e}")
            return None, None
    
    def wait_for_tasks_completion(self):
        """等待所有任务完成"""
        logging.info(f"等待 {len(self.running_tasks)} 个任务完成...")
        final_statuses = {}
        started_at = time.monotonic()
        poll_timeout_seconds = getattr(self, 'poll_timeout_seconds', 6 * 60 * 60)
        poll_interval_seconds = getattr(self, 'poll_interval_seconds', 10)
        
        while self.running_tasks:
            elapsed_seconds = time.monotonic() - started_at
            if elapsed_seconds >= poll_timeout_seconds:
                timed_out_task_ids = sorted(self.running_tasks)
                logging.error(
                    "任务状态轮询超过总时限 %s 秒，按失败处理: %s",
                    poll_timeout_seconds,
                    timed_out_task_ids
                )
                for task_id in timed_out_task_ids:
                    final_statuses[task_id] = 1
                self.running_tasks.clear()
                break

            completed_tasks = []
            
            for task_id, task_info in self.running_tasks.items():
                run_status, task_stage = self.check_task_status(task_id)
                
                if run_status is not None:
                    if run_status == 3:  # 完成
                        logging.info(f"任务 {task_id} 完成")
                        final_statuses[task_id] = run_status
                        completed_tasks.append(task_id)
                    elif run_status in (1, -1):  # 异常
                        logging.error(f"任务 {task_id} 失败")
                        final_statuses[task_id] = run_status
                        completed_tasks.append(task_id)
                    else:
                        # 任务仍在运行中(2)或等待中(4)
                        logging.info(f"任务 {task_id} 状态: {run_status}, 阶段: {task_stage}")
            
            # 移除已完成的任务
            for task_id in completed_tasks:
                del self.running_tasks[task_id]
            
            if self.running_tasks:
                remaining_seconds = max(
                    0,
                    poll_timeout_seconds - (time.monotonic() - started_at)
                )
                sleep_seconds = min(poll_interval_seconds, remaining_seconds)
                logging.info(
                    "还有 %s 个任务在运行，等待 %s 秒...",
                    len(self.running_tasks),
                    sleep_seconds
                )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
        
        logging.info("所有任务已完成")
        return final_statuses
    
    def update_appid_records(self, appid_records):
        """追加appid记录到文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.appid_record_file), exist_ok=True)
            
            # 追加新记录到文件
            with open(self.appid_record_file, 'a', encoding='utf-8') as f:
                for app_id, last_run_time in appid_records.items():
                    f.write(f"{app_id}\t{last_run_time}\n")
            
            logging.info(f"追加了 {len(appid_records)} 个appid记录到文件: {self.appid_record_file}")
            
        except Exception as e:
            logging.error(f"追加appid记录文件失败: {e}")
            raise
    
    def run(self):
        """运行批量任务"""
        logging.info("开始批量运行聊天QA挖掘任务")
        
        # 1. 加载appid记录
        appid_records = self.load_appid_records()
        
        # 2. 获取启用的appid列表
        enabled_appids = self.get_enabled_appids()
        if not enabled_appids:
            raise RuntimeError("启用 App 查询结果为空，拒绝按成功结束批任务")
        
        # 3. 为每个appid创建并发送任务请求
        launch_failed_appids = []
        
        for app_info in enabled_appids:
            app_id = app_info['app_id']
            client = app_info['client']
            
            logging.info(f"处理appid: {app_id}, client: {client}")
            
            # 创建任务请求
            task_info = self.create_task_request(app_info, appid_records)
            
            # 发送任务请求
            task_id = self.send_task_request(task_info)
            
            if task_id:
                # 记录运行中的任务
                self.running_tasks[task_id] = {
                    'app_id': app_id,
                    'client': client,
                    'task_info': task_info
                }
                
            else:
                logging.error(f"appid {app_id} 任务启动失败")
                launch_failed_appids.append(app_id)
        
        # 4. 等待所有任务完成
        if self.running_tasks:
            launched_tasks = dict(self.running_tasks)
            final_statuses = self.wait_for_tasks_completion()
        else:
            raise RuntimeError("没有成功启动任何任务")

        # 5. 只为最终完成的任务推进 App 水位；失败任务保留原水位以便下轮重试。
        completed_records = {}
        failed_task_ids = []
        for task_id, run_status in final_statuses.items():
            task_meta = launched_tasks.get(task_id)
            if task_meta is None:
                continue
            if run_status == 3:
                completed_records[task_meta['app_id']] = task_meta['task_info']['end_time']
            else:
                failed_task_ids.append(task_id)
        if completed_records:
            self.update_appid_records(completed_records)

        if launch_failed_appids or failed_task_ids:
            raise RuntimeError(
                f"批量任务未全部成功：启动失败 App {launch_failed_appids}；运行失败任务 {failed_task_ids}"
            )
        
        logging.info("批量运行聊天QA挖掘任务完成")

def main():
    """主函数"""
    if len(sys.argv) != 6:
        print("用法: python batch_run_chatqa_request.py <appid_record_file> <mysql_config_file> <start_time> <end_time> <flag>")
        print("示例: python batch_run_chatqa_request.py data/chatknowledge/appid_record.txt config/mysql_conn_config.json 20250101000000 20250101235959 timing_v1_20250101")
        sys.exit(1)
    
    appid_record_file = sys.argv[1]
    mysql_config_file = sys.argv[2]
    start_time = sys.argv[3]
    end_time = sys.argv[4]
    flag = sys.argv[5]
    
    try:
        runner = BatchChatQARequestRunner(
            appid_record_file=appid_record_file,
            mysql_config_file=mysql_config_file,
            start_time=start_time,
            end_time=end_time,
            flag=flag
        )
        
        runner.run()
        
    except Exception as e:
        logging.error(f"运行批量任务时发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
