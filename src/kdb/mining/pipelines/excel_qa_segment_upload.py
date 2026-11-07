#!/usr/bin/env python
# -*- coding:utf8 -*-
"""
Excel QA数据上传任务控制脚本
基于原始的insert_audit_excel.sh脚本改造
支持从远程文件系统（MinIO等）下载Excel文件并上传QA数据
"""
from kdb.shared.config.private_values import private_value as _private_value
import os
import sys
import json
import argparse
import logging
import shlex
import subprocess
import traceback
from pathlib import Path

from kdb.shared.config.paths import SOURCE_ROOT, subprocess_env

from kdb.mining.tasks.minio_downloader import MinioDownloader
from kdb.mining.tasks.task_status_updater import TaskStatusUpdater
from kdb.mining.transformations.schema_trans import classify_excel_upload
from kdb.shared.config.legacy_config import GLOBAL_CONFIG

class ExcelQASegmentUploadController:
    """Excel QA数据上传任务控制器"""
    
    def __init__(self, script_dir, task_id, task_info):
        """初始化控制器"""
        self.script_dir = script_dir
        self.task_id = task_id
        self.task_info = task_info
        
        # 配置路径
        self.config_dir = os.path.join(script_dir, 'config')
        self.mysql_config_path = os.path.join(self.config_dir, 'mysql_conn_config.json')
        self.minio_config_path = os.path.join(self.config_dir, 'minio_config.json')
        
        # 工作目录
        self.data_dir = os.path.join(script_dir, 'data/off_task_data', task_id)
        self.log_dir = os.path.join(script_dir, 'log/off_task_log', task_id)
        
        # 确保目录存在
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.log_dir, exist_ok=True)
        
        # 初始化工具
        self.downloader = MinioDownloader(self.minio_config_path)
        self.status_updater = TaskStatusUpdater(self.mysql_config_path)
        
        # 任务配置
        self.files = task_info.get('files', [])
        self.index_name = task_info.get('index_name', '')
        self.client = task_info.get('client', self.index_name)
        # 确保 category_id 是字符串类型（避免纯数字被解析为 int）
        category_id = task_info.get('category_id')
        self.category_id = str(category_id) if category_id is not None else None
        self.category_name = task_info.get('category_name')
        
        # 中间文件路径
        self.downloaded_excel_path = None  # 将在下载时设置
        self.json_file_path = os.path.join(self.data_dir, f'audit_search_json_{self.task_id}.txt')
        self.image_processed_json_file_path = os.path.join(
            self.data_dir, f'audit_search_image_processed_{self.task_id}.txt'
        )
        self.index_input_file_path = self.json_file_path
        self._index_config_path = None
        self.excel_classification = {}
        self.excel_process_mode = None
        self.document_fallback_completed = False
        
        # 设置日志
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志"""
        # 清除现有的handler，避免重复配置
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # 配置日志输出到标准输出，这样会被任务日志文件捕获
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(sys.stdout)  # 确保输出到stdout
            ],
            force=True  # 强制重新配置
        )
    
    def _get_index_config_path(self):
        """获取索引配置文件路径"""
        if self._index_config_path:
            return self._index_config_path
        
        index_config_path = os.path.join(self.config_dir, f'{self.index_name}_config.json')
        if not os.path.exists(index_config_path):
            logging.warning(f"索引配置文件不存在: {index_config_path}，尝试使用默认配置")
            default_configs = [
                os.path.join(self.config_dir, 'config_for_search_index.json'),
                os.path.join(self.config_dir, 'index_config.json')
            ]
            for config in default_configs:
                if os.path.exists(config):
                    index_config_path = config
                    break
            else:
                logging.error("找不到可用的索引配置文件")
                return None
        
        self._index_config_path = index_config_path
        return self._index_config_path
    
    def _run_command(self, cmd, stage_name):
        """运行命令并记录日志"""
        log_file = os.path.join(self.log_dir, f'{stage_name}.log')
        cmd_for_log = shlex.join(cmd) if isinstance(cmd, (list, tuple)) else cmd
        logging.info(f"执行阶段: {stage_name}")
        logging.info(f"工作目录: {self.script_dir}")
        logging.info("=" * 80)
        logging.info(f"执行命令: {cmd_for_log}")
        logging.info("=" * 80)
        
        try:
            with open(log_file, 'w', encoding='utf-8') as f:
                result = subprocess.run(
                    cmd, 
                    shell=isinstance(cmd, str),
                    stdout=f, 
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=self.script_dir,
                    env=subprocess_env(),
                )
            
            # 读取命令输出日志，打印一些关键信息
            if os.path.exists(log_file):
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_content = f.read(500)
                    if log_content.strip():
                        logging.info(f"阶段 {stage_name} 命令输出（前500字符）:")
                        logging.info(log_content[:500])
                    else:
                        logging.warning(f"阶段 {stage_name} 命令没有输出")
            
            if result.returncode == 0:
                logging.info(f"阶段 {stage_name} 执行成功，返回码: {result.returncode}")
                return True
            else:
                logging.error(f"阶段 {stage_name} 执行失败，返回码: {result.returncode}")
                # 如果有错误日志，显示更多信息
                if os.path.exists(log_file):
                    with open(log_file, 'rb') as f:
                        f.seek(max(os.path.getsize(log_file) - 4000, 0))
                        error_content = f.read(4000).decode('utf-8', errors='replace')
                        if error_content.strip():
                            logging.error(f"错误详情: {error_content[-1000:]}")  # 显示最后1000字符
                return False
                
        except Exception as e:
            logging.error(f"执行阶段 {stage_name} 时发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_1_download_files(self):
        """阶段1：文件下载"""
        self.status_updater.update_task_stage(self.task_id, "file_download")
        logging.info("开始阶段1：文件下载")
        
        try:
            if not self.files or len(self.files) == 0:
                logging.error("没有指定要下载的文件")
                return False
            
            # 只处理第一个文件（Excel文件）
            file_info = self.files[0]
            file_name = file_info.get('name', '')
            file_ext = file_info.get('ext', '')
            store_method = file_info.get('store_method', '')
            address = file_info.get('address', '')
            
            if not file_name or not address:
                logging.error(f"文件信息不完整: {file_info}")
                return False
            
            # 生成本地文件路径
            local_filename = f"{file_name}.{file_ext}" if file_ext else file_name
            local_path = os.path.join(self.data_dir, local_filename)
            
            # 下载文件
            logging.info(f"开始下载文件: {file_name}")
            logging.info(f"存储方式: {store_method}, 地址: {address}")
            logging.info(f"本地路径: {local_path}")
            
            success = self.downloader.download_file(file_info, local_path)
            
            if success and os.path.exists(local_path):
                self.downloaded_excel_path = local_path
                logging.info(f"文件下载成功: {file_name} -> {local_path}")
                return True
            else:
                logging.error(f"文件下载失败: {file_name}")
                return False
            
        except Exception as e:
            logging.error(f"文件下载阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def stage_2_excel_to_json(self):
        """阶段2：Excel转JSON"""
        self.status_updater.update_task_stage(self.task_id, "excel_to_json")
        logging.info("开始阶段2：Excel转JSON")
        
        try:
            if not self.downloaded_excel_path or not os.path.exists(self.downloaded_excel_path):
                logging.error(f"Excel文件不存在: {self.downloaded_excel_path}")
                return False

            self.excel_classification = classify_excel_upload(self.downloaded_excel_path)
            self.excel_process_mode = self.excel_classification.get("mode", "unstructured_excel")
            logging.info(
                "Excel识别结果: mode=%s, confidence=%s, reason=%s, mapping=%s",
                self.excel_process_mode,
                self.excel_classification.get("confidence"),
                self.excel_classification.get("reason"),
                self.excel_classification.get("mapping"),
            )

            if self.excel_process_mode == "unstructured_excel":
                logging.info("Excel无法映射为QA表，切换到document_qa_segment_mining非结构化文档流程")
                success = self._run_unstructured_document_fallback()
                self.document_fallback_completed = success
                return success
            
            # 准备extra_field_name_dict：task_info排除files部分
            extra_field_name_dict = {k: v for k, v in self.task_info.items() if k != 'files'}
            logging.info(f"extra_field_name_dict: {extra_field_name_dict}")
            if "audit_result" not in extra_field_name_dict:
                extra_field_name_dict['audit_result'] = 1
            
            # 将字典转为JSON字符串
            extra_field_json = json.dumps(extra_field_name_dict, ensure_ascii=False)
        
            # 使用参数列表执行，避免文件名里的空格被 shell 拆分。
            cmd = [
                sys.executable,
                '-m', 'kdb.mining.transformations.schema_trans',
                "trans_web_excel_to_json_file",
                f"--excel_file={self.downloaded_excel_path}",
                f"--output_file={self.json_file_path}",
                "--list_field_names=synonyms_title,supply_info_query",
                f"--extra_field_name_dict={extra_field_json}",
            ]

            
            if self._run_command(cmd, "excel_to_json"):
                # 检查输出文件是否存在
                if os.path.exists(self.json_file_path):
                    # 统计转换的数据量
                    with open(self.json_file_path, 'r', encoding='utf-8') as f:
                        line_count = sum(1 for line in f if line.strip())
                    
                    logging.info(f"Excel转JSON阶段完成，共转换 {line_count} 条数据")
                    self.index_input_file_path = self.json_file_path
                    return True
                else:
                    logging.error("Excel转JSON失败：输出文件不存在")
                    return False
            else:
                logging.error("Excel转JSON阶段失败")
                return False
            
        except Exception as e:
            logging.error(f"Excel转JSON阶段发生异常: {e}")
            traceback.print_exc()
            return False

    def _jsonl_has_ori_image_path(self, data_file):
        """检查结构化 JSONL 是否包含 ori_image_path 字段。"""
        if not data_file or not os.path.exists(data_file):
            return False
        try:
            with open(data_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    image_paths = data.get('ori_image_path')
                    if image_paths:
                        return True
        except Exception as e:
            logging.warning(f"检查图片字段失败: {e}")
        return False

    def stage_2_5_process_images(self):
        """阶段2.5：结构化Excel图片理解（仅存在ori_image_path时执行）"""
        if self.excel_process_mode == "unstructured_excel":
            logging.info("非结构化Excel流程跳过结构化图片理解阶段")
            return True

        if not self._jsonl_has_ori_image_path(self.json_file_path):
            logging.info("结构化Excel未发现ori_image_path，跳过图片理解阶段")
            self.index_input_file_path = self.json_file_path
            return True

        self.status_updater.update_task_stage(self.task_id, "excel_image_process")
        logging.info("开始阶段2.5：结构化Excel图片理解")

        image_api_key = GLOBAL_CONFIG.get(
            'dify_api_key_mluti_vision_forward_nomix',
            _private_value('70462a63d94e008ca27fba4d')
        )
        cmd = [
            sys.executable,
            '-m', 'kdb.shared.files.image_data',
            "process_search_data_image_file",
            self.json_file_path,
            image_api_key,
        ]

        log_file = os.path.join(self.log_dir, "excel_image_process.log")
        logging.info(f"执行命令: {shlex.join(cmd)}")
        try:
            with open(self.image_processed_json_file_path, 'w', encoding='utf-8') as out_f, \
                    open(log_file, 'w', encoding='utf-8') as log_f:
                result = subprocess.run(
                    cmd,
                    shell=False,
                    stdout=out_f,
                    stderr=log_f,
                    text=True,
                    cwd=self.script_dir,
                    env=subprocess_env(),
                )
            if result.returncode == 0 and os.path.exists(self.image_processed_json_file_path):
                self.index_input_file_path = self.image_processed_json_file_path
                logging.info(f"图片理解阶段完成，入库文件切换为: {self.index_input_file_path}")
                return True
            logging.error(f"图片理解阶段失败，返回码: {result.returncode}")
            return False
        except Exception as e:
            logging.error(f"图片理解阶段发生异常: {e}")
            traceback.print_exc()
            return False

    def _run_unstructured_document_fallback(self):
        """复用document_qa_segment_mining完整流程处理不可映射Excel。"""
        try:
            from kdb.mining.pipelines.document_qa_segment import DocumentQAMiningTaskController

            document_controller = DocumentQAMiningTaskController(
                self.script_dir,
                self.task_id,
                self.task_info,
            )
            success = document_controller.run_all_stages()
            if success:
                task_result = document_controller.count_qa_results()
                task_result.update(self._excel_route_result_fields())
                self.status_updater.update_task_result(
                    self.task_id,
                    json.dumps(task_result, ensure_ascii=False),
                )
            return success
        except Exception as e:
            logging.error(f"非结构化Excel fallback失败: {e}")
            traceback.print_exc()
            return False

    def _excel_route_result_fields(self):
        """返回写入task_result的Excel路由元信息。"""
        return {
            "excel_process_mode": self.excel_process_mode or self.excel_classification.get("mode"),
            "mapping_confidence": self.excel_classification.get("confidence", 0.0),
            "mapping_reason": self.excel_classification.get("reason", ""),
        }
    
    def stage_3_insert_index(self):
        """阶段3：插入索引"""
        self.status_updater.update_task_stage(self.task_id, "index_insert")
        logging.info("开始阶段3：插入索引")
        
        try:
            if not os.path.exists(self.index_input_file_path):
                logging.error(f"JSON文件不存在: {self.index_input_file_path}")
                return False
            
            # 获取索引配置文件路径
            index_config_path = self._get_index_config_path()
            if not index_config_path:
                logging.error("找不到可用的索引配置文件")
                return False
            
            # 构建命令。使用argv list，避免路径空格被shell拆分。
            cmd = [
                sys.executable,
                '-m', 'kdb.retrieval.application.search_index_data_interface',
                "insert_data_to_search_index",
                f"--data_file={self.index_input_file_path}",
                f"--config_path={index_config_path}",
                "--is_update_data=1",
                f"--index_name_assign={self.index_name}",
            ]
            
            
            if self._run_command(cmd, "insert_index"):
                logging.info("插入索引阶段完成")
                return True
            else:
                logging.error("插入索引阶段失败")
                return False
            
        except Exception as e:
            logging.error(f"插入索引阶段发生异常: {e}")
            traceback.print_exc()
            return False
    
    def predict_credits(self):
        """预测任务成本（阶段开始前）"""
        logging.info("开始预测任务成本...")
        try:
            # Excel上传任务不需要成本，设置为0
            self.status_updater.update_predict_credits(self.task_id, 0)
            logging.info("任务预测成本已设置为 0")
            return True
        except Exception as e:
            logging.error(f"预测任务成本失败: {e}")
            traceback.print_exc()
            return False
    
    def calculate_credits(self):
        """计算任务实际成本（阶段结束后）"""
        logging.info("开始计算任务实际成本...")
        try:
            # Excel上传任务不需要成本，设置为0
            self.status_updater.update_actual_credits(self.task_id, 0)
            logging.info("任务实际成本已设置为 0")
            return True
        except Exception as e:
            logging.error(f"计算任务实际成本失败: {e}")
            traceback.print_exc()
            return False
    
    def count_upload_results(self):
        """统计上传结果"""
        logging.info("开始统计任务结果...")
        
        if not os.path.exists(self.index_input_file_path):
            logging.warning(f"统计文件不存在: {self.index_input_file_path}")
            result = {"upload_count": 0}
            result.update(self._excel_route_result_fields())
            return result
        
        try:
            upload_count = 0
            
            with open(self.index_input_file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        upload_count += 1
                    except json.JSONDecodeError as e:
                        logging.warning(f"JSON解析失败: {e}")
                        continue
            
            result = {"upload_count": upload_count}
            result.update(self._excel_route_result_fields())
            logging.info(f"统计完成: 上传数据量={upload_count}")
            return result
            
        except Exception as e:
            logging.error(f"统计任务结果时发生异常: {e}")
            traceback.print_exc()
            result = {"upload_count": 0}
            result.update(self._excel_route_result_fields())
            return result
    
    def run_all_stages(self):
        """运行所有阶段"""
        logging.info(f"开始执行任务: {self.task_id}")
        
        # 阶段开始前，预测成本
        logging.info("=" * 100)
        logging.info("阶段开始前：预测任务成本")
        logging.info("=" * 100)
        self.predict_credits()
        
        stages = [
            ("文件下载", self.stage_1_download_files),
            ("Excel转JSON", self.stage_2_excel_to_json),
            ("结构化图片理解", self.stage_2_5_process_images),
            ("插入索引", self.stage_3_insert_index),
        ]
        
        try:
            for stage_name, stage_func in stages:
                logging.info("=" * 100)
                logging.info(f"开始执行阶段: {stage_name}")
                logging.info("=" * 100)
                success = stage_func()
                
                if not success:
                    logging.error("=" * 100)
                    logging.error(f"阶段 {stage_name} 执行失败，任务终止")
                    logging.error("=" * 100)
                    self.status_updater.update_task_run_status(self.task_id, 1, "error")
                    return False

                if self.document_fallback_completed:
                    logging.info("非结构化Excel已由document_qa_segment_mining流程完成，跳过Excel结构化后续阶段")
                    return True
                
                logging.info("=" * 100)
                logging.info(f"阶段 {stage_name} 执行完成")
                logging.info("=" * 100)
            
            # 所有阶段完成后，计算实际成本
            logging.info("=" * 100)
            logging.info("阶段结束后：计算任务实际成本")
            logging.info("=" * 100)
            self.calculate_credits()
            
            # 所有阶段完成，统计任务结果
            logging.info("=" * 100)
            logging.info("开始统计任务结果...")
            logging.info("=" * 100)
            
            task_result = self.count_upload_results()
            task_result_json = json.dumps(task_result, ensure_ascii=False)
            
            # 更新任务结果到数据库
            result_update_success = self.status_updater.update_task_result(self.task_id, task_result_json)
            if result_update_success:
                logging.info(f"任务结果更新成功: {task_result_json}")
            else:
                logging.warning("任务结果更新失败，但任务执行成功")
            
            # 更新任务状态为完成
            logging.info("所有阶段执行完成，任务成功")
            self.status_updater.update_task_run_status(self.task_id, 3, "completed")
            return True
            
        except Exception as e:
            logging.error(f"执行任务时发生异常: {e}")
            traceback.print_exc()
            self.status_updater.update_task_run_status(self.task_id, -1, "error")
            return False

def main():
    """主函数"""
    # 先配置基础日志，确保早期日志能够输出
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True
    )
    
    parser = argparse.ArgumentParser(description='Excel QA数据上传任务控制脚本')
    parser.add_argument('--script-dir', required=True, help='脚本根目录路径')
    parser.add_argument('--task-id', required=True, help='任务ID')
    parser.add_argument('--task-info', required=True, help='任务信息JSON字符串')
    
    args = parser.parse_args()
    
    logging.info("=== Excel QA数据上传任务脚本启动 ===")
    logging.info(f"脚本目录: {args.script_dir}")
    logging.info(f"任务ID: {args.task_id}")
    logging.info(f"任务信息: {args.task_info}")
    
    try:
        # 解析任务信息
        task_info = json.loads(args.task_info)
        logging.info("任务信息解析成功")
        
        # 创建任务控制器
        logging.info("正在创建任务控制器...")
        controller = ExcelQASegmentUploadController(
            args.script_dir,
            args.task_id,
            task_info
        )
        logging.info("任务控制器创建成功")
        
        # 运行所有阶段
        logging.info("开始运行所有阶段...")
        success = controller.run_all_stages()
        
        if success:
            logging.info("=== 任务执行成功完成 ===")
        else:
            logging.error("=== 任务执行失败 ===")
        
        sys.exit(0 if success else 1)
        
    except json.JSONDecodeError as e:
        logging.error(f"任务信息JSON解析失败: {e}")
        sys.exit(1)
    except Exception as e:
        logging.error(f"脚本执行发生异常: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == '__main__':
    main()
