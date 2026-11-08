import kdb.mining.common.runtime.accounting as _common_runtime_accounting
import kdb.mining.common.runtime.logging as _common_runtime_logging
import kdb.mining.common.runtime.results as _common_runtime_results
from kdb.mining.tasks.status import TaskStatusUpdater
from kdb.shared.categories.trees import build_category_id_to_path_map
from kdb.shared.categories.trees import build_category_path_map
from kdb.shared.categories.trees import get_category_tree
from kdb.shared.storage.downloads import MinioDownloader
import json
import kdb.mining.web.workflows.qa_segment.accounting as _qa_segment_accounting
import kdb.mining.web.workflows.qa_segment.execution as _qa_segment_execution
import kdb.mining.web.workflows.qa_segment.stages as _qa_segment_stages
import logging
import os
import shlex
import traceback

class HtmlKgGenTaskController:
    """HTML知识生成任务控制器"""

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

        # 设置日志（需要先设置，预处理时会用到）
        self._setup_logging()

        # 初始化工具
        self.downloader = MinioDownloader(self.minio_config_path)
        self.status_updater = TaskStatusUpdater(self.mysql_config_path)

        # 预处理task_info，补齐类目信息
        self._preprocess_task_info()

        # 任务配置
        self.url_infos = task_info.get('url_infos', [])
        self.client = task_info.get('client', '')
        self.index_name = task_info.get('index_name', self.client)
        self.is_use_firecrawl = task_info.get('is_use_firecrawl', True)
        self.is_need_translated = task_info.get('is_need_translated', False)
        # 确保 category_id 是字符串类型（避免纯数字被解析为 int）
        category_id = task_info.get('category_id')
        self.category_id = str(category_id) if category_id is not None else None
        self.category_name = task_info.get('category_name')

        # 可选业务上下文增强：默认关闭，缺省时保持旧流程行为。
        self.business_context_text = task_info.get('business_context_text')
        self.knowledge_objective = task_info.get('knowledge_objective')
        self.quality_profile = task_info.get('quality_profile', 'business_task_knowledge')
        self.enable_context_enrichment = bool(task_info.get('enable_context_enrichment', False))
        self.enable_chat_query_context = bool(task_info.get('enable_chat_query_context', False))
        self.enable_web_context = bool(task_info.get('enable_web_context', False))
        self.context_cache_ttl_days = int(task_info.get('context_cache_ttl_days', 30) or 30)
        self.llm_backend = task_info.get('llm_backend', 'dify')
        self.llm_model_name = task_info.get('llm_model_name')
        self.llm_provider = task_info.get('llm_provider')
        self.review_only = bool(task_info.get('review_only', False))
        insert_is_need_llm = task_info.get('insert_is_need_llm')
        if isinstance(insert_is_need_llm, str):
            insert_is_need_llm = insert_is_need_llm.strip().lower() == 'true'
        self.insert_is_need_llm = (
            None if insert_is_need_llm is None else bool(insert_is_need_llm)
        )
        insert_check_duplicate = task_info.get('insert_check_duplicate')
        if isinstance(insert_check_duplicate, str):
            insert_check_duplicate = insert_check_duplicate.strip().lower() == 'true'
        self.insert_check_duplicate = (
            None if insert_check_duplicate is None else bool(insert_check_duplicate)
        )
        self.skip_multimodal = bool(
            task_info.get('skip_multimodal', False)
            or task_info.get('firecrawl_only', False)
        )

        # 中间文件路径
        self.crawler_result_file = os.path.join(self.data_dir, f'crawler_result_{task_id}.json')
        self.processed_result_file = os.path.join(self.data_dir, f'crawler_and_process_results_{task_id}.txt')
        self.multimodal_result_file = os.path.join(self.data_dir, f'crawler_and_process_results_multimodal_{task_id}.txt')
        self.translated_result_file = os.path.join(self.data_dir, f'web_crawler_translated_{task_id}.txt')
        self.qa_result_file = os.path.join(self.data_dir, f'web_crawler_clear_qa_{task_id}.txt')
        self.reclear_qa_file_path = os.path.join(self.data_dir, f'web_crawler_reclear_qa_{task_id}.txt')
        self.search_data_file_path = os.path.join(self.data_dir, f'web_crawler_reclear_qa_{task_id}_search_data.txt')
        self.segment_knowledge_file_path = os.path.join(self.data_dir, f'segment_knowledge_{task_id}.txt')
        self.segment_search_data_file_path = os.path.join(self.data_dir, f'segment_knowledge_{task_id}_search_data.txt')
        self.business_context_path = os.path.join(self.data_dir, 'business_context.json')
        self.business_context_cache_dir = task_info.get(
            'business_context_cache_dir',
            os.path.join(self.script_dir, 'data', 'business_context_cache')
        )
        self.quality_report_path = os.path.join(self.data_dir, 'generic_quality_report.json')

        # 多模态资源信息映射文件
        self.multimodal_data_info_path = os.path.join(self.data_dir, f'multimodal_data_info_{task_id}.json')

        self._index_config_path = None

    def _preprocess_task_info(self):
        """
        预处理task_info，补齐类目信息
        确保task_info和url_infos中都同时拥有category_name和category_id
        """
        client = self.task_info.get('client')
        if not client:
            # 没有client信息，无法查询类目树
            return

        try:
            # 获取类目树
            category_tree = get_category_tree(client)
            if not category_tree:
                logging.warning(f"无法获取客户端 {client} 的类目树，跳过类目信息补齐")
                return

            # 构建双向映射
            name_to_id_map = build_category_path_map(category_tree)
            id_to_name_map = build_category_id_to_path_map(category_tree)

            # 处理task_info顶层的类目信息
            self._fill_category_info(self.task_info, name_to_id_map, id_to_name_map)

            # 处理url_infos中的每个url的类目信息
            url_infos = self.task_info.get('url_infos', [])
            for url_info in url_infos:
                self._fill_category_info(url_info, name_to_id_map, id_to_name_map)
                # 若url_info不存在keep_attr_name，则默认设为"all"
                if 'keep_attr_name' not in url_info:
                    url_info['keep_attr_name'] = 'all'
                    logging.info(f"url_info缺少keep_attr_name，已默认设为'all': {url_info.get('url', '')}")

            logging.info("类目信息补齐完成")

        except Exception as e:
            logging.warning(f"预处理类目信息时发生异常: {e}")
            traceback.print_exc()

    def _fill_category_info(self, info_dict, name_to_id_map, id_to_name_map):
        """
        补齐单个字典中的类目信息
        
        Args:
            info_dict: 包含类目信息的字典（task_info或url_info）
            name_to_id_map: 类目名称到ID的映射
            id_to_name_map: 类目ID到名称的映射
        """
        category_name = info_dict.get('category_name')
        category_id = info_dict.get('category_id')

        # 如果两个都有，不需要处理
        if category_name and category_id:
            return

        # 只有category_name，需要查找category_id
        if category_name and not category_id:
            found_id = name_to_id_map.get(category_name)
            if found_id:
                info_dict['category_id'] = found_id
                logging.info(f"根据类目名称 '{category_name}' 补齐了类目ID: {found_id}")
            else:
                logging.warning(f"找不到类目名称 '{category_name}' 对应的ID")

        # 只有category_id，需要查找category_name
        elif category_id and not category_name:
            # 确保category_id是字符串
            category_id_str = str(category_id)
            found_name = id_to_name_map.get(category_id_str)
            if found_name:
                info_dict['category_name'] = found_name
                logging.info(f"根据类目ID '{category_id_str}' 补齐了类目名称: {found_name}")
            else:
                logging.warning(f"找不到类目ID '{category_id_str}' 对应的名称")

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

    _run_command = _qa_segment_execution._run_command

    stage_1_crawl_urls = _qa_segment_stages.stage_1_crawl_urls

    stage_2_process_crawled_content = _qa_segment_stages.stage_2_process_crawled_content

    stage_3_multimodal_process = _qa_segment_stages.stage_3_multimodal_process

    stage_4_translate_documents = _qa_segment_stages.stage_4_translate_documents

    stage_4_5_build_business_context = _qa_segment_stages.stage_4_5_build_business_context

    def _qa_context_cli_args(self):
        """构造 QA/segment 生成脚本的业务上下文/后端透传参数。"""
        if not self.enable_context_enrichment:
            return ""
        args = []
        if os.path.exists(self.business_context_path):
            args.append(f"--business_context_path={shlex.quote(self.business_context_path)}")
        if self.quality_profile:
            args.append(f"--quality_profile={shlex.quote(self.quality_profile)}")
        if self.llm_backend:
            args.append(f"--llm_backend={shlex.quote(self.llm_backend)}")
        if self.llm_model_name:
            args.append(f"--llm_model_name={shlex.quote(self.llm_model_name)}")
        if self.llm_provider:
            args.append(f"--llm_provider={shlex.quote(self.llm_provider)}")
        return " " + " ".join(args) if args else ""

    stage_5_generate_qa = _qa_segment_stages.stage_5_generate_qa

    stage_6_qa_quality = _qa_segment_stages.stage_6_qa_quality

    stage_6_5_generic_quality = _qa_segment_stages.stage_6_5_generic_quality

    stage_7_schema_transform = _qa_segment_stages.stage_7_schema_transform

    stage_8_insert_index = _qa_segment_stages.stage_8_insert_index

    stage_9_generate_segment = _qa_segment_stages.stage_9_generate_segment

    stage_10_segment_schema_transform = _qa_segment_stages.stage_10_segment_schema_transform

    stage_11_insert_segment_index = _qa_segment_stages.stage_11_insert_segment_index

    predict_credits = _common_runtime_accounting.predict_credits

    calculate_credits = _qa_segment_accounting.calculate_credits

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
            ("URL爬取", self.stage_1_crawl_urls),
            ("内容处理", self.stage_2_process_crawled_content),
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
HTML知识生成任务控制脚本
基于原始的platform_knowledge_generate_from_html.sh脚本改造
支持从task_info生成HTML知识
"""
