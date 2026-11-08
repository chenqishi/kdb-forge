#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
MinIO文件下载工具
"""
import os
import json
import logging
import requests
from urllib.parse import urlparse
import boto3
from botocore.exceptions import ClientError

class MinioDownloader:
    """MinIO文件下载器"""
    
    def __init__(self, config_path=None):
        """初始化下载器"""
        self.config = {}
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            except Exception as e:
                logging.warning(f"无法读取MinIO配置文件 {config_path}: {e}")
        
        # 初始化S3客户端（如果有配置）
        self.s3_client = None
        if self.config.get('access_key') and self.config.get('secret_key'):
            # 构建S3客户端配置
            s3_config = {
                's3': {
                    'addressing_style': self.config.get('addressing_style', 'path')  # 支持 'path' 或 'virtual'
                }
            }
            
            self.s3_client = boto3.client(
                's3',
                endpoint_url=self.config.get('endpoint_url'),
                aws_access_key_id=self.config.get('access_key'),
                aws_secret_access_key=self.config.get('secret_key'),
                aws_session_token=None,
                region_name=self.config.get('region', 'us-east-1'),
                config=boto3.session.Config(**s3_config)
            )
    
    def download_file_from_url(self, url, local_path):
        """直接通过HTTP URL下载文件"""
        try:
            response = requests.get(url, stream=True, timeout=300)
            response.raise_for_status()
            
            # 确保目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            with open(local_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            
            logging.info(f"文件下载成功: {url} -> {local_path}")
            return True
            
        except Exception as e:
            logging.error(f"下载文件失败 {url}: {e}")
            return False
    
    def list_bucket_objects(self, bucket_name, prefix=""):
        """列出bucket中的对象"""
        if not self.s3_client:
            return []
        
        try:
            response = self.s3_client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
            objects = response.get('Contents', [])
            return [obj['Key'] for obj in objects]
        except Exception as e:
            logging.error(f"列出bucket对象失败: {e}")
            return []
    
    def download_file_from_s3(self, bucket_name, object_key, local_path):
        """通过S3 API下载文件"""
        if not self.s3_client:
            logging.error("S3客户端未初始化")
            return False
        
        try:
            logging.info(f"开始S3下载 - Bucket: {bucket_name}, Object Key: {object_key}, Local Path: {local_path}")
            logging.info(f"S3客户端配置 - Endpoint: {self.config.get('endpoint_url')}, Region: {self.config.get('region', 'us-east-1')}, Addressing Style: {self.config.get('addressing_style', 'path')}")
            
            # 首先检查bucket是否存在
            try:
                self.s3_client.head_bucket(Bucket=bucket_name)
                logging.info(f"Bucket存在性检查通过: {bucket_name}")
            except ClientError as bucket_error:
                error_code = bucket_error.response['Error']['Code']
                logging.error(f"Bucket检查失败 - 错误代码: {error_code}")
                if error_code == '404':
                    logging.error(f"Bucket不存在: {bucket_name}")
                elif error_code == '403':
                    logging.error(f"Bucket访问被拒绝: {bucket_name}")
                    
                # 如果bucket检查失败，尝试列出所有对象看看是否有相似的文件
                logging.info("尝试列出bucket中的文件...")
                objects = self.list_bucket_objects(bucket_name)
                if objects:
                    logging.info(f"Bucket中找到 {len(objects)} 个文件:")
                    for obj in objects[:10]:  # 只显示前10个
                        logging.info(f"  - {obj}")
                    if len(objects) > 10:
                        logging.info(f"  ... 还有 {len(objects) - 10} 个文件")
                else:
                    logging.info("Bucket中没有找到任何文件")
                
                raise bucket_error
            
            # 检查文件是否存在
            try:
                self.s3_client.head_object(Bucket=bucket_name, Key=object_key)
                logging.info(f"文件存在性检查通过: s3://{bucket_name}/{object_key}")
            except ClientError as head_error:
                error_code = head_error.response['Error']['Code']
                logging.error(f"文件存在性检查失败 - 错误代码: {error_code}")
                if error_code == '404':
                    logging.error(f"文件不存在: s3://{bucket_name}/{object_key}")
                    # 列出bucket中的文件，看是否有相似的文件名
                    logging.info("尝试查找相似的文件名...")
                    objects = self.list_bucket_objects(bucket_name)
                    similar_files = [obj for obj in objects if '品质决胜' in obj or 'PDF' in obj]
                    if similar_files:
                        logging.info(f"找到可能相关的文件:")
                        for file in similar_files:
                            logging.info(f"  - {file}")
                    else:
                        logging.info("没有找到相似的文件名")
                elif error_code == '403':
                    logging.error(f"文件访问被拒绝: s3://{bucket_name}/{object_key}")
                raise head_error
            
            # 确保目录存在
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            
            self.s3_client.download_file(bucket_name, object_key, local_path)
            logging.info(f"S3文件下载成功: s3://{bucket_name}/{object_key} -> {local_path}")
            return True
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logging.error(f"S3下载失败 - Bucket: {bucket_name}, Object Key: {object_key}")
            logging.error(f"错误代码: {error_code}, 错误信息: {error_message}")
            logging.error(f"完整错误响应: {e.response}")
            return False
        except Exception as e:
            logging.error(f"下载文件失败 - Bucket: {bucket_name}, Object Key: {object_key}")
            logging.error(f"异常类型: {type(e).__name__}, 异常信息: {e}")
            return False
    
    def download_file(self, file_info, local_path):
        """根据文件信息下载文件"""
        address = file_info.get('address', '')
        store_method = file_info.get('store_method', '')
        bucket_name = file_info.get('bucket_name', '')
        ext = file_info.get('ext', '')
        
        logging.info(f"下载文件请求 - file_info: {file_info}, local_path: {local_path}")
        
        if store_method == 'minio':
            if address.startswith('s3://'):
                # 解析S3路径: s3://bucket/path/to/file
                parsed = urlparse(address)
                bucket_name = parsed.netloc
                object_key = parsed.path.lstrip('/')
                logging.info(f"解析S3路径 - 原始address: {address}, 解析出bucket: {bucket_name}, object_key: {object_key}")
                return self.download_file_from_s3(bucket_name, object_key, local_path)            
            # 确定bucket_name和object_key
            if bucket_name:
                # 如果传入了bucket_name，直接使用传入的bucket_name和address作为object_key
                object_key = address.lstrip('/')  # 移除前导斜杠
                logging.info(f"使用传入的bucket_name - Bucket: {bucket_name}, 原始address: {address}, 处理后object_key: {object_key}")
            else:
                # 从address中解析bucket_name和object_key
                # 格式：bucket/path/to/file 或 bucket/file
                address_parts = address.strip('/').split('/', 1)
                if len(address_parts) >= 2:
                    bucket_name = address_parts[0]
                    object_key = address_parts[1]
                    logging.info(f"从address解析 - 原始address: {address}, 解析出bucket: {bucket_name}, object_key: {object_key}")
                else:
                    logging.error(f"无法从address解析bucket和object_key: {address}")
                    return False
            if not object_key.endswith(ext):
                object_key = f"{object_key}.{ext}"

            # 检查object_key是否包含特殊字符并尝试下载
            import urllib.parse
            encoded_object_key = urllib.parse.quote(object_key, safe='/')
            if encoded_object_key != object_key:
                logging.info(f"检测到特殊字符，URL编码前: {object_key}, URL编码后: {encoded_object_key}")
                # 尝试使用编码后的key
                success = self.download_file_from_s3(bucket_name, encoded_object_key, local_path)
                if not success:
                    logging.info(f"编码后的key下载失败，尝试原始key: {object_key}")
                    return self.download_file_from_s3(bucket_name, object_key, local_path)
                return success
            else:
                return self.download_file_from_s3(bucket_name, object_key, local_path)
        
        else:
            # 其他存储方式，默认尝试HTTP下载
            if address.startswith('http'):
                return self.download_file_from_url(address, local_path)
            else:
                logging.error(f"不支持的存储方式: {store_method}")
                return False

def main():
    """测试函数"""
    import argparse
    
    # 设置详细的日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description='MinIO文件下载测试')
    parser.add_argument('--config', help='配置文件路径')
    parser.add_argument('--url', help='文件URL')
    parser.add_argument('--bucket', help='MinIO bucket名称')
    parser.add_argument('--output', help='输出文件路径')
    parser.add_argument('--list', action='store_true', help='列出bucket中的文件')
    args = parser.parse_args()
    
    downloader = MinioDownloader(args.config)
    
    # 如果指定了列出文件
    if args.list and args.bucket:
        logging.info(f"列出bucket '{args.bucket}' 中的文件...")
        objects = downloader.list_bucket_objects(args.bucket)
        if objects:
            print(f"Bucket '{args.bucket}' 中找到 {len(objects)} 个文件:")
            for obj in objects:
                print(f"  - {obj}")
        else:
            print(f"Bucket '{args.bucket}' 中没有找到任何文件")
        return
    
    if args.url and args.output:
        logging.info(f"开始下载 - 配置文件: {args.config}, URL: {args.url}, Bucket: {args.bucket}, 输出路径: {args.output}")
        
        file_info = {
            'address': args.url,
            'store_method': 'minio'
        }
        # 如果传入了bucket参数，添加到file_info中
        if args.bucket:
            file_info['bucket_name'] = args.bucket
        
        success = downloader.download_file(file_info, args.output)
        print(f"下载{'成功' if success else '失败'}")
    else:
        print("请提供 --url 和 --output 参数进行下载，或使用 --list --bucket 列出文件")

if __name__ == '__main__':
    main() 