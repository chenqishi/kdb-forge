import kdb.mining.common.runtime.logging as _common_runtime_logging
from kdb.mining.tasks.status import TaskStatusUpdater
from kdb.shared.storage.downloads import MinioDownloader
import json
import kdb.mining.document.workflows.excel.accounting as _excel_accounting
import kdb.mining.document.workflows.excel.execution as _excel_execution
import kdb.mining.document.workflows.excel.stages as _excel_stages
import logging
import os
import traceback

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

    _setup_logging = _common_runtime_logging._setup_logging

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

    _run_command = _excel_execution._run_command

    stage_1_download_files = _excel_stages.stage_1_download_files

    stage_2_excel_to_json = _excel_stages.stage_2_excel_to_json

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

    stage_2_5_process_images = _excel_stages.stage_2_5_process_images

    def _run_unstructured_document_fallback(self):
        """复用document_qa_segment_mining完整流程处理不可映射Excel。"""
        try:
            from kdb.mining.document.pipelines.qa_segment import DocumentQAMiningTaskController

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

    stage_3_insert_index = _excel_stages.stage_3_insert_index

    predict_credits = _excel_accounting.predict_credits

    calculate_credits = _excel_accounting.calculate_credits

    count_upload_results = _excel_accounting.count_upload_results

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


"""
Excel QA数据上传任务控制脚本
基于原始的insert_audit_excel.sh脚本改造
支持从远程文件系统（MinIO等）下载Excel文件并上传QA数据
"""
