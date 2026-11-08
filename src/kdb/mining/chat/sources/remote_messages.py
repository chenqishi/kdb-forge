from kdb.shared.files.ssh import download_file_from_remote_machine
from kdb.shared.files.ssh import fetch_remote_file
from kdb.shared.files.ssh import run_batch_download_files
import json
import logging
import os
import sys
import traceback

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


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-11-17
"""


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
