from kdb.shared.config.paths import PROJECT_ROOT as _PROJECT_ROOT
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
自动补充ES索引中缺失的字段
- 自动获取ES所有索引或指定索引
- 自动添加字段mapping（如果不存在）
- 批量补充缺失的字段数据
- 不影响其他字段

Author: Assistant
Date: 2025-01-30
"""

import json
import logging
import argparse
import sys
import os
from typing import List, Dict, Any, Optional, Union
from elasticsearch import Elasticsearch

# 添加项目根目录到Python路径
current_dir = str(_PROJECT_ROOT)
project_root = os.path.dirname(current_dir)

try:
    from kdb.retrieval.application.knowledge_tools import (get_from_norm_type,
                                                           build_default_primary_category)
except ImportError:
    # 如果还是失败，尝试从当前目录导入
    from kdb.retrieval.application.knowledge_tools import get_from_norm_type, build_default_primary_category

# 缺失时补充的 primary_category 默认值。
# 定义收敛到 knowledge_tools，和插入链路 process_one_data 的兜底共用一份，
# 避免两边各写一个字面量后漂移。
DEFAULT_PRIMARY_CATEGORY = build_default_primary_category()

# scroll 拉取时不需要的重字段（每条两个 1024 维向量，不排除的话响应会大几十倍）
SOURCE_EXCLUDES = ["title_embedding", "content_embedding",
                   "indexes", "image_indexes"]


def build_missing_field_query(field_names: List[str], force: bool = False) -> Dict[str, Any]:
    """
    构造「待补字段」的查询：存活文档中**缺少这些字段里任意一个**的。

    注意不能写成 `must_not: [exists f1, exists f2]` —— 那个语义是
    「既没有 f1 **也**没有 f2」，只会捞到两个字段都缺的文档。
    实测 payoneer_olive 缺 dataset 的有 2629 条、缺 primary_category 的 74 条
    （74 是前者的子集），一次传 `dataset,primary_category` 只更新了 74 条，
    另外 2555 条被静默跳过，日志里还显示"处理完成"。
    正确写法是 should + minimum_should_match=1。
    """
    if force:
        return {"bool": {"must": [{"term": {"del_flag": 0}}]}}
    return {
        "bool": {
            "must": [{"term": {"del_flag": 0}}],
            "should": [{"bool": {"must_not": {"exists": {"field": name}}}}
                       for name in field_names],
            "minimum_should_match": 1,
        }
    }

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class FieldSupplier:
    """字段补充工具类"""
    
    def __init__(self, config_path: str):
        """
        初始化字段补充工具
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
    
    def get_all_indexes(self, exclude_system: bool = True) -> List[str]:
        """
        获取ES中的所有索引
        Args:
            exclude_system: 是否排除系统索引（以.开头的索引）
        Returns:
            List[str]: 索引名称列表
        """
        try:
            # 获取所有索引信息
            response = self.es.cat.indices(format='json', h='index')
            
            indexes = []
            for index_info in response:
                index_name = index_info['index']
                
                # 排除系统索引
                if exclude_system and index_name.startswith('.'):
                    continue
                    
                indexes.append(index_name)
            
            logging.info(f"发现 {len(indexes)} 个索引: {indexes}")
            return sorted(indexes)
            
        except Exception as e:
            logging.error(f"获取索引列表失败: {str(e)}")
            raise
    
    def check_field_mapping(self, index_name: str, field_name: str) -> bool:
        """
        检查索引中是否存在指定字段的mapping
        Args:
            index_name: 索引名称
            field_name: 字段名称
        Returns:
            bool: 是否存在mapping
        """
        try:
            mapping = self.es.indices.get_mapping(index=index_name)
            
            # 获取索引的properties
            index_mapping = mapping.get(index_name, {})
            mappings = index_mapping.get('mappings', {})
            properties = mappings.get('properties', {})
            
            # 检查字段是否存在
            return field_name in properties
            
        except Exception as e:
            logging.warning(f"检查索引 {index_name} 的mapping失败: {str(e)}")
            return False
    
    def add_field_mapping(self, index_name: str, field_name: str, field_type: Union[str, Dict[str, Any]] = "integer") -> bool:
        """
        为索引添加字段mapping
        Args:
            index_name: 索引名称
            field_name: 字段名称
            field_type: 字段类型（字符串如 integer/keyword）或完整 mapping 字典（如 object 类型）
        Returns:
            bool: 是否添加成功
        """
        try:
            if isinstance(field_type, dict):
                field_mapping = field_type
            else:
                field_mapping = {"type": field_type}
            mapping_body = {
                "properties": {
                    field_name: field_mapping
                }
            }
            self.es.indices.put_mapping(
                index=index_name,
                body=mapping_body
            )
            logging.info(f"为索引 {index_name} 添加字段 {field_name} mapping成功")
            return True
        except Exception as e:
            logging.error(f"为索引 {index_name} 添加字段 {field_name} mapping失败: {str(e)}")
            return False
    
    def check_field_coverage(self, index_name: str, field_name: str) -> Dict[str, Any]:
        """
        检查索引中字段的覆盖情况
        Args:
            index_name: 索引名称
            field_name: 字段名称
        Returns:
            Dict: 覆盖情况统计
        """
        try:
            # 查询总文档数
            total_response = self.es.count(index=index_name)
            total_docs = total_response["count"]
            
            if total_docs == 0:
                return {
                    "index_name": index_name,
                    "field_name": field_name,
                    "total_docs": 0,
                    "has_field": 0,
                    "missing_field": 0,
                    "coverage_rate": 100.0,
                    "field_distribution": {}
                }
            
            # 查询有字段的文档数
            has_field_response = self.es.count(
                index=index_name,
                body={
                    "query": {
                        "exists": {"field": field_name}
                    }
                }
            )
            has_field = has_field_response["count"]
            
            # 查询没有字段的文档数
            missing_field = total_docs - has_field
            
            # 查询字段值分布
            distribution = {}
            try:
                # 对于阿里云ES Serverless，使用简化的聚合查询
                agg_response = self.es.search(
                    index=index_name,
                    body={
                        "size": 0,
                        "aggs": {
                            "field_distribution": {
                                "terms": {
                                    "field": field_name,
                                    "size": 20
                                }
                            }
                        }
                    }
                )
                
                for bucket in agg_response["aggregations"]["field_distribution"]["buckets"]:
                    distribution[str(bucket["key"])] = bucket["doc_count"]
                
                # 如果有缺失字段的文档，手动添加missing统计
                if missing_field > 0:
                    distribution["missing"] = missing_field
                    
            except Exception as e:
                logging.warning(f"获取字段分布失败: {str(e)}")
                # 如果聚合查询失败，使用基础统计
                if missing_field > 0:
                    distribution["missing"] = missing_field
                if has_field > 0:
                    distribution["has_value"] = has_field
            
            result = {
                "index_name": index_name,
                "field_name": field_name,
                "total_docs": total_docs,
                "has_field": has_field,
                "missing_field": missing_field,
                "coverage_rate": round(has_field / total_docs * 100, 2) if total_docs > 0 else 0,
                "field_distribution": distribution
            }
            
            return result
            
        except Exception as e:
            logging.error(f"检查索引 {index_name} 字段 {field_name} 覆盖情况失败: {str(e)}")
            raise
    
    def supply_missing_field(self, 
                           index_name: str, 
                           field_name: str,
                           default_value: Any,
                           field_type: str = "integer",
                           batch_size: int = 1000) -> Dict[str, Any]:
        """
        为索引补充缺失的字段
        Args:
            index_name: 索引名称
            field_name: 字段名称
            default_value: 字段默认值
            field_type: 字段类型
            batch_size: 批处理大小
        Returns:
            Dict: 补充结果
        """
        try:
            logging.info(f"开始为索引 {index_name} 补充字段 {field_name}")
            
            # 1. 检查并添加mapping
            if not self.check_field_mapping(index_name, field_name):
                logging.info(f"索引 {index_name} 缺少字段 {field_name} 的mapping，正在添加...")
                if not self.add_field_mapping(index_name, field_name, field_type):
                    raise Exception(f"添加字段 {field_name} mapping失败")
            else:
                logging.info(f"索引 {index_name} 已存在字段 {field_name} 的mapping")
            
            # 2. 检查字段覆盖情况
            coverage = self.check_field_coverage(index_name, field_name)
            
            if coverage['missing_field'] == 0:
                logging.info(f"索引 {index_name} 所有文档都已有字段 {field_name}，无需补充")
                return coverage
            
            # 3. 构建更新查询
            update_query = {
                "query": {
                    "bool": {
                        "must_not": {
                            "exists": {"field": field_name}
                        }
                    }
                },
                "script": {
                    "source": f"ctx._source.{field_name} = params.default_value",
                    "lang": "painless",
                    "params": {
                        "default_value": default_value
                    }
                }
            }
            
            # 4. 执行批量更新 - 使用scroll + bulk方式避免阿里云ES Serverless的限制
            logging.info(f"开始批量更新，预计更新 {coverage['missing_field']} 个文档")
            
            try:
                # 尝试使用update_by_query（标准方式）
                update_query_copy = update_query.copy()
                update_query_copy["size"] = 100  # 小批量处理
                
                response = self.es.update_by_query(
                    index=index_name,
                    body=update_query_copy,
                    wait_for_completion=True,
                    conflicts="proceed"
                )
                
                # 检查是否有错误
                if "error" in response:
                    raise Exception(f"update_by_query失败: {response['error']}")
                
                result = {
                    "index_name": index_name,
                    "field_name": field_name,
                    "default_value": default_value,
                    "total": response.get("total", 0),
                    "updated": response.get("updated", 0),
                    "batches": response.get("batches", 0),
                    "version_conflicts": response.get("version_conflicts", 0),
                    "failures": response.get("failures", []),
                    "took": response.get("took", 0)
                }
                
            except Exception as e:
                logging.warning(f"update_by_query失败: {str(e)}")
                logging.info("使用scroll + bulk方式进行更新")
                
                # 使用scroll + bulk方式
                result = self._update_with_scroll_bulk(index_name, field_name, default_value, batch_size)
            
            logging.info(f"索引 {index_name} 字段 {field_name} 补充完成: 更新了 {result['updated']} 个文档")
            return result
            
        except Exception as e:
            logging.error(f"为索引 {index_name} 补充字段 {field_name} 失败: {str(e)}")
            raise
    
    def _update_with_scroll_bulk(self, index_name: str, field_name: str, default_value: Any, batch_size: int = 100) -> Dict[str, Any]:
        """
        使用scroll + bulk方式更新字段
        Args:
            index_name: 索引名称
            field_name: 字段名称
            default_value: 默认值
            batch_size: 批处理大小
        Returns:
            Dict: 更新结果
        """
        updated_count = 0
        total_count = 0
        failures = []
        
        try:
            # 使用scroll查询缺失字段的文档
            query_body = {
                "query": {
                    "bool": {
                        "must_not": {
                            "exists": {"field": field_name}
                        }
                    }
                },
                "size": batch_size
            }
            
            # 初始化scroll
            response = self.es.search(
                index=index_name,
                body=query_body,
                scroll='5m'
            )
            
            scroll_id = response['_scroll_id']
            hits = response['hits']['hits']
            
            while hits:
                # 构建bulk更新请求
                bulk_body = []
                for hit in hits:
                    # 更新操作
                    bulk_body.append({
                        "update": {
                            "_index": index_name,
                            "_id": hit["_id"]
                        }
                    })
                    bulk_body.append({
                        "doc": {
                            field_name: default_value
                        }
                    })
                
                # 执行bulk更新
                if bulk_body:
                    bulk_response = self.es.bulk(body=bulk_body)
                    
                    # 统计结果
                    for item in bulk_response.get("items", []):
                        if "update" in item:
                            if item["update"].get("status") in [200, 201]:
                                updated_count += 1
                            else:
                                failures.append(item["update"])
                        total_count += 1
                
                logging.info(f"已处理 {total_count} 个文档，成功更新 {updated_count} 个")
                
                # 获取下一批数据
                response = self.es.scroll(scroll_id=scroll_id, scroll='5m')
                hits = response['hits']['hits']
            
            # 清理scroll
            try:
                self.es.clear_scroll(scroll_id=scroll_id)
            except:
                pass
            
            return {
                "index_name": index_name,
                "field_name": field_name,
                "default_value": default_value,
                "total": total_count,
                "updated": updated_count,
                "failures": failures,
                "method": "scroll_bulk"
            }
            
        except Exception as e:
            logging.error(f"scroll + bulk更新失败: {str(e)}")
            raise
    
    def supply_field_for_indexes(self,
                               index_names: List[str],
                               field_name: str,
                               default_value: Any,
                               field_type: str = "integer",
                               batch_size: int = 1000,
                               dry_run: bool = False) -> Dict[str, Any]:
        """
        为多个索引批量补充字段
        Args:
            index_names: 索引名称列表
            field_name: 字段名称
            default_value: 字段默认值
            field_type: 字段类型
            batch_size: 批处理大小
            dry_run: 是否为试运行
        Returns:
            Dict: 批量处理结果
        """
        results = {}
        summary = {
            "total_indexes": len(index_names),
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "total_docs_updated": 0
        }
        
        for index_name in index_names:
            print(f"\n{'='*60}")
            print(f"处理索引: {index_name}")
            print(f"{'='*60}")
            
            try:
                # 检查覆盖情况
                coverage = self.check_field_coverage(index_name, field_name)
                
                print(f"总文档数: {coverage['total_docs']:,}")
                print(f"已有字段: {coverage['has_field']:,}")
                print(f"缺失字段: {coverage['missing_field']:,}")
                print(f"覆盖率: {coverage['coverage_rate']}%")
                
                if coverage['total_docs'] == 0:
                    print("⏭️  索引为空，跳过处理")
                    results[index_name] = {"status": "skipped", "reason": "empty_index"}
                    summary["skipped_count"] += 1
                    continue
                
                if coverage['missing_field'] == 0:
                    print("✅ 所有文档都已有该字段，跳过处理")
                    results[index_name] = {"status": "skipped", "reason": "no_missing_field"}
                    summary["skipped_count"] += 1
                    continue
                
                if dry_run:
                    print(f"🔍 试运行模式：将为 {coverage['missing_field']:,} 个文档添加 {field_name}={default_value}")
                    results[index_name] = {"status": "dry_run", "coverage": coverage}
                    continue
                
                # 执行补充
                result = self.supply_missing_field(
                    index_name=index_name,
                    field_name=field_name,
                    default_value=default_value,
                    field_type=field_type,
                    batch_size=batch_size
                )
                
                print(f"✅ 成功更新 {result['updated']:,} 个文档")
                results[index_name] = {"status": "success", "result": result}
                summary["success_count"] += 1
                summary["total_docs_updated"] += result['updated']
                
            except Exception as e:
                logging.error(f"处理索引 {index_name} 失败: {str(e)}")
                print(f"❌ 处理失败: {str(e)}")
                results[index_name] = {"status": "failed", "error": str(e)}
                summary["failed_count"] += 1
        
        # 打印总结
        print(f"\n{'='*60}")
        print("批量处理总结")
        print(f"{'='*60}")
        print(f"总索引数: {summary['total_indexes']}")
        print(f"成功: {summary['success_count']}")
        print(f"失败: {summary['failed_count']}")
        print(f"跳过: {summary['skipped_count']}")
        if not dry_run:
            print(f"总更新文档数: {summary['total_docs_updated']:,}")
        
        return {
            "summary": summary,
            "details": results
        }
    
    def supply_dynamic_fields(self, 
                            index_name: str, 
                            field_names: List[str],
                            batch_size: int = 100,
                            force: bool = False) -> Dict[str, Any]:
        """
        为索引补充需要动态计算的字段（如from_type_norm, tags）
        Args:
            index_name: 索引名称
            field_names: 需要补充的字段名称列表
            batch_size: 批处理大小
            force: 是否强制更新已有字段（默认False，只更新缺失字段）
        Returns:
            Dict: 更新结果
        """
        logging.info(f"开始为索引 {index_name} 补充动态字段: {field_names}")
        
        # 支持的动态字段映射（简单类型为 {"type": "keyword"}，对象类型为完整 mapping）
        dynamic_field_mappings = {
            "from_type_norm": {"type": "keyword"},
            "tags": {"type": "keyword"},
            "dataset": {"type": "keyword"},
            "primary_category": {
                "type": "object",
                "properties": {
                    "category_path": {"type": "keyword"},
                    "category_ids": {"type": "keyword"},
                    "cate1_name": {"type": "keyword"},
                    "cate1_id": {"type": "keyword"},
                    "cate2_name": {"type": "keyword"},
                    "cate2_id": {"type": "keyword"},
                    "cate3_name": {"type": "keyword"},
                    "cate3_id": {"type": "keyword"},
                    "cate4_name": {"type": "keyword"},
                    "cate4_id": {"type": "keyword"}
                }
            }
        }
        
        # 检查并添加字段mapping
        for field_name in field_names:
            if field_name not in dynamic_field_mappings:
                raise ValueError(f"不支持的动态字段: {field_name}")
            field_config = dynamic_field_mappings[field_name]
            if not self.check_field_mapping(index_name, field_name):
                # 对象类型传完整 mapping，简单类型传 type 字符串
                mapping_arg = field_config if isinstance(field_config, dict) and "properties" in field_config else field_config.get("type", "keyword")
                self.add_field_mapping(index_name, field_name, mapping_arg)
        
        # 构建查询条件
        query = {"query": build_missing_field_query(field_names, force=force)}
        if force:
            logging.info(f"强制模式：将重新计算所有文档的 {field_names} 字段")

        # 使用scroll API处理数据
        #
        # `_source` 必须排除向量：这些索引每条带两个 1024 维 embedding，
        # 默认 batch_size=1000 时一次 scroll 响应能有几十 MB，纯属白传
        # （动态字段只用到 from_type / ext_info.from_file_name / keywords）。
        try:
            response = self.es.search(
                index=index_name,
                body=query,
                _source_excludes=SOURCE_EXCLUDES,
                scroll='5m',
                size=batch_size
            )
            
            scroll_id = response['_scroll_id']
            hits = response['hits']['hits']
            total_count = 0
            updated_count = 0
            failures = []
            
            while hits:
                # 准备bulk更新操作
                bulk_body = []
                
                for hit in hits:
                    doc = hit['_source']
                    doc['_id'] = hit['_id']
                    
                    # 计算动态字段值
                    update_fields = {}
                    
                    if "from_type_norm" in field_names:
                        if force or "from_type_norm" not in doc or not doc.get("from_type_norm"):
                            try:
                                from_type_norm = get_from_norm_type(doc)
                                update_fields["from_type_norm"] = from_type_norm
                            except Exception as e:
                                logging.warning(f"生成from_type_norm失败 for doc {doc.get('_id')}: {str(e)}")
                                update_fields["from_type_norm"] = "其他"
                    
                    if "tags" in field_names:
                        if force or "tags" not in doc or not doc.get("tags"):
                            keywords = doc.get("keywords", [])
                            if isinstance(keywords, list):
                                update_fields["tags"] = keywords
                            else:
                                update_fields["tags"] = []
                    
                    if "dataset" in field_names:
                        if force or "dataset" not in doc or not doc.get("dataset"):
                            # dataset字段的值就是索引名称
                            update_fields["dataset"] = index_name
                    
                    if "primary_category" in field_names:
                        if force or "primary_category" not in doc or not doc.get("primary_category"):
                            # 缺失时补充默认分组
                            update_fields["primary_category"] = DEFAULT_PRIMARY_CATEGORY.copy()
                    
                    # 如果有需要更新的字段，添加到bulk操作中
                    if update_fields:
                        bulk_body.append({
                            "update": {
                                "_index": index_name,
                                "_id": hit["_id"]
                            }
                        })
                        bulk_body.append({
                            "doc": update_fields
                        })
                
                # 执行bulk更新
                if bulk_body:
                    try:
                        bulk_response = self.es.bulk(body=bulk_body)
                        
                        # 统计结果
                        for item in bulk_response.get("items", []):
                            if "update" in item:
                                if item["update"].get("status") in [200, 201]:
                                    updated_count += 1
                                else:
                                    failures.append(item["update"])
                    except Exception as e:
                        logging.error(f"批量更新失败: {str(e)}")
                        failures.append({"error": str(e), "batch_size": len(bulk_body)//2})
                
                total_count += len(hits)
                logging.info(f"已处理 {total_count} 个文档，成功更新 {updated_count} 个")
                
                # 获取下一批数据
                response = self.es.scroll(scroll_id=scroll_id, scroll='5m')
                hits = response['hits']['hits']
            
            # 清理scroll
            try:
                self.es.clear_scroll(scroll_id=scroll_id)
            except:
                pass
            
            return {
                "index_name": index_name,
                "field_names": field_names,
                "total": total_count,
                "updated": updated_count,
                "failures": failures,
                "method": "dynamic_scroll_bulk"
            }
            
        except Exception as e:
            logging.error(f"动态字段补充失败: {str(e)}")
            raise
    
    def supply_dynamic_fields_for_indexes(self,
                                        index_names: List[str],
                                        field_names: List[str],
                                        batch_size: int = 100,
                                        dry_run: bool = False,
                                        force: bool = False) -> Dict[str, Any]:
        """
        为多个索引批量补充动态字段
        Args:
            index_names: 索引名称列表
            field_names: 需要补充的字段名称列表
            batch_size: 批处理大小
            dry_run: 是否为试运行
            force: 是否强制更新已有字段（默认False，只更新缺失字段）
        Returns:
            Dict: 批量处理结果
        """
        results = {}
        summary = {
            "total_indexes": len(index_names),
            "success_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "total_docs_updated": 0
        }
        
        for index_name in index_names:
            print(f"\n{'='*60}")
            print(f"处理索引: {index_name}")
            print(f"字段: {', '.join(field_names)}")
            print(f"{'='*60}")
            
            try:
                # 检查索引是否存在
                if not self.es.indices.exists(index=index_name):
                    print(f"⏭️  索引 {index_name} 不存在，跳过处理")
                    results[index_name] = {"status": "skipped", "reason": "index_not_exists"}
                    summary["skipped_count"] += 1
                    continue
                
                # 获取文档总数
                total_response = self.es.count(index=index_name)
                total_docs = total_response["count"]
                
                if total_docs == 0:
                    print("⏭️  索引为空，跳过处理")
                    results[index_name] = {"status": "skipped", "reason": "empty_index"}
                    summary["skipped_count"] += 1
                    continue
                
                # 统计需要处理的文档数
                # 预估条数和实际处理必须用**同一个**查询构造器，否则 dry-run 报的数
                # 和真正会改的数不一致（这里原来各写了一份 must_not，两处都是错的）
                target_docs = self.es.count(
                    index=index_name,
                    body={"query": build_missing_field_query(field_names, force=force)}
                )["count"]
                print(f"总文档数: {total_docs:,}")
                if force:
                    print(f"需要重新计算的文档数（强制模式）: {target_docs:,}")
                else:
                    print(f"需要补充字段的文档数: {target_docs:,}")
                    # 每个字段单独报一次，避免「合起来 N 条」掩盖某个字段其实一条都没补
                    for field_name in field_names:
                        n = self.es.count(
                            index=index_name,
                            body={"query": build_missing_field_query([field_name])}
                        )["count"]
                        print(f"  其中缺 {field_name}: {n:,}")
                
                if target_docs == 0:
                    print("✅ 没有需要处理的文档，跳过处理")
                    results[index_name] = {"status": "skipped", "reason": "no_docs_to_process"}
                    summary["skipped_count"] += 1
                    continue
                
                if dry_run:
                    mode_text = "强制更新" if force else "补充"
                    print(f"🔍 试运行模式：将为 {target_docs:,} 个文档{mode_text}字段 {', '.join(field_names)}")
                    results[index_name] = {"status": "dry_run", "target_docs": target_docs}
                    continue
                
                # 执行补充
                result = self.supply_dynamic_fields(
                    index_name=index_name,
                    field_names=field_names,
                    batch_size=batch_size,
                    force=force
                )
                
                print(f"✅ 成功更新 {result['updated']:,} 个文档")
                results[index_name] = {"status": "success", "result": result}
                summary["success_count"] += 1
                summary["total_docs_updated"] += result['updated']
                
            except Exception as e:
                logging.error(f"处理索引 {index_name} 失败: {str(e)}")
                print(f"❌ 处理失败: {str(e)}")
                results[index_name] = {"status": "failed", "error": str(e)}
                summary["failed_count"] += 1
        
        # 打印总结
        print(f"\n{'='*60}")
        print("动态字段补充总结")
        print(f"{'='*60}")
        print(f"总索引数: {summary['total_indexes']}")
        print(f"成功: {summary['success_count']}")
        print(f"失败: {summary['failed_count']}")
        print(f"跳过: {summary['skipped_count']}")
        if not dry_run:
            print(f"总更新文档数: {summary['total_docs_updated']:,}")
        
        return {
            "summary": summary,
            "details": results
        }

def main():
    parser = argparse.ArgumentParser(description="自动补充ES索引中缺失的字段")
    parser.add_argument("--config", required=True, help="ES配置文件路径")
    parser.add_argument("--index", help="索引名称，支持'all'获取所有索引")
    parser.add_argument("--indexes", help="多个索引名称，用逗号分隔")
    parser.add_argument("--field", default="del_flag", help="字段名称 (默认: del_flag)")
    parser.add_argument("--value", type=int, default=0, help="字段默认值 (默认: 0)")
    parser.add_argument("--type", default="integer", help="字段类型 (默认: integer)")
    parser.add_argument("--batch-size", type=int, default=1000, help="批处理大小 (默认: 1000)")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式，只检查不更新")
    parser.add_argument("--exclude-system", action="store_true", default=True, help="排除系统索引")
    parser.add_argument("--dynamic-fields", help="动态字段名称，用逗号分隔 (支持: from_type_norm,tags,dataset,primary_category)")
    parser.add_argument("--mode", default="static", choices=["static", "dynamic"], help="字段补充模式 (默认: static)")
    parser.add_argument("--force", action="store_true", help="强制更新已有字段（仅对动态模式有效）")
    
    args = parser.parse_args()
    
    try:
        # 初始化字段补充工具
        supplier = FieldSupplier(args.config)
        
        # 确定要处理的索引
        if args.index:
            if args.index.lower() == 'all':
                index_names = supplier.get_all_indexes(exclude_system=args.exclude_system)
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
        
        # 根据模式执行不同的字段补充
        if args.mode == "dynamic":
            # 动态字段模式
            if not args.dynamic_fields:
                parser.error("动态模式下必须指定 --dynamic-fields 参数")
            
            field_names = [name.strip() for name in args.dynamic_fields.split(',')]
            supported_fields = ["from_type_norm", "tags", "dataset", "primary_category"]
            
            for field_name in field_names:
                if field_name not in supported_fields:
                    parser.error(f"不支持的动态字段: {field_name}，支持的字段: {', '.join(supported_fields)}")
            
            result = supplier.supply_dynamic_fields_for_indexes(
                index_names=index_names,
                field_names=field_names,
                batch_size=args.batch_size,
                dry_run=args.dry_run,
                force=args.force
            )
        else:
            # 静态字段模式（原有逻辑）
            result = supplier.supply_field_for_indexes(
                index_names=index_names,
                field_name=args.field,
                default_value=args.value,
                field_type=args.type,
                batch_size=args.batch_size,
                dry_run=args.dry_run
            )
        
        print(f"\n🎉 处理完成！")
        
    except Exception as e:
        logging.error(f"执行失败: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main() 