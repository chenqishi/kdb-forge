import kdb.mining.common.runtime.accounting as _common_runtime_accounting
import kdb.mining.common.runtime.logging as _common_runtime_logging
import kdb.mining.common.runtime.results as _common_runtime_results
import kdb.mining.document.workflows.accounting as _document_workflows_accounting
import kdb.mining.document.workflows.execution as _document_workflows_execution
import kdb.mining.document.workflows.stages as _document_workflows_stages
from kdb.mining.tasks.status import TaskStatusUpdater
from kdb.shared.storage.downloads import MinioDownloader
import json
import kdb.mining.document.workflows.execution as _qa_segment_execution
import kdb.mining.document.workflows.qa_segment.stages as _qa_segment_stages
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
        self.multimodal_config_path = os.path.join(
            self.config_dir, 'config_document_qasegment.json'
        )

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

        # ===== 新增（可选）业务上下文增强字段 =====
        # 缺省值保证：不传这些字段时，旧流程行为完全不变。
        self.business_context_text = task_info.get('business_context_text')
        self.knowledge_objective = task_info.get('knowledge_objective')
        self.quality_profile = task_info.get('quality_profile', 'business_task_knowledge')
        self.enable_context_enrichment = bool(task_info.get('enable_context_enrichment', False))
        self.enable_chat_query_context = bool(task_info.get('enable_chat_query_context', False))
        self.enable_web_context = bool(task_info.get('enable_web_context', False))  # 网络检索默认关闭
        self.context_cache_ttl_days = int(task_info.get('context_cache_ttl_days', 30))
        self.llm_backend = task_info.get('llm_backend', 'dify')  # 默认 dify，保持旧行为
        self.llm_model_name = task_info.get('llm_model_name')
        self.llm_provider = task_info.get('llm_provider')
        self.review_only = bool(task_info.get('review_only', False))

        # 中间文件路径
        self.file_mapping_path = os.path.join(self.data_dir, 'file_mapping.txt')
        self.content_mapping_path = os.path.join(self.data_dir, 'content_mapping.txt')
        self.translated_mapping_path = os.path.join(self.data_dir, 'translated_mapping.txt')
        self.qa_file_path = os.path.join(self.data_dir, 'all_clear_qa_file.txt')
        self.reclear_qa_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file.txt')
        self.search_data_file_path = os.path.join(self.data_dir, 'all_reclear_qa_file_search_data.txt')
        self.segment_knowledge_file_path = os.path.join(self.data_dir, 'segment_knowledge.txt')
        self.segment_search_data_file_path = os.path.join(self.data_dir, 'segment_knowledge_search_data.txt')
        self.multimodal_mapping_path = os.path.join(
            self.data_dir, 'content_mapping_multimodal.txt'
        )
        self.multimodal_data_info_path = os.path.join(self.data_dir, 'multimodal_data_info.json')
        self.multimodal_file_num = 5
        self._index_config_path = None

        # 业务上下文增强相关路径
        self.business_context_path = os.path.join(self.data_dir, 'business_context.json')
        self.business_context_cache_dir = task_info.get(
            'business_context_cache_dir',
            os.path.join(script_dir, 'data', 'business_context_cache')
        )
        self.quality_report_path = os.path.join(self.data_dir, 'generic_quality_report.json')

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

    _run_command = _document_workflows_execution._run_command

    stage_1_download_files = _document_workflows_stages.stage_1_download_files

    stage_2_parse_documents = _document_workflows_stages.stage_2_parse_documents

    stage_3_multimodal_process = _qa_segment_stages.stage_3_multimodal_process

    stage_4_translate_documents = _qa_segment_stages.stage_4_translate_documents

    stage_4_5_build_business_context = _qa_segment_stages.stage_4_5_build_business_context

    def _qa_context_cli_args(self):
        """构造 QA/segment 生成脚本的业务上下文/后端透传参数（仅在启用时附加）。"""
        if not self.enable_context_enrichment:
            return ""
        args = ""
        if os.path.exists(self.business_context_path):
            args += f" --business_context_path={self.business_context_path}"
        if self.quality_profile:
            args += f" --quality_profile={self.quality_profile}"
        if self.llm_backend:
            args += f" --llm_backend={self.llm_backend}"
        if self.llm_model_name:
            args += f" --llm_model_name={self.llm_model_name}"
        if self.llm_provider:
            args += f" --llm_provider={self.llm_provider}"
        return args

    stage_5_generate_qa = _qa_segment_stages.stage_5_generate_qa

    stage_6_qa_quality = _qa_segment_stages.stage_6_qa_quality

    stage_6_5_generic_quality = _qa_segment_stages.stage_6_5_generic_quality

    stage_7_schema_transform = _qa_segment_stages.stage_7_schema_transform

    stage_8_insert_index = _qa_segment_stages.stage_8_insert_index

    stage_9_generate_segment = _qa_segment_stages.stage_9_generate_segment

    stage_10_segment_schema_transform = _qa_segment_stages.stage_10_segment_schema_transform

    stage_11_insert_segment_index = _qa_segment_stages.stage_11_insert_segment_index

    predict_credits = _common_runtime_accounting.predict_credits

    calculate_credits = _document_workflows_accounting.calculate_credits

    count_qa_results = _common_runtime_results.count_qa_results

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
            ("多模态处理", self.stage_3_multimodal_process),
            ("文本翻译", self.stage_4_translate_documents),
            ("构建业务上下文", self.stage_4_5_build_business_context),
            ("QA生成", self.stage_5_generate_qa),
            ("QA质量处理", self.stage_6_qa_quality),
            ("通用质量后处理", self.stage_6_5_generic_quality),
            ("QA Schema转换", self.stage_7_schema_transform),
            ("QA插入索引", self.stage_8_insert_index),
            ("段落知识生成", self.stage_9_generate_segment),
            ("段落知识Schema转换", self.stage_10_segment_schema_transform),
            ("段落知识插入ES", self.stage_11_insert_segment_index),
        ]

        # review_only=true：生成审核/中间文件，但跳过 ES 插入阶段
        if self.review_only:
            skip_insert = {"QA插入索引", "段落知识插入ES"}
            stages = [(name, func) for name, func in stages if name not in skip_insert]
            logging.info("review_only=true：本次跳过 QA/段落知识 ES 插入阶段，仅产出审核/中间文件")

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
