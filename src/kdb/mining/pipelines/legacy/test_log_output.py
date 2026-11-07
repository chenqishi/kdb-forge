#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
测试日志输出功能
"""
import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime

def test_log_output():
    """测试日志输出功能"""
    
    # 创建临时日志目录
    temp_dir = tempfile.mkdtemp()
    log_dir = os.path.join(temp_dir, 'log', 'off_task')
    os.makedirs(log_dir, exist_ok=True)
    
    task_id = "test_task_123"
    task_log_file = os.path.join(log_dir, f'{task_id}.log')
    
    print(f"测试日志文件路径: {task_log_file}")
    
    # 模拟start_mining_task中的日志写入逻辑
    try:
        # 写入启动信息
        with open(task_log_file, 'w', encoding='utf-8') as log_file:
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: document_qa_mining\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()
            
            # 启动一个简单的测试进程
            cmd = [sys.executable, '-c', '''
import time
print("测试任务开始执行...")
print("正在处理文件...")
time.sleep(1)
print("任务执行完成!")
            ''']
            
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )
        
        # 等待进程完成
        returncode = process.wait()
        print(f"进程退出码: {returncode}")
        
        # 检查日志文件内容
        if os.path.exists(task_log_file):
            with open(task_log_file, 'r', encoding='utf-8') as f:
                content = f.read()
                print("=== 日志文件内容 ===")
                print(content)
                print("=== 日志文件内容结束 ===")
                
                # 验证关键内容
                if "任务启动信息" in content and "测试任务开始执行" in content:
                    print("✅ 日志输出功能正常工作！")
                    return True
                else:
                    print("❌ 日志内容不完整")
                    return False
        else:
            print("❌ 日志文件不存在")
            return False
            
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        return False
    finally:
        # 清理临时文件
        try:
            if os.path.exists(task_log_file):
                os.remove(task_log_file)
            os.rmdir(log_dir)
            os.rmdir(os.path.dirname(log_dir))
            os.rmdir(temp_dir)
        except:
            pass

if __name__ == '__main__':
    print("=== 测试任务日志输出功能 ===")
    success = test_log_output()
    if success:
        print("\n🎉 测试通过！日志输出功能工作正常。")
    else:
        print("\n⚠️ 测试失败，需要检查日志输出实现。") 