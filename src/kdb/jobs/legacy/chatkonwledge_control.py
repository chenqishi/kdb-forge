import json
import time
import os
import subprocess
from datetime import datetime
import logging
import sys

def read_config(config_path):
    """读取配置文件"""
    with open(config_path, 'r') as f:
        return json.load(f)

def read_and_clear_control_file(control_file):
    """读取控制文件获取filter_group_name列表并清除内容"""
    try:
        with open(control_file, 'r') as f:
            # 读取所有非空行
            contents = [line.strip() for line in f.readlines() if line.strip()]
        
        # 如果文件有内容，则清除文件内容
        if contents:
            with open(control_file, 'w') as f:
                f.write('')
            
        return contents
    except FileNotFoundError:
        return []

def build_command(config, filter_group_name):
    """构建执行命令"""
    cmd = f"""sh -x control_script/chatknowledge_process.sh \
        {config['robot_remote_data']} \
        {config['room_type_config']} \
        {config['room_record']} \
        {config['room_white']} \
        {config['output_dir']} \
        {config['log_dir']} \
        {config['version']} \
        {config['api_key']} \
        {config['dataset_map_file']} \
        {config['white_name_map']} \
        {filter_group_name} \
        &>{config['log_dir']}/run_chatknowledge_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log """
    return cmd

def execute_command(cmd):
    """执行命令并记录输出"""
    try:
        # 使用Popen执行命令，并捕获输出
        process = subprocess.Popen(
            cmd, 
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # 记录进程ID
        logging.info(f"Started process with PID: {process.pid}")
        
        # 等待命令执行完成，设置超时时间
        try:
            stdout, stderr = process.communicate(timeout=3600)  # 1小时超时
            
            # 记录命令执行结果
            if process.returncode == 0:
                logging.info(f"Command completed successfully. PID: {process.pid}")
                logging.debug(f"Output: {stdout}")
            else:
                logging.error(f"Command failed with return code {process.returncode}. PID: {process.pid}")
                logging.error(f"Error output: {stderr}")
                
        except subprocess.TimeoutExpired:
            logging.warning(f"Command timed out after 1 hour. PID: {process.pid}")
            process.kill()
            stdout, stderr = process.communicate()
            
    except Exception as e:
        logging.error(f"Error executing command: {str(e)}")
        return False
    
    return process.returncode == 0

def start_chatknowledge_control(config_file):
    # 读取配置文件
    config = read_config(config_file)
    control_file = config['control_file']
    
    # 设置日志
    if not os.path.exists(config['log_dir']):
        os.makedirs(config['log_dir'])

    
    logging.info(f"开始监控控制文件: {control_file}")
    
    while True:
        current_contents = read_and_clear_control_file(control_file)
        
        # 处理每个filter_group_name
        for filter_group_name in current_contents:
            logging.info(f"检测到新的filter_group_name: {filter_group_name}")
            cmd = build_command(config, filter_group_name)
            logging.info(f"执行命令: {cmd}")
            
            # 为每个命令创建新的日志文件
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            log_file = f"{config['log_dir']}/run_chatknowledge_{filter_group_name}_{timestamp}.log"
            cmd = cmd.replace("run_chatknowledge.log", os.path.basename(log_file))
            
            # 执行命令并获取结果
            success = execute_command(cmd)
            if success:
                logging.info(f"命令执行成功: {filter_group_name}")
            else:
                logging.error(f"命令执行失败: {filter_group_name}")
            
        time.sleep(60)  # 每分钟检查一次

if __name__ == '__main__':
    
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')   
    import fire
    fire.Fire({
        'start_chatknowledge_control': start_chatknowledge_control,
    })    
