#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
MinIO文件下载工具
"""
from kdb.shared.config.private_values import private_value as _private_value
import os
import sys
import json
import logging
import requests
from urllib.parse import urlparse
import boto3
from botocore.exceptions import ClientError
import time
import logging
logger = logging.getLogger(__name__)
class MinioTools:
    """MinIO工具类"""
    
    def __init__(self, config=None):
        """初始化下载器"""
        if isinstance(config, dict):
            self.config = config
        elif isinstance(config, str):
            self.config = json.load(open(config, 'r', encoding='utf-8'))
        else:
            self.config = {}
        
        # 使用普通字典存储URL和其生成时间
        self.url_cache = {}
        # 检查并设置默认值
        if not self.config.get('endpoint_url'):
            self.config['endpoint_url'] = "http://47.107.119.83:9000"
        if not self.config.get('access_key'):
            self.config['access_key'] = _private_value('0ee180dc6e95fd57e8b2b323')
        if not self.config.get('secret_key'):
            self.config['secret_key'] = _private_value('b6cd00e5a7df684416e8cc6e')
        if not self.config.get('region'):
            self.config['region'] = "us-east-1"
        if not self.config.get('bucket_name'):
            self.config['bucket_name'] = "boot-admin"
        if not self.config.get("valid_time"):
            self.config['valid_time'] = 3600 * 24 * 7

        print(f"endpoint_url:{self.config['endpoint_url']}")
        

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
    
    def generate_public_url(self, object_key, bucket_name=None, permanent=False):
        """根据完整路径生成公网可访问的URL
        
        Args:
            object_key: 对象键，如 "default/20250822/1958810147841191937.png"
            bucket_name: bucket名称，如果不指定则使用默认bucket
            permanent: 是否生成永久有效URL，默认False生成临时URL
            
        Returns:
            str: 公网可访问的URL，如果生成失败返回None
        """
        if not self.s3_client:
            logging.error("S3客户端未初始化")
            return None
        
        # 如果没有指定bucket，使用默认bucket
        if not bucket_name:
            bucket_name = self.config.get('bucket_name', 'boot-admin')
        
        # 如果需要永久URL，直接拼接返回（需要确保bucket有公开读权限）
        if permanent:
            endpoint_url = self.config.get('endpoint_url', '')
            # 去掉协议部分
            if endpoint_url.startswith('http://'):
                endpoint_url = endpoint_url[7:]
            elif endpoint_url.startswith('https://'):
                endpoint_url = endpoint_url[8:]
            
            permanent_url = f"{self.config.get('endpoint_url')}/{bucket_name}/{object_key}"
            logger.info(f"生成永久URL: {permanent_url}")
            return permanent_url
        
        # 生成临时URL（带签名）
        full_path = f"{bucket_name}/{object_key}"
        
        # 检查缓存，如果存在且未过期则返回
        if full_path in self.url_cache:
            cached_data = self.url_cache[full_path]
            cached_url = cached_data['url']
            cached_time = cached_data['time']
            # 如果缓存时间未超过3600秒，直接返回缓存的URL
            if time.time() - cached_time < self.config.get('valid_time', 3600 * 24 * 3):
                return cached_url
            else:
                # 缓存过期，删除
                del self.url_cache[full_path]
        
        try:
            # 生成预签名URL，有效期3700秒
            print(f"生成预签名URL: {bucket_name}/{object_key}, 有效时间{self.config.get('valid_time', 3600 * 24 * 3)}")
            presigned_url = self.s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': bucket_name, 'Key': object_key},
                ExpiresIn=self.config.get('valid_time', 3600 * 24 * 3)
            )
            
            # 缓存URL和生成时间
            self.url_cache[full_path] = {
                'url': presigned_url,
                'time': time.time()
            }
            return presigned_url
            
        except Exception as e:
            logger.error(f"生成URL失败: {full_path}, 错误: {e}")
            return None
    
    def upload_file(self, local_file_path, object_key, bucket_name=None, content_type=None):
        """上传文件到MinIO
        
        Args:
            local_file_path: 本地文件路径
            object_key: 对象键（存储路径），如 "default/20250822/test.png"
            bucket_name: bucket名称，如果不指定则使用默认bucket
            content_type: 文件MIME类型，如 "image/png"，不指定则自动推断
            
        Returns:
            bool: 上传是否成功
        """
        if not self.s3_client:
            logger.error("S3客户端未初始化")
            return False
        
        # 如果没有指定bucket，使用默认bucket
        if not bucket_name:
            bucket_name = self.config.get('bucket_name', 'boot-admin')
        
        # 检查本地文件是否存在
        if not os.path.exists(local_file_path):
            logger.error(f"本地文件不存在: {local_file_path}")
            return False
        
        try:
            # 准备上传参数
            extra_args = {}
            if content_type:
                extra_args['ContentType'] = content_type
            else:
                # 自动推断content_type
                import mimetypes
                guessed_type, _ = mimetypes.guess_type(local_file_path)
                if guessed_type:
                    extra_args['ContentType'] = guessed_type
            
            # 上传文件
            self.s3_client.upload_file(
                local_file_path,
                bucket_name,
                object_key,
                ExtraArgs=extra_args if extra_args else None
            )
            
            logger.info(f"文件上传成功: {local_file_path} -> {bucket_name}/{object_key}")
            return True
            
        except Exception as e:
            logger.error(f"文件上传失败: {local_file_path} -> {bucket_name}/{object_key}, 错误: {e}")
            return False
    
    def upload_file_and_get_url(self, local_file_path, object_key, bucket_name=None, content_type=None):
        """上传文件到MinIO并生成永久有效URL
        
        Args:
            local_file_path: 本地文件路径
            object_key: 对象键（存储路径），如 "default/20250822/test.png"
            bucket_name: bucket名称，如果不指定则使用默认bucket
            content_type: 文件MIME类型，如 "image/png"，不指定则自动推断
            
        Returns:
            str: 永久有效的公网URL，如果上传失败返回None
        """
        # 先上传文件
        upload_success = self.upload_file(local_file_path, object_key, bucket_name, content_type)
        
        if not upload_success:
            logger.error(f"上传文件失败，无法生成URL")
            return None
        
        # 生成永久有效URL
        url = self.generate_public_url(object_key, bucket_name, permanent=True)
        return url

 
if __name__ == "__main__":
    import argparse
    
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='MinIO文件管理工具 - 支持文件上传和URL生成')
    parser.add_argument('--config_path', type=str, help='配置文件路径', default=None)
    parser.add_argument('--file_path', type=str, help='要上传的本地文件路径')
    parser.add_argument('--object_key', type=str, help='远程对象键（存储路径）', default=None)
    parser.add_argument('--bucket', type=str, help='bucket名称（可选，不指定则使用默认）', default=None)
    parser.add_argument('--permanent', action='store_true', help='生成永久URL（默认生成临时URL）')
    parser.add_argument('--url_only', action='store_true', help='仅生成URL，不上传文件（需要指定object_key）')
    
    args = parser.parse_args()
    
    # 参数验证
    if args.url_only:
        # 仅生成URL模式，需要指定object_key
        if not args.object_key:
            print("❌ 错误：使用 --url_only 模式时，必须指定 --object_key 参数")
            sys.exit(1)
    else:
        # 上传模式，需要指定file_path
        if not args.file_path:
            print("❌ 错误：上传模式需要指定 --file_path 参数")
            sys.exit(1)
    
    # 初始化MinioTools
    if args.config_path:
        print(f"使用配置文件: {args.config_path}")
        minio_tools = MinioTools(config=args.config_path)
    else:
        print("使用默认配置")
        minio_tools = MinioTools()
    
    # 获取object_key
    if args.object_key:
        object_key = args.object_key
    elif not args.url_only:
        # 上传模式且未指定object_key，使用文件名作为默认值
        file_name = os.path.basename(args.file_path)
        # 可以加上日期路径
        from datetime import datetime
        date_str = datetime.now().strftime("%Y%m%d")
        object_key = f"upload/{date_str}/{file_name}"
    else:
        # 这种情况不应该发生，因为前面已经检查过了
        print("❌ 错误：object_key未指定")
        sys.exit(1)
    
    # 显示操作信息
    if args.url_only:
        print(f"模式: 仅生成URL")
        print(f"远程路径: {object_key}")
        if args.bucket:
            print(f"目标bucket: {args.bucket}")
        
        # 仅生成URL
        print(f"\n正在生成{'永久' if args.permanent else '临时'}URL...")
        url = minio_tools.generate_public_url(object_key, args.bucket, permanent=args.permanent)
        
        if url:
            print(f"\n✅ URL生成成功！")
            print(f"{'永久' if args.permanent else '临时'}URL: {url}")
        else:
            print(f"\n❌ URL生成失败！")
            sys.exit(1)
    else:
        print(f"模式: 上传文件并生成URL")
        print(f"本地文件: {args.file_path}")
        print(f"远程路径: {object_key}")
        if args.bucket:
            print(f"目标bucket: {args.bucket}")
        
        # 上传文件并生成URL
        print("\n开始上传文件...")
        url = minio_tools.upload_file_and_get_url(
            args.file_path,
            object_key,
            bucket_name=args.bucket
        )
        
        if url:
            print(f"\n✅ 上传成功！")
            if args.permanent:
                print(f"永久URL: {url}")
            else:
                # 重新生成指定类型的URL
                url = minio_tools.generate_public_url(object_key, args.bucket, permanent=args.permanent)
                print(f"{'永久' if args.permanent else '临时'}URL: {url}")
        else:
            print(f"\n❌ 上传失败！")
            sys.exit(1)

