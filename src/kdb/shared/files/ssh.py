import logging
import os
import paramiko
import shutil
import socket
import traceback

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
