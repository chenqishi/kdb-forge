#!/usr/bin/env python
# -*- coding:utf8 -*-
################################################################################
#
# Copyright (c) 2024 qishichen, Inc. All Rights Reserved
#
################################################################################
"""
Authors: qishichen(263436967@qq.com)
Date: 2024-11-17
"""
import string
import sys
import os
import re
import json
import time
import math
import logging
import copy
import traceback
import codecs
from datetime import datetime
from datetime import timedelta
import paramiko
from typing import Optional
import shutil
import socket

from commons.file_utils import get_index_file_name

def is_local_host(host: str) -> bool:
    """
    判断给定的主机名或IP是否为本地主机
    
    Args:
        host: 主机名或IP地址
    
    Returns:
        bool: 如果是本地主机返回True，否则返回False
    """
    try:
        # 获取本机所有IP
        local_ips = set()
        # 添加常用的本地地址
        local_ips.add('localhost')
        local_ips.add('127.0.0.1')
        
        # 获取本机主机名
        hostname = socket.gethostname()
        local_ips.add(hostname)
        
        # 获取本机IP地址
        local_ips.add(socket.gethostbyname(hostname))
        
        # 尝试获取所有网络接口的IP
        for ip in socket.gethostbyname_ex(hostname)[2]:
            local_ips.add(ip)
            
        return host.lower() in local_ips
    except Exception:
        return False

def fetch_remote_file(
    remote_host: str,
    remote_path: str, 
    local_path: str,
    username: str = "",
    password: str = "",
    port: int = 22
) -> bool:
    """
    从远程服务器或本地拉取文件
    
    Args:
        remote_host: 远程主机IP或域名，如果是本地主机可以是实际IP、主机名、localhost等
        remote_path: 远程/源文件路径
        local_path: 本地存储路径
        username: SSH用户名（远程传输时需要）
        password: SSH密码（远程传输时需要）
        port: SSH端口号,默认22（远程传输时需要）
    
    Returns:
        bool: 成功返回True,失败返回False
    """
    logging.info(f"从远程主机{remote_host}下载文件: {remote_path} -> {local_path}, username: {username}, password: {password}, port: {port}")
    try:
        # 判断是否为本地文件
        if is_local_host(remote_host):
            # 确保源文件存在
            if not os.path.exists(remote_path):
                raise FileNotFoundError(f"源文件不存在: {remote_path}")
                
            # 创建目标文件夹（如果不存在）
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 使用shutil复制文件
            shutil.copy2(remote_path, local_path)
            logging.info(f"本地文件复制成功: {remote_path} -> {local_path}")
            return True
            
        # 远程文件处理
        ssh = None
        sftp = None
        try:
            ssh = paramiko.SSHClient()
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # 连接远程服务器
            ssh.connect(
                hostname=remote_host,
                port=port,
                username=username,
                password=password
            )
            
            # 创建SFTP客户端
            sftp = ssh.open_sftp()
            
            # 创建目标文件夹（如果不存在）
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            # 下载文件
            sftp.get(remote_path, local_path)
            
            logging.info(f"远程文件下载成功: {remote_host}:{remote_path} -> {local_path}")
            return True
            
        except Exception as e:
            logging.error(f"文件传输失败: {str(e)}")
            logging.error(traceback.format_exc())
            return False
        
        finally:
            # 确保连接被关闭
            if sftp:
                sftp.close()
            if ssh:
                ssh.close()
        
    except Exception as e:
        logging.error(f"文件传输失败: {str(e)}")
        logging.error(traceback.format_exc())
        return False


def run_batch_download_files(
    batch_file_path: str,
    output_file_path: str,
    save_data_dir: str,
    remote_field_num: int = 2,
    username: str = "",
    password: str = "",
    port: int = 22
) -> bool:
    """
    批量下载远程文件
    """
    with open(batch_file_path, 'r') as f, open(output_file_path, 'w') as output_f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            fields = line.split('\t')
            if len(fields) < remote_field_num:
                logging.error(f"行数据不完整: {line}")
                continue
            remote_host_path = fields[remote_field_num]
            remote_host, remote_path = remote_host_path.split(':')
            file_name = remote_path.split('/')[-1]
            local_path = os.path.join(save_data_dir, file_name)
            is_download = fetch_remote_file(remote_host, remote_path, local_path, username, password, port)
            if is_download:
                fields.append(local_path)
                output_f.write('\t'.join(fields) + '\n')
            else:
                logging.error(f"文件下载失败: {remote_host_path}")

            
def download_file_from_remote_machine(
    remote_file_path: str,
    local_file_path: str,
    username: str = "",
    password: str = "",
    port: int = 22
) -> bool:
    """
    从远程机器下载文件
    """
    try:
        # 判断是否为本地文件
        if is_local_host(remote_file_path):
            shutil.copy2(remote_file_path, local_file_path)
            return True
        else:
            remote_host, remote_path = remote_file_path.split(':')
            return fetch_remote_file(remote_host, remote_path, local_file_path, username, password, port)
    except Exception as e:
        logging.error(f"文件下载失败: {remote_file_path}")
        logging.error(traceback.format_exc())
        return False
def process_file_message(
    input_file_path: str,
    output_file_path: str,
    save_image_dir: str,
    remote_host: str,
    username: str = "",
    password: str = "",
    port: int = 22,
    remote_path_root_dir: str = '/root/dify/dify-on-wechat'
) -> bool:
    """
    处理消息文件，下载图片并更新内容
    
    Args:
        input_file_path: 输入文件路径
        output_file_path: 输出文件路径
        save_image_dir: 图片保存目录
        remote_host: 远程主机
        username: SSH用户名
        password: SSH密码
        port: SSH端口号
    
    Returns:
        bool: 处理成功返回True，否则返回False
    """
    try:
        os.makedirs(save_image_dir, exist_ok=True)
        
        with open(input_file_path, 'r', encoding='utf-8') as f_in, \
             open(output_file_path, 'w', encoding='utf-8') as f_out:
            
            for line in f_in:
                line = line.strip()
                if not line:
                    continue
                    
                fields = line.split('\t')
                if len(fields) != 3:
                    logging.warning(f"无效的行格式: {line}")
                    continue
                    
                sender, timestamp, message = fields
                
                try:
                    message_dict = json.loads(message)
                    original_info = message_dict.get('original_info', {})
                    
                    # 处理图片类型消息
                    if original_info.get('ctype') == 'IMAGE':
                        remote_image_path = original_info.get('content', '')
                        if not remote_image_path.startswith('/'):
                            remote_image_path = os.path.join(remote_path_root_dir, remote_image_path)
                        if remote_image_path:
                            # 生成本地图片路径
                            image_name = os.path.basename(remote_image_path)
                            local_image_path = os.path.join(save_image_dir, image_name)
                            
                            # 下载图片
                            if fetch_remote_file(
                                remote_host,
                                remote_image_path,
                                local_image_path,
                                username,
                                password,
                                port
                            ):
                                # 更新消���中的图片路径
                                message_dict['conent'] = local_image_path
                                original_info['content'] = local_image_path
                                message_dict['is_image_download'] = True
                                message = json.dumps(message_dict, ensure_ascii=False)
                            else:
                                logging.error(f"图片下载失败: {remote_image_path}")
                                
                    # 写入处理后的行
                    f_out.write(f"{sender}\t{timestamp}\t{message}\n")
                    
                except json.JSONDecodeError:
                    logging.error(f"JSON解析失败: {message}")
                    continue
                except Exception as e:
                    logging.error(f"处理消息失败: {str(e)}")
                    continue
                    
        return True
        
    except Exception as e:
        logging.error(f"文件处理失败: {str(e)}")
        logging.error(traceback.format_exc())
        return False

def run_batch_process_message(
    input_file_path: str,
    output_file_path: str,
    save_image_dir: str,
    remote_field_num: int = 2,
    local_field_num: int = 3,
    username: str = "",
    password: str = "",
    port: int = 22
) -> bool:
    """
    批量处理消息文件
    
    Args:
        input_file_path: 输入文件路径（run_batch_download_files的输出文件）
        output_file_path: 输出文件路径
        save_image_dir: 图片保存目录
        remote_field_num: 远程路径字段位置
        local_field_num: 本地路径字段位置
        username: SSH用户名
        password: SSH密码
        port: SSH端口号
    
    Returns:
        bool: 处理成功返回True，否则返回False
    """
    try:
        # 处理下载的每个文件
        with open(input_file_path, 'r') as f, open(output_file_path, 'w') as output_f:
            for line in f:
                fields = line.strip().split('\t')
                if len(fields) < remote_field_num:  # +2是因为包含了本地路径
                    continue
                    
                remote_host_path = fields[remote_field_num]
                remote_host = remote_host_path.split(':')[0]
                local_file_path = fields[local_field_num]
                
                # 生成处理后的文件路径
                ext = local_file_path.split('.')[-1]
                processed_file_path = local_file_path.replace(f'.{ext}', f'.processed.{ext}')
                
                # 处理文件
                if process_file_message(
                    local_file_path,
                    processed_file_path,
                    save_image_dir,
                    remote_host,
                    username,
                    password,
                    port
                ):
                    # 更新输出行，使用处理后的文件路径
                    fields[-1] = processed_file_path
                    output_f.write('\t'.join(fields) + '\n')
                else:
                    logging.error(f"文件处理失败: {local_file_path}")
        
        return True
        
    except Exception as e:
        logging.error(f"批处理失败: {str(e)}")
        logging.error(traceback.format_exc())
        return False

if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format=
            '''[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '''
            '''[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s''')  
    import fire
    fire.Fire({
        'run_batch_download_files': run_batch_download_files,
        'run_batch_process_message': run_batch_process_message,
        'download_file_from_remote_machine': download_file_from_remote_machine,
    })
    