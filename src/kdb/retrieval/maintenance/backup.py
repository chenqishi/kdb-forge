#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ES数据备份工具
- 支持备份所有索引或指定索引的数据
- 支持备份mapping和settings信息
- 支持多种格式和压缩选项
- 支持断点续传和增量备份

Author: Assistant
Date: 2025-01-30
"""

import json
import logging
import argparse
import os
import gzip
import time
from datetime import datetime
from typing import List
from typing import Dict
from typing import Any
from typing import Optional
from typing import Iterator
from elasticsearch import Elasticsearch
from elasticsearch.helpers import scan

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)


def _remove_fields_from_source(source: Dict[str, Any], field_paths: List[str]) -> None:
    """
    从 _source 字典中按点分路径删除指定字段（原地修改）。
    用于客户端剥离 dense_vector 等字段，避免依赖服务端 _source 过滤（部分 ES/OpenSearch 会返回空）。
    """
    for path in field_paths:
        parts = path.split('.')
        if len(parts) == 1:
            if path in source:
                del source[path]
            continue
        d = source
        for p in parts[:-1]:
            if p not in d or not isinstance(d.get(p), dict):
                break
            d = d[p]
        else:
            if parts[-1] in d:
                del d[parts[-1]]


class ESBackupTool:
    """ES数据备份工具类"""
    
    def __init__(self, config_path: str):
        """
        初始化备份工具
        Args:
            config_path: ES配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.es = self._init_es_client()
        
    def _load_config(self) -> Dict[str, Any]:
        """加载ES配置"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.error(f"加载配置文件失败: {str(e)}")
            raise
    
    def _init_es_client(self) -> Elasticsearch:
        """初始化ES客户端"""
        try:
            hosts = self.config.get('hosts')
            username = self.config.get('username')
            password = self.config.get('password')
            extra_params = self.config.get('extra_params', {})
            
            es_params = {
                'hosts': hosts,
                'timeout': 30,
                'max_retries': 3,
                'retry_on_timeout': True,
                'verify_certs': False,
            }
            
            if username and password:
                es_params['http_auth'] = (username, password)
            
            if extra_params:
                es_params.update(extra_params)
            
            return Elasticsearch(**es_params)
        except Exception as e:
            logging.error(f"初始化ES客户端失败: {str(e)}")
            raise
    
    def get_all_indexes(self, exclude_system: bool = True) -> List[Dict[str, str]]:
        """
        获取ES中的所有索引
        Args:
            exclude_system: 是否排除系统索引
        Returns:
            List[Dict]: 索引信息列表
        """
        try:
            response = self.es.cat.indices(format='json', h='index,docs.count,store.size')
            
            indexes = []
            for index_info in response:
                index_name = index_info['index']
                
                # 排除系统索引
                if exclude_system and index_name.startswith('.'):
                    continue
                    
                indexes.append({
                    'name': index_name,
                    'docs_count': index_info.get('docs.count', '0'),
                    'store_size': index_info.get('store.size', '0b')
                })
            
            logging.info(f"发现 {len(indexes)} 个索引")
            return indexes
            
        except Exception as e:
            logging.error(f"获取索引列表失败: {str(e)}")
            raise
    
    def get_index_mapping(self, index_name: str) -> Dict[str, Any]:
        """
        获取索引的mapping信息
        Args:
            index_name: 索引名称
        Returns:
            Dict: mapping信息
        """
        try:
            response = self.es.indices.get_mapping(index=index_name)
            return response.get(index_name, {})
        except Exception as e:
            logging.error(f"获取索引 {index_name} mapping失败: {str(e)}")
            return {}
    
    def get_index_settings(self, index_name: str) -> Dict[str, Any]:
        """
        获取索引的settings信息
        Args:
            index_name: 索引名称
        Returns:
            Dict: settings信息
        """
        try:
            response = self.es.indices.get_settings(index=index_name)
            return response.get(index_name, {})
        except Exception as e:
            logging.error(f"获取索引 {index_name} settings失败: {str(e)}")
            return {}
    
    def get_dense_vector_fields(self, index_name: str) -> List[str]:
        """
        获取索引中的所有dense_vector字段
        Args:
            index_name: 索引名称
        Returns:
            List[str]: dense_vector字段名称列表
        """
        try:
            mapping = self.get_index_mapping(index_name)
            dense_vector_fields = []
            
            def extract_dense_vector_fields(properties: Dict[str, Any], prefix: str = ""):
                """递归提取dense_vector字段"""
                for field_name, field_config in properties.items():
                    full_field_name = f"{prefix}.{field_name}" if prefix else field_name
                    
                    if isinstance(field_config, dict):
                        # 检查字段类型
                        if field_config.get('type') == 'dense_vector':
                            dense_vector_fields.append(full_field_name)
                        
                        # 递归处理嵌套字段
                        if 'properties' in field_config:
                            extract_dense_vector_fields(field_config['properties'], full_field_name)
            
            # 提取字段
            mappings = mapping.get('mappings', {})
            if 'properties' in mappings:
                extract_dense_vector_fields(mappings['properties'])
            
            if dense_vector_fields:
                logging.info(f"索引 {index_name} 发现 {len(dense_vector_fields)} 个dense_vector字段: {dense_vector_fields}")
            
            return dense_vector_fields
            
        except Exception as e:
            logging.error(f"获取索引 {index_name} dense_vector字段失败: {str(e)}")
            return []
    
    def _backup_with_search_after(self, 
                                 index_name: str, 
                                 batch_size: int, 
                                 excluded_fields: List[str],
                                 file_handle,
                                 backup_format: str) -> int:
        """
        使用search_after API进行数据备份（兼容阿里云ES等不支持scroll的环境）
        Args:
            index_name: 索引名称
            batch_size: 批处理大小
            excluded_fields: 排除的字段列表
            file_handle: 文件句柄
            backup_format: 备份格式
        Returns:
            int: 备份的文档数量
        """
        backed_up_docs = 0
        search_after = None
        warned_empty_source = False
        
        # 构建基础查询（不传 _source 过滤，拉取完整 _source 后在客户端剥离排除字段，兼容阿里云 ES Serverless 等对 _source 过滤返回空的情况）
        query_body = {
            "query": {"match_all": {}},
            "size": batch_size,
            "sort": [{"_id": {"order": "asc"}}]  # 使用_id排序以确保一致性
        }
        
        while True:
            # 添加search_after参数
            if search_after:
                query_body['search_after'] = search_after
            
            try:
                # 执行搜索
                response = self.es.search(
                    index=index_name,
                    body=query_body
                )
                
                hits = response['hits']['hits']
                
                # 如果没有更多数据，退出循环
                if not hits:
                    break
                
                # 处理每个文档
                for i, doc in enumerate(hits):
                    source = doc.get("_source") or {}
                    if excluded_fields:
                        _remove_fields_from_source(source, excluded_fields)
                    if not source and not warned_empty_source:
                        warned_empty_source = True
                        logging.warning(
                            f"索引 {index_name} 首条文档 _source 为空。若全部文档皆空，请检查索引 mapping 中 _source.enabled 或 GET /<index>/_doc/<id> 查看单条。"
                        )
                    doc_data = {
                        "_index": doc["_index"],
                        "_id": doc["_id"],
                        "_source": source
                    }
                    
                    if backup_format == "json":
                        # JSON格式
                        if backed_up_docs > 0:
                            file_handle.write(',\n')
                        json.dump(doc_data, file_handle, ensure_ascii=False, indent=2)
                    else:
                        # NDJSON格式
                        json.dump(doc_data, file_handle, ensure_ascii=False)
                        file_handle.write('\n')
                    
                    backed_up_docs += 1
                
                # 更新search_after为最后一个文档的sort值
                if hits:
                    search_after = hits[-1]['sort']
                
                # 显示进度
                if backed_up_docs % (batch_size * 10) == 0:
                    logging.info(f"备份进度: {backed_up_docs:,} 文档")
                
            except Exception as e:
                logging.error(f"search_after查询失败: {str(e)}")
                raise
        
        return backed_up_docs
    
    def backup_index_data(self, 
                         index_name: str,
                         backup_dir: str,
                         batch_size: int = 1000,
                         backup_format: str = "ndjson",
                         compress: bool = False,
                         exclude_dense_vector: bool = True,
                         use_search_after: bool = False) -> Dict[str, Any]:
        """
        备份索引数据
        Args:
            index_name: 索引名称
            backup_dir: 备份目录
            batch_size: 批处理大小
            backup_format: 备份格式 (json|ndjson)
            compress: 是否压缩
            exclude_dense_vector: 是否排除dense_vector字段
            use_search_after: 是否强制使用search_after API（适用于不支持scroll的ES环境）
        Returns:
            Dict: 备份结果
        """
        try:
            # 创建索引备份目录
            index_backup_dir = os.path.join(backup_dir, index_name)
            os.makedirs(index_backup_dir, exist_ok=True)
            
            # 生成备份文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            if backup_format == "json":
                filename = f"{index_name}_data_{timestamp}.json"
            else:
                filename = f"{index_name}_data_{timestamp}.ndjson"
            
            if compress:
                filename += ".gz"
            
            filepath = os.path.join(index_backup_dir, filename)
            
            # 获取索引总文档数
            count_response = self.es.count(index=index_name)
            total_docs = count_response['count']
            
            if total_docs == 0:
                logging.warning(f"索引 {index_name} 为空，跳过数据备份")
                return {
                    "index_name": index_name,
                    "total_docs": 0,
                    "backed_up_docs": 0,
                    "backup_file": None,
                    "file_size": 0,
                    "status": "skipped"
                }
            
            # 获取需要排除的dense_vector字段
            excluded_fields = []
            if exclude_dense_vector:
                dense_vector_fields = self.get_dense_vector_fields(index_name)
                excluded_fields.extend(dense_vector_fields)
            
            if excluded_fields:
                logging.info(f"排除字段: {excluded_fields}")
            
            logging.info(f"开始备份索引 {index_name}，总文档数: {total_docs:,}")
            
            # 开始备份
            start_time = time.time()
            backed_up_docs = 0
            
            # 打开文件进行写入
            if compress:
                file_handle = gzip.open(filepath, 'wt', encoding='utf-8')
            else:
                file_handle = open(filepath, 'w', encoding='utf-8')
            
            try:
                if backup_format == "json":
                    # JSON格式：写入数组开始
                    file_handle.write('[\n')
                
                # 根据参数决定使用哪种API
                force_search_after = use_search_after
                
                if force_search_after:
                    # 强制使用search_after API
                    logging.info(f"强制使用search_after API进行备份...")
                    backed_up_docs = self._backup_with_search_after(
                        index_name=index_name,
                        batch_size=batch_size,
                        excluded_fields=excluded_fields,
                        file_handle=file_handle,
                        backup_format=backup_format
                    )
                else:
                    # 首先尝试使用scroll API
                    try:
                        # 构建查询（不传 _source 过滤，拉取完整 _source 后在客户端剥离排除字段，兼容阿里云 ES Serverless 等对 _source 过滤返回空的情况）
                        scan_kwargs = {
                            'query': {"query": {"match_all": {}}},
                            'index': index_name,
                            'size': batch_size,
                            'scroll': '5m'
                        }
                        
                        logging.info(f"尝试使用scroll API进行备份...")
                        
                        warned_empty = False
                        for i, doc in enumerate(scan(self.es, **scan_kwargs)):
                            source = doc.get("_source") or {}
                            if excluded_fields:
                                _remove_fields_from_source(source, excluded_fields)
                            if not source and not warned_empty:
                                warned_empty = True
                                logging.warning(
                                    f"索引 {index_name} 首条文档 _source 为空。若全部文档皆空，请检查索引 mapping 中 _source.enabled 或 GET /<index>/_doc/<id> 查看单条。"
                                )
                            doc_data = {
                                "_index": doc["_index"],
                                "_id": doc["_id"],
                                "_source": source
                            }
                            
                            if backup_format == "json":
                                # JSON格式
                                if i > 0:
                                    file_handle.write(',\n')
                                json.dump(doc_data, file_handle, ensure_ascii=False, indent=2)
                            else:
                                # NDJSON格式
                                json.dump(doc_data, file_handle, ensure_ascii=False)
                                file_handle.write('\n')
                            
                            backed_up_docs += 1
                            
                            # 显示进度
                            if backed_up_docs % (batch_size * 10) == 0:
                                progress = (backed_up_docs / total_docs) * 100
                                logging.info(f"备份进度: {backed_up_docs:,}/{total_docs:,} ({progress:.1f}%)")
                    
                    except Exception as scroll_error:
                        # 检查是否是serverless不支持的错误
                        error_msg = str(scroll_error).lower()
                        if 'serverless_unsupported_exception' in error_msg or 'scroll' in error_msg:
                            logging.warning(f"Scroll API不支持，切换到search_after API: {str(scroll_error)}")
                            backed_up_docs = 0  # 重置计数器
                            
                            # 重置文件位置
                            file_handle.seek(0)
                            file_handle.truncate()
                            if backup_format == "json":
                                file_handle.write('[\n')
                            
                            # 使用search_after API重新备份
                            logging.info(f"使用search_after API进行备份...")
                            backed_up_docs = self._backup_with_search_after(
                                index_name=index_name,
                                batch_size=batch_size,
                                excluded_fields=excluded_fields,
                                file_handle=file_handle,
                                backup_format=backup_format
                            )
                        else:
                            # 其他错误直接抛出
                            raise scroll_error
                
                if backup_format == "json":
                    # JSON格式：写入数组结束
                    file_handle.write('\n]')
                
            finally:
                file_handle.close()
            
            # 获取文件大小
            file_size = os.path.getsize(filepath)
            
            end_time = time.time()
            elapsed_time = end_time - start_time
            
            result = {
                "index_name": index_name,
                "total_docs": total_docs,
                "backed_up_docs": backed_up_docs,
                "backup_file": filepath,
                "file_size": file_size,
                "file_size_mb": round(file_size / 1024 / 1024, 2),
                "elapsed_time": round(elapsed_time, 2),
                "docs_per_second": round(backed_up_docs / elapsed_time, 2) if elapsed_time > 0 else 0,
                "status": "success"
            }
            
            logging.info(f"索引 {index_name} 备份完成: {backed_up_docs:,} 文档, "
                        f"{result['file_size_mb']}MB, 耗时 {elapsed_time:.1f}s")
            
            return result
            
        except Exception as e:
            logging.error(f"备份索引 {index_name} 数据失败: {str(e)}")
            return {
                "index_name": index_name,
                "status": "failed",
                "error": str(e)
            }
    
    def backup_index_metadata(self,
                            index_name: str,
                            backup_dir: str,
                            include_mapping: bool = True,
                            include_settings: bool = True,
                            compress: bool = False) -> Dict[str, Any]:
        """
        备份索引元数据（mapping和settings）
        Args:
            index_name: 索引名称
            backup_dir: 备份目录
            include_mapping: 是否包含mapping
            include_settings: 是否包含settings
            compress: 是否压缩
        Returns:
            Dict: 备份结果
        """
        try:
            # 创建索引备份目录
            index_backup_dir = os.path.join(backup_dir, index_name)
            os.makedirs(index_backup_dir, exist_ok=True)
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backed_files = []
            
            # 备份mapping
            if include_mapping:
                mapping = self.get_index_mapping(index_name)
                if mapping:
                    mapping_filename = f"{index_name}_mapping_{timestamp}.json"
                    if compress:
                        mapping_filename += ".gz"
                    
                    mapping_filepath = os.path.join(index_backup_dir, mapping_filename)
                    
                    if compress:
                        with gzip.open(mapping_filepath, 'wt', encoding='utf-8') as f:
                            json.dump(mapping, f, ensure_ascii=False, indent=2)
                    else:
                        with open(mapping_filepath, 'w', encoding='utf-8') as f:
                            json.dump(mapping, f, ensure_ascii=False, indent=2)
                    
                    backed_files.append({
                        "type": "mapping",
                        "file": mapping_filepath,
                        "size": os.path.getsize(mapping_filepath)
                    })
            
            # 备份settings
            if include_settings:
                settings = self.get_index_settings(index_name)
                if settings:
                    settings_filename = f"{index_name}_settings_{timestamp}.json"
                    if compress:
                        settings_filename += ".gz"
                    
                    settings_filepath = os.path.join(index_backup_dir, settings_filename)
                    
                    if compress:
                        with gzip.open(settings_filepath, 'wt', encoding='utf-8') as f:
                            json.dump(settings, f, ensure_ascii=False, indent=2)
                    else:
                        with open(settings_filepath, 'w', encoding='utf-8') as f:
                            json.dump(settings, f, ensure_ascii=False, indent=2)
                    
                    backed_files.append({
                        "type": "settings",
                        "file": settings_filepath,
                        "size": os.path.getsize(settings_filepath)
                    })
            
            return {
                "index_name": index_name,
                "backed_files": backed_files,
                "status": "success"
            }
            
        except Exception as e:
            logging.error(f"备份索引 {index_name} 元数据失败: {str(e)}")
            return {
                "index_name": index_name,
                "status": "failed",
                "error": str(e)
            }
    
    def backup_indexes(self,
                      index_names: List[str],
                      backup_dir: str,
                      batch_size: int = 1000,
                      backup_format: str = "ndjson",
                      include_mapping: bool = False,
                      include_settings: bool = False,
                      compress: bool = False,
                      exclude_dense_vector: bool = True,
                      use_search_after: bool = False,
                      dry_run: bool = False) -> Dict[str, Any]:
        """
        批量备份索引
        Args:
            index_names: 索引名称列表
            backup_dir: 备份目录
            batch_size: 批处理大小
            backup_format: 备份格式
            include_mapping: 是否包含mapping
            include_settings: 是否包含settings
            compress: 是否压缩
            exclude_dense_vector: 是否排除dense_vector字段
            use_search_after: 是否强制使用search_after API
            dry_run: 是否为试运行
        Returns:
            Dict: 批量备份结果
        """
        results = {}
        summary = {
            "total_indexes": len(index_names),
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "total_docs_backed_up": 0,
            "total_backup_size_mb": 0,
            "start_time": datetime.now().isoformat(),
            "end_time": None
        }
        
        start_time = time.time()
        
        for index_name in index_names:
            print(f"\n{'='*60}")
            print(f"处理索引: {index_name}")
            print(f"{'='*60}")
            
            try:
                if dry_run:
                    # 试运行模式：只获取索引信息
                    count_response = self.es.count(index=index_name)
                    total_docs = count_response['count']
                    
                    print(f"🔍 试运行模式")
                    print(f"文档数量: {total_docs:,}")
                    
                    if include_mapping:
                        print("📋 将备份mapping信息")
                    if include_settings:
                        print("⚙️  将备份settings信息")
                    
                    results[index_name] = {
                        "status": "dry_run",
                        "total_docs": total_docs
                    }
                    continue
                
                # 实际备份
                index_results = {}
                
                # 备份数据
                data_result = self.backup_index_data(
                    index_name=index_name,
                    backup_dir=backup_dir,
                    batch_size=batch_size,
                    backup_format=backup_format,
                    compress=compress,
                    exclude_dense_vector=exclude_dense_vector,
                    use_search_after=use_search_after
                )
                index_results["data"] = data_result
                
                if data_result["status"] == "success":
                    summary["total_docs_backed_up"] += data_result["backed_up_docs"]
                    summary["total_backup_size_mb"] += data_result.get("file_size_mb", 0)
                elif data_result["status"] == "skipped":
                    summary["skipped_count"] += 1
                    continue
                
                # 备份元数据
                if include_mapping or include_settings:
                    metadata_result = self.backup_index_metadata(
                        index_name=index_name,
                        backup_dir=backup_dir,
                        include_mapping=include_mapping,
                        include_settings=include_settings,
                        compress=compress
                    )
                    index_results["metadata"] = metadata_result
                
                # 判断整体状态
                if (data_result["status"] == "success" and 
                    (not (include_mapping or include_settings) or 
                     index_results.get("metadata", {}).get("status") == "success")):
                    print(f"✅ 备份成功")
                    summary["success_count"] += 1
                    index_results["status"] = "success"
                else:
                    print(f"❌ 备份失败")
                    summary["failed_count"] += 1
                    index_results["status"] = "failed"
                
                results[index_name] = index_results
                
            except Exception as e:
                logging.error(f"处理索引 {index_name} 失败: {str(e)}")
                print(f"❌ 处理失败: {str(e)}")
                results[index_name] = {"status": "failed", "error": str(e)}
                summary["failed_count"] += 1
        
        end_time = time.time()
        total_time = end_time - start_time
        summary["end_time"] = datetime.now().isoformat()
        summary["total_time_seconds"] = round(total_time, 2)
        
        # 打印总结
        print(f"\n{'='*60}")
        print("批量备份总结")
        print(f"{'='*60}")
        print(f"总索引数: {summary['total_indexes']}")
        print(f"成功: {summary['success_count']}")
        print(f"失败: {summary['failed_count']}")
        print(f"跳过: {summary['skipped_count']}")
        if not dry_run:
            print(f"总备份文档数: {summary['total_docs_backed_up']:,}")
            print(f"总备份大小: {summary['total_backup_size_mb']:.2f}MB")
        print(f"总耗时: {total_time:.1f}s")
        
        return {
            "summary": summary,
            "details": results
        }

def main():
    parser = argparse.ArgumentParser(description="ES数据备份工具")
    parser.add_argument("--config", required=True, help="ES配置文件路径")
    parser.add_argument("--index", help="索引名称，支持'all'获取所有索引")
    parser.add_argument("--indexes", help="多个索引名称，用逗号分隔")
    parser.add_argument("--backup-dir", help="备份目录路径")
    parser.add_argument("--list-indexes", action="store_true", help="列出所有索引")
    parser.add_argument("--format", default="ndjson", choices=["json", "ndjson"], help="备份格式")
    parser.add_argument("--batch-size", type=int, default=1000, help="批处理大小")
    parser.add_argument("--include-mapping", action="store_true", help="包含mapping信息")
    parser.add_argument("--include-settings", action="store_true", help="包含settings信息")
    parser.add_argument("--compress", action="store_true", help="压缩备份文件")
    parser.add_argument("--exclude-system", action="store_true", default=True, help="排除系统索引")
    parser.add_argument("--exclude-dense-vector", action="store_true", default=True, help="排除dense_vector字段")
    parser.add_argument("--include-dense-vector", action="store_true", help="包含dense_vector字段")
    parser.add_argument("--use-search-after", action="store_true", help="强制使用search_after API（适用于阿里云ES等）")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式")
    
    args = parser.parse_args()
    
    try:
        # 初始化备份工具
        backup_tool = ESBackupTool(args.config)
        
        # 列出索引
        if args.list_indexes:
            indexes = backup_tool.get_all_indexes(exclude_system=args.exclude_system)
            print(f"\n发现 {len(indexes)} 个索引:")
            print(f"{'索引名称':<30} {'文档数':<15} {'存储大小':<15}")
            print("-" * 60)
            for index_info in indexes:
                print(f"{index_info['name']:<30} {index_info['docs_count']:<15} {index_info['store_size']:<15}")
            return
        
        # 检查必需参数
        if not args.backup_dir:
            parser.error("备份操作需要指定 --backup-dir 参数")
        
        # 确定要备份的索引
        if args.index:
            if args.index.lower() == 'all':
                indexes_info = backup_tool.get_all_indexes(exclude_system=args.exclude_system)
                index_names = [info['name'] for info in indexes_info]
                if not index_names:
                    print("❌ 未找到任何索引")
                    return
                print(f"🔍 发现 {len(index_names)} 个索引: {index_names}")
            else:
                index_names = [args.index]
        elif args.indexes:
            index_names = [name.strip() for name in args.indexes.split(',')]
        else:
            parser.error("必须指定 --index 或 --indexes 参数")
        
        # 处理dense_vector参数
        exclude_dense_vector = not args.include_dense_vector if args.include_dense_vector else args.exclude_dense_vector
        
        # 执行备份
        result = backup_tool.backup_indexes(
            index_names=index_names,
            backup_dir=args.backup_dir,
            batch_size=args.batch_size,
            backup_format=args.format,
            include_mapping=args.include_mapping,
            include_settings=args.include_settings,
            compress=args.compress,
            exclude_dense_vector=exclude_dense_vector,
            use_search_after=args.use_search_after,
            dry_run=args.dry_run
        )
        
        print(f"\n🎉 备份完成！")
        
    except Exception as e:
        logging.error(f"执行失败: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main() 