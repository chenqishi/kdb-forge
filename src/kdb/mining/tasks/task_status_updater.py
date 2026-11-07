from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
任务状态更新工具
"""
import os
import sys
import logging
from datetime import datetime

# 添加项目根目录到sys.path
project_root = str(_PROJECT_ROOT)

from kdb.shared.clients.mysql_connector import MySQLConnector
from mysql.connector import Error

class TaskStatusUpdater:
    """任务状态更新器"""
    
    def __init__(self, config_path):
        """初始化更新器"""
        self.mysql_connector = MySQLConnector(config_path)
        
    def update_task_stage(self, task_id, task_stage):
        """更新任务阶段"""
        return self._update_task_status(task_id, task_stage=task_stage)
        
    def update_task_run_status(self, task_id, run_status, task_stage=None):
        """更新任务运行状态"""
        return self._update_task_status(task_id, run_status=run_status, task_stage=task_stage)
    
    def update_task_result(self, task_id, task_result):
        """更新任务结果"""
        return self._update_task_status(task_id, task_result=task_result)
    
    def update_predict_credits(self, task_id, predict_credits):
        """更新任务预测成本"""
        return self._update_task_status(task_id, predict_credits=predict_credits)
    
    def update_actual_credits(self, task_id, actual_credits):
        """更新任务实际成本"""
        return self._update_task_status(task_id, actual_credits=actual_credits)
        
    def _update_task_status(self, task_id, run_status=None, task_stage=None, task_result=None, predict_credits=None, actual_credits=None):
        """更新任务状态"""
        connection = self.mysql_connector.get_connection()
        if connection is None:
            logging.error("无法获取数据库连接")
            return False
        
        try:
            cursor = connection.cursor()
            
            # 构建更新语句，每次更新都自动更新update_time
            update_fields = []
            values = []
            
            if run_status is not None:
                update_fields.append("run_status = %s")
                values.append(run_status)
                
            if task_stage is not None:
                update_fields.append("task_stage = %s")
                values.append(task_stage)
            
            if task_result is not None:
                update_fields.append("task_result = %s")
                values.append(task_result)
            
            if predict_credits is not None:
                update_fields.append("predict_credits = %s")
                values.append(predict_credits)
            
            if actual_credits is not None:
                update_fields.append("actual_credits = %s")
                values.append(actual_credits)
            
            if not update_fields:
                logging.warning("没有需要更新的字段")
                return True
            
            # 每次更新都自动更新update_time
            update_fields.append("update_time = %s")
            values.append(datetime.now())
                
            values.append(task_id)
            
            sql = f"""
            UPDATE rufitai.dops_task_kggen_info 
            SET {', '.join(update_fields)}
            WHERE task_id = %s
            """
            
            cursor.execute(sql, values)
            connection.commit()
            
            if run_status is not None and task_stage is not None:
                logging.info(f"任务状态更新成功: {task_id}, status: {run_status}, stage: {task_stage}")
            elif run_status is not None:
                logging.info(f"任务运行状态更新成功: {task_id}, status: {run_status}")
            elif task_result is not None:
                logging.info(f"任务结果更新成功: {task_id}, result: {task_result}")
            else:
                logging.info(f"任务阶段更新成功: {task_id}, stage: {task_stage}")
            
            return True
            
        except Error as e:
            logging.error(f"更新任务状态失败: {e}")
            connection.rollback()
            return False
        finally:
            self.mysql_connector.close_connection(connection, cursor)

def main():
    """测试函数"""
    import argparse
    parser = argparse.ArgumentParser(description='任务状态更新测试')
    parser.add_argument('--config', required=True, help='数据库配置文件路径')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--stage', help='任务阶段')
    parser.add_argument('--status', type=int, help='运行状态')
    args = parser.parse_args()
    
    updater = TaskStatusUpdater(args.config)
    
    if args.stage and args.status is not None:
        success = updater.update_task_run_status(args.task_id, args.status, args.stage)
    elif args.stage:
        success = updater.update_task_stage(args.task_id, args.stage)
    elif args.status is not None:
        success = updater.update_task_run_status(args.task_id, args.status)
    else:
        print("请指定--stage或--status参数")
        return
        
    print(f"更新{'成功' if success else '失败'}")

if __name__ == '__main__':
    main() 