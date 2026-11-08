import kdb.mining.common.runtime.accounting as _common_runtime_accounting
import kdb.mining.common.runtime.logging as _common_runtime_logging
import kdb.mining.document.workflows.accounting as _document_workflows_accounting
import kdb.mining.document.workflows.execution as _document_workflows_execution
import kdb.mining.document.workflows.stages as _document_workflows_stages
from kdb.mining.tasks.status import TaskStatusUpdater
from kdb.shared.storage.downloads import MinioDownloader
import json
import kdb.mining.document.workflows.qa.accounting as _qa_accounting
import kdb.mining.document.workflows.execution as _qa_execution
import kdb.mining.document.workflows.qa.stages as _qa_stages
import logging
import os
import traceback

class DocumentQAMiningTaskController:
    """文档QA挖掘任务控制器"""

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
        self.need_translate = task_info.get('need_translate', 0)
        self.client = task_info.get('client', self.index_name)
        # 确保 category_id 是字符串类型（避免纯数字被解析为 int）
        category_id = task_info.get('category_id')
        self.category_id = str(category_id) if category_id is not None else None
        self.category_name = task_info.get('category_name')

        # 中间文件路径
        self.file_mapping_path = os.path.join(self.data_dir, 'file_mapping.txt')
        self.content_mapping_path = os.path.join(self.data_dir, 'content_mapping.txt')
        self.translated_mapping_path = os.path.join(self.data_dir, 'translated_mapping.txt')
        self.qa_file_path = os.path.join(self.data_dir, 'all_clear_qa_file.txt')
        self.reclear_qa_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file.txt')
        self.search_data_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file_search_data.txt')

        # 设置日志
        self._setup_logging()

    _setup_logging = _common_runtime_logging._setup_logging

    _run_command = _document_workflows_execution._run_command

    stage_1_download_files = _document_workflows_stages.stage_1_download_files

    stage_2_parse_documents = _document_workflows_stages.stage_2_parse_documents

    stage_3_translate_documents = _qa_stages.stage_3_translate_documents

    stage_4_generate_qa = _qa_stages.stage_4_generate_qa

    stage_5_qa_quality = _qa_stages.stage_5_qa_quality

    stage_6_schema_transform = _qa_stages.stage_6_schema_transform

    stage_7_insert_index = _qa_stages.stage_7_insert_index

    predict_credits = _common_runtime_accounting.predict_credits

    calculate_credits = _document_workflows_accounting.calculate_credits

    count_qa_results = _qa_accounting.count_qa_results

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
            ("文件解析", self.stage_2_parse_documents),
            ("文本翻译", self.stage_3_translate_documents),
            ("QA生成", self.stage_4_generate_qa),
            ("QA质量处理", self.stage_5_qa_quality),
            ("ES Schema转换", self.stage_6_schema_transform),
            ("ES插入索引", self.stage_7_insert_index),
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

            task_result = self.count_qa_results()
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
文档QA挖掘任务控制脚本
基于原始的platform_knowledge_generate_from_raw_document.sh脚本改造
支持从远程文件系统（MinIO等）下载文件并生成QA
"""
