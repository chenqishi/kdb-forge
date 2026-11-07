#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量更新ES索引中缺失的del_flag字段
Author: Assistant
Date: 2025-01-30
"""

import json
import logging
import argparse
from typing import List, Optional
from knowledge_interface_tools.es_search_interface import EsSearchInterface

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def update_del_flag_for_index(config_path: str, 
                             index_name: str, 
                             default_value: int = 0,
                             batch_size: int = 1000,
                             dry_run: bool = False) -> dict:
    """
    为指定索引更新del_flag字段
    Args:
        config_path: ES配置文件路径
        index_name: 索引名称
        default_value: del_flag默认值
        batch_size: 批处理大小
        dry_run: 是否为试运行（只检查不更新）
    Returns:
        dict: 更新结果
    """
    try:
        # 初始化ES接口
        es_interface = EsSearchInterface(config_path=config_path, index_name=index_name)
        
        # 检查当前覆盖情况
        logging.info(f"检查索引 {index_name} 的del_flag覆盖情况...")
        coverage = es_interface.check_del_flag_coverage()
        
        print(f"\n=== 索引 {index_name} del_flag 覆盖情况 ===")
        print(f"总文档数: {coverage['total_docs']:,}")
        print(f"已有del_flag: {coverage['has_del_flag']:,}")
        print(f"缺失del_flag: {coverage['missing_del_flag']:,}")
        print(f"覆盖率: {coverage['coverage_rate']}%")
        print(f"del_flag值分布: {coverage['del_flag_distribution']}")
        
        if coverage['missing_del_flag'] == 0:
            print("✅ 所有文档都已有del_flag字段，无需更新")
            return coverage
        
        if dry_run:
            print(f"🔍 试运行模式：将为 {coverage['missing_del_flag']:,} 个文档添加 del_flag={default_value}")
            return coverage
        
        # 确认更新
        confirm = input(f"\n是否为 {coverage['missing_del_flag']:,} 个文档添加 del_flag={default_value}? (y/N): ")
        if confirm.lower() != 'y':
            print("❌ 用户取消操作")
            return coverage
        
        # 执行更新
        logging.info(f"开始批量更新，批处理大小: {batch_size}")
        result = es_interface.update_missing_del_flag(
            default_value=default_value,
            batch_size=batch_size
        )
        
        print(f"\n=== 更新完成 ===")
        print(f"处理文档数: {result['total']:,}")
        print(f"成功更新数: {result['updated']:,}")
        print(f"批次数: {result['batches']}")
        print(f"版本冲突: {result['version_conflicts']}")
        print(f"耗时: {result['took']}ms")
        
        if result['failures']:
            print(f"⚠️  失败数: {len(result['failures'])}")
            for failure in result['failures'][:5]:  # 只显示前5个失败
                print(f"   - {failure}")
        
        # 再次检查覆盖情况
        logging.info("验证更新结果...")
        final_coverage = es_interface.check_del_flag_coverage()
        print(f"\n=== 更新后覆盖情况 ===")
        print(f"覆盖率: {final_coverage['coverage_rate']}%")
        print(f"剩余缺失: {final_coverage['missing_del_flag']:,}")
        
        return result
        
    except Exception as e:
        logging.error(f"更新失败: {str(e)}")
        raise

def update_multiple_indexes(config_path: str, 
                          index_names: List[str],
                          default_value: int = 0,
                          batch_size: int = 1000,
                          dry_run: bool = False):
    """
    批量更新多个索引的del_flag字段
    """
    results = {}
    
    for index_name in index_names:
        print(f"\n{'='*50}")
        print(f"处理索引: {index_name}")
        print(f"{'='*50}")
        
        try:
            result = update_del_flag_for_index(
                config_path=config_path,
                index_name=index_name,
                default_value=default_value,
                batch_size=batch_size,
                dry_run=dry_run
            )
            results[index_name] = {"status": "success", "result": result}
        except Exception as e:
            logging.error(f"索引 {index_name} 更新失败: {str(e)}")
            results[index_name] = {"status": "failed", "error": str(e)}
    
    # 输出总结
    print(f"\n{'='*50}")
    print("批量更新总结")
    print(f"{'='*50}")
    
    for index_name, result in results.items():
        status = "✅ 成功" if result["status"] == "success" else "❌ 失败"
        print(f"{index_name}: {status}")
        if result["status"] == "failed":
            print(f"   错误: {result['error']}")

def main():
    parser = argparse.ArgumentParser(description="批量更新ES索引中的del_flag字段")
    parser.add_argument("--config", required=True, help="ES配置文件路径")
    parser.add_argument("--index", help="单个索引名称")
    parser.add_argument("--indexes", help="多个索引名称，用逗号分隔")
    parser.add_argument("--value", type=int, default=0, help="del_flag默认值 (默认: 0)")
    parser.add_argument("--batch-size", type=int, default=1000, help="批处理大小 (默认: 1000)")
    parser.add_argument("--dry-run", action="store_true", help="试运行模式，只检查不更新")
    
    args = parser.parse_args()
    
    if not args.index and not args.indexes:
        parser.error("必须指定 --index 或 --indexes 参数")
    
    try:
        if args.index:
            # 单个索引
            update_del_flag_for_index(
                config_path=args.config,
                index_name=args.index,
                default_value=args.value,
                batch_size=args.batch_size,
                dry_run=args.dry_run
            )
        else:
            # 多个索引
            index_names = [name.strip() for name in args.indexes.split(',')]
            update_multiple_indexes(
                config_path=args.config,
                index_names=index_names,
                default_value=args.value,
                batch_size=args.batch_size,
                dry_run=args.dry_run
            )
            
    except Exception as e:
        logging.error(f"执行失败: {str(e)}")
        exit(1)

if __name__ == "__main__":
    main() 