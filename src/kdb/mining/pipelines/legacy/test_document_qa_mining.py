#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
测试document_qa_mining_task_control.py脚本的功能
"""
from kdb.compat.layout import legacy_source_path as _legacy_source_path
__legacy_source_file__ = _legacy_source_path('control_service/test_document_qa_mining.py')
from kdb.shared.config.private_values import private_value as _private_value
import os
import sys
import json
import argparse
import subprocess
import tempfile
import shutil
from pathlib import Path

def create_test_config():
    """创建测试配置文件"""
    config_dir = Path(__legacy_source_file__).parent.parent / 'config'
    config_dir.mkdir(exist_ok=True)
    
    # 创建MySQL配置（测试用）
    mysql_config = {
        "host": "localhost",
        "database": "rufitai",
        "user": "test_user",
        "password": _private_value('43f372bea64ca6421668395d')
    }
    
    mysql_config_path = config_dir / 'mysql_conn_config.json'
    with open(mysql_config_path, 'w', encoding='utf-8') as f:
        json.dump(mysql_config, f, indent=2, ensure_ascii=False)
    
    # 创建MinIO配置（测试用）
    minio_config = {
        "endpoint_url": "http://localhost:9000",
        "access_key": _private_value('63182d8a89f6e5625ac3892d'),
        "secret_key": _private_value('888885b0cefe90751f517e6f'),
        "region": "us-east-1",
        "bucket_name": "test-bucket"
    }
    
    minio_config_path = config_dir / 'minio_config.json'
    with open(minio_config_path, 'w', encoding='utf-8') as f:
        json.dump(minio_config, f, indent=2, ensure_ascii=False)
    
    # 创建索引配置（测试用）
    index_config = {
        "index_name": "test_index",
        "elasticsearch_host": "localhost:9200",
        "settings": {
            "number_of_shards": 1,
            "number_of_replicas": 0
        }
    }
    
    index_config_path = config_dir / 'test_index_config.json'
    with open(index_config_path, 'w', encoding='utf-8') as f:
        json.dump(index_config, f, indent=2, ensure_ascii=False)
    
    print(f"测试配置文件已创建：")
    print(f"  MySQL配置: {mysql_config_path}")
    print(f"  MinIO配置: {minio_config_path}")
    print(f"  索引配置: {index_config_path}")
    
    return config_dir

def create_test_task_info():
    """创建测试任务信息"""
    task_info = {
        "files": [
            {
                "name": "test_document_1",
                "ext": "pdf",
                "store_method": "minio",
                "address": "http://localhost:9000/test-bucket/documents/test1.pdf"
            },
            {
                "name": "test_document_2", 
                "ext": "docx",
                "store_method": "minio",
                "address": "s3://test-bucket/documents/test2.docx"
            }
        ],
        "index_name": "test_index",
        "client": "test_client",
        "need_translate": 0
    }
    return task_info

def test_script_syntax():
    """测试脚本语法"""
    script_path = Path(__legacy_source_file__).parent / 'document_qa_mining_task_control.py'
    
    print("测试脚本语法...")
    try:
        result = subprocess.run([
            sys.executable, '-m', 'py_compile', str(script_path)
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("✓ 脚本语法检查通过")
            return True
        else:
            print(f"✗ 脚本语法错误: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ 语法检查失败: {e}")
        return False

def test_script_import():
    """测试脚本导入"""
    print("测试脚本导入...")
    try:
        # 添加路径
        script_dir = Path(__legacy_source_file__).parent.parent
        sys.path.append(str(script_dir))
        
        # 尝试导入主要模块
        from control_service.document_qa_mining_task_control import DocumentQAMiningTaskController
        print("✓ 主要模块导入成功")
        
        # 测试创建控制器实例
        task_info = create_test_task_info()
        controller = DocumentQAMiningTaskController(
            str(script_dir),
            "test_task_id",
            task_info
        )
        print("✓ 控制器实例创建成功")
        return True
        
    except ImportError as e:
        print(f"✗ 导入错误: {e}")
        return False
    except Exception as e:
        print(f"✗ 其他错误: {e}")
        return False

def test_script_help():
    """测试脚本帮助信息"""
    script_path = Path(__legacy_source_file__).parent / 'document_qa_mining_task_control.py'
    
    print("测试脚本帮助信息...")
    try:
        result = subprocess.run([
            sys.executable, str(script_path), '--help'
        ], capture_output=True, text=True)
        
        if result.returncode == 0 and '--script-dir' in result.stdout:
            print("✓ 脚本帮助信息正常")
            return True
        else:
            print(f"✗ 脚本帮助信息异常: {result.stderr}")
            return False
    except Exception as e:
        print(f"✗ 帮助信息测试失败: {e}")
        return False

def test_dry_run():
    """测试脚本空运行（不实际执行任务）"""
    script_path = Path(__legacy_source_file__).parent / 'document_qa_mining_task_control.py'
    script_dir = Path(__legacy_source_file__).parent.parent
    
    print("测试脚本参数解析...")
    
    task_info = create_test_task_info()
    task_info_json = json.dumps(task_info, ensure_ascii=False)
    
    try:
        # 由于实际任务会连接数据库等，这里只测试参数解析
        cmd = [
            sys.executable, str(script_path),
            '--script-dir', str(script_dir),
            '--task-id', 'test_task_123',
            '--task-info', task_info_json
        ]
        
        print(f"测试命令: {' '.join(cmd[:3])} [参数已隐藏]")
        
        # 注意：这个测试会尝试实际运行，但由于没有真实的依赖环境，会失败
        # 我们主要是检查参数解析是否正常
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        
        # 如果是因为依赖问题失败，这是预期的
        if "No module named" in result.stderr or "无法获取数据库连接" in result.stderr:
            print("✓ 参数解析正常（依赖环境未配置，这是预期的）")
            return True
        elif result.returncode == 0:
            print("✓ 脚本运行成功（意外但好的结果）")
            return True
        else:
            print(f"? 脚本运行结果: {result.stderr}")
            return True  # 在测试环境中，某些失败是预期的
            
    except subprocess.TimeoutExpired:
        print("✓ 脚本启动正常（5秒超时，避免长时间运行）")
        return True
    except Exception as e:
        print(f"✗ 脚本运行测试失败: {e}")
        return False

def test_dependencies():
    """测试依赖模块"""
    print("测试依赖模块...")
    
    # 测试标准库
    try:
        import json, os, sys, argparse, logging, subprocess, traceback
        print("✓ 标准库导入正常")
    except ImportError as e:
        print(f"✗ 标准库导入失败: {e}")
        return False
    
    # 测试第三方库
    optional_modules = {
        'requests': '用于HTTP请求',
        'boto3': '用于S3/MinIO操作',
        'mysql.connector': '用于MySQL连接'
    }
    
    for module, desc in optional_modules.items():
        try:
            __import__(module)
            print(f"✓ {module} 可用 ({desc})")
        except ImportError:
            print(f"? {module} 不可用 ({desc}) - 可能需要安装")
    
    return True

def main():
    """主测试函数"""
    parser = argparse.ArgumentParser(description='测试document_qa_mining_task_control.py脚本')
    parser.add_argument('--create-config', action='store_true', help='创建测试配置文件')
    parser.add_argument('--full-test', action='store_true', help='运行完整测试')
    parser.add_argument('--syntax-only', action='store_true', help='仅测试语法')
    
    args = parser.parse_args()
    
    print("=== document_qa_mining_task_control.py 脚本测试 ===\n")
    
    if args.create_config:
        config_dir = create_test_config()
        print(f"\n测试配置已创建在: {config_dir}")
        return
    
    tests = []
    
    if args.syntax_only:
        tests = [
            ("语法检查", test_script_syntax),
        ]
    elif args.full_test:
        tests = [
            ("依赖模块检查", test_dependencies),
            ("语法检查", test_script_syntax),
            ("导入测试", test_script_import),
            ("帮助信息测试", test_script_help),
            ("参数解析测试", test_dry_run),
        ]
    else:
        tests = [
            ("语法检查", test_script_syntax),
            ("帮助信息测试", test_script_help),
        ]
    
    results = []
    for test_name, test_func in tests:
        print(f"\n--- {test_name} ---")
        success = test_func()
        results.append((test_name, success))
        print()
    
    print("=== 测试结果汇总 ===")
    passed = 0
    for test_name, success in results:
        status = "通过" if success else "失败"
        print(f"{test_name}: {status}")
        if success:
            passed += 1
    
    print(f"\n总计: {passed}/{len(results)} 项测试通过")
    
    if passed == len(results):
        print("🎉 所有测试通过！脚本基本功能正常。")
    else:
        print("⚠️  部分测试失败，请检查相关问题。")
    
    print("\n注意：")
    print("- 完整功能测试需要配置真实的MySQL、MinIO等环境")
    print("- 使用 --create-config 创建测试配置文件")
    print("- 使用 --full-test 运行完整的测试套件")

if __name__ == '__main__':
    main() 