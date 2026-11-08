import json
import logging
import os
import shlex
import sys
import traceback

def stage_1_crawl_urls(self):
    """阶段1：爬取URL"""
    self.status_updater.update_task_stage(self.task_id, "url_crawl")
    logging.info("开始阶段1：爬取URL")

    try:
        task_info_json = json.dumps(self.task_info, ensure_ascii=False)

        # 构建命令
        cmd = (
            f"{shlex.quote(sys.executable)} -m kdb.mining.web.crawlers.batch "
            f"run_crawl_task_info "
            f"--task_id={self.task_id} "
            f"--task_info='{task_info_json}' "
            f"--output_file={self.crawler_result_file}"
        )

        if self._run_command(cmd, "url_crawl"):
            if os.path.exists(self.crawler_result_file):
                # 统计爬取的结果数量
                with open(self.crawler_result_file, 'r', encoding='utf-8') as f:
                    crawled_count = sum(1 for line in f if line.strip())
                logging.info(f"URL爬取阶段完成，共爬取 {crawled_count} 个结果")
                return True
            else:
                logging.error("URL爬取失败：输出文件不存在")
                return False
        else:
            logging.error("URL爬取阶段失败")
            return False

    except Exception as e:
        logging.error(f"URL爬取阶段发生异常: {e}")
        traceback.print_exc()
        return False


def stage_2_process_crawled_content(self):
    """阶段2：处理已爬取的内容"""
    self.status_updater.update_task_stage(self.task_id, "content_process")
    logging.info("开始阶段2：处理已爬取的内容")

    if not os.path.exists(self.crawler_result_file):
        logging.error(f"处理已爬取内容失败：输入文件不存在: {self.crawler_result_file}")
        return False

    try:
        # 构建命令
        cmd = (
            f"{shlex.quote(sys.executable)} -m kdb.mining.web.crawlers.batch "
            f"process_crawled_content_json_format "
            f"--input_file={self.crawler_result_file} "
            f"--output_dir={self.data_dir} "
            f"--flag={self.task_id}"
        )

        if self._run_command(cmd, "content_process"):
            if os.path.exists(self.processed_result_file):
                # 统计处理的结果数量
                with open(self.processed_result_file, 'r', encoding='utf-8') as f:
                    processed_count = sum(1 for line in f if line.strip())
                logging.info(f"内容处理阶段完成，共处理 {processed_count} 个结果")
                return True
            else:
                logging.error("内容处理失败：输出文件不存在")
                return False
        else:
            logging.error("内容处理阶段失败")
            return False

    except Exception as e:
        logging.error(f"内容处理阶段发生异常: {e}")
        traceback.print_exc()
        return False


def stage_3_multimodal_process(self):
    """阶段3：多模态处理"""
    self.status_updater.update_task_stage(self.task_id, "multimodal_process")
    logging.info("开始阶段3：多模态处理")

    if not os.path.exists(self.processed_result_file):
        logging.error(f"多模态处理失败：输入文件不存在: {self.processed_result_file}")
        return False

    if self.skip_multimodal:
        if not self.is_use_firecrawl:
            logging.error("skip_multimodal=true 目前要求 is_use_firecrawl=true")
            return False
        logging.info(
            "skip_multimodal=true：跳过图片/OCR处理，后续直接使用 firecrawl_content"
        )
        return True

    if not os.path.exists(self.multimodal_config_path):
        logging.error(f"多模态处理失败：配置文件不存在 {self.multimodal_config_path}")
        return False

    # 根据 is_use_firecrawl 选择 process_key
    process_key = 'firecrawl_content' if self.is_use_firecrawl else 'formatted_text'

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.mining.common.multimodal.process "
        f"batch_process_html_file "
        f"--config_path={self.multimodal_config_path} "
        f"--data_map_file={self.processed_result_file} "
        f"--field_num=-1 "
        f"--process_key={process_key} "
        f"--new_mapfile_path={self.multimodal_result_file} "
        f"--multimodal_data_info_path={self.multimodal_data_info_path} "
        f"--is_local=False"
    )

    if self._run_command(cmd, "multimodal_process"):
        if os.path.exists(self.multimodal_result_file):
            self.processed_result_file = self.multimodal_result_file
            logging.info(f"多模态处理完成，映射文件更新为: {self.multimodal_result_file}")
            try:
                with open(self.processed_result_file, 'r', encoding='utf-8') as f:
                    updated_count = sum(1 for line in f if line.strip())
                logging.info(f"多模态映射记录数: {updated_count}")
                #exit(1)
            except Exception as e:
                logging.warning(f"统计多模态映射记录数失败: {e}")
        else:
            logging.info("多模态处理未生成新的映射文件，将继续使用原始内容映射文件")
        return True

    logging.error("多模态处理阶段失败")
    return False


def stage_4_translate_documents(self):
    """阶段4：文本翻译（可选）"""
    if not self.is_need_translated:
        logging.info("跳过翻译阶段（is_need_translated != True）")
        # 直接复制内容映射文件
        import shutil
        shutil.copy2(self.processed_result_file, self.translated_result_file)
        return True

    self.status_updater.update_task_stage(self.task_id, "document_translate")
    logging.info("开始阶段4：文本翻译")

    process_field = (
        'firecrawl_content'
        if self.skip_multimodal and self.is_use_firecrawl
        else 'content_with_multimodal_unsderstanding'
    )
    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.mining.common.translation.documents "
        f"run_batch_translate_html_json_content "
        f"--input_file={self.processed_result_file} "
        f"--output_file={self.translated_result_file} "
        f"--field_num=-1 "
        f"--process_field={process_field}"
    )

    if self._run_command(cmd, "translate"):
        if os.path.exists(self.translated_result_file):
            logging.info("文本翻译阶段完成")
            return True
        else:
            logging.error("文本翻译失败：输出文件不存在")
            return False
    else:
        logging.error("文本翻译阶段失败")
        return False


def stage_4_5_build_business_context(self):
    """阶段4.5：构建业务上下文（仅 enable_context_enrichment=true 时执行）。"""
    if not self.enable_context_enrichment:
        logging.info("跳过业务上下文构建（enable_context_enrichment=false）")
        return True

    self.status_updater.update_task_stage(self.task_id, "build_business_context")
    logging.info("开始阶段4.5：构建业务上下文")
    try:
        from kdb.mining.common.context.business import build_business_context

        ctx = build_business_context(
            client=self.client,
            knowledge_objective=self.knowledge_objective,
            business_context_text=self.business_context_text,
            enable_context_enrichment=self.enable_context_enrichment,
            enable_chat_query_context=self.enable_chat_query_context,
            enable_web_context=self.enable_web_context,
            cache_dir=self.business_context_cache_dir,
            ttl_days=self.context_cache_ttl_days,
            task_info=self.task_info,
        )
        with open(self.business_context_path, 'w', encoding='utf-8') as f:
            json.dump(ctx, f, ensure_ascii=False, indent=2)
        logging.info(
            f"业务上下文已生成: {self.business_context_path}, sources={ctx.get('sources')}, "
            f"intents={len(ctx.get('query_intents', []))}, cache_hit={ctx.get('cache_hit')}"
        )
        return True
    except Exception as e:
        logging.error(f"业务上下文构建失败，降级为不增强: {e}")
        traceback.print_exc()
        return True


def stage_5_generate_qa(self):
    """阶段5：QA生成"""
    self.status_updater.update_task_stage(self.task_id, "qa_generation")
    logging.info("开始阶段5：QA生成")

    # 确定输入文件
    input_file = self.translated_result_file if os.path.exists(self.translated_result_file) else self.processed_result_file

    # 根据 is_need_translated 选择 process_field
    process_field = 'translated_text' if self.is_need_translated else (
        'firecrawl_content'
        if self.skip_multimodal and self.is_use_firecrawl
        else 'content_with_multimodal_unsderstanding'
    )

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.mining.web.processing.qa_generation "
        f"run_batch_clear_html_content "
        f"--input_file={input_file} "
        f"--output_file={self.qa_result_file} "
        f"--process_field_num=-1 "
        f"--process_field={process_field}"
        f"{self._qa_context_cli_args()}"
    )

    if self._run_command(cmd, "qa_generation"):
        if os.path.exists(self.qa_result_file):
            logging.info("QA生成阶段完成")
            return True
        else:
            logging.error("QA生成失败：输出文件不存在")
            return False
    else:
        logging.error("QA生成阶段失败")
        return False


def stage_6_qa_quality(self):
    """阶段6：QA质量处理"""
    self.status_updater.update_task_stage(self.task_id, "qa_quality")
    logging.info("开始阶段6：QA质量处理")

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.mining.common.quality.qa "
        f"run_batch_re_clear_qa_info "
        f"--input_file={self.qa_result_file} "
        f"--output_file={self.reclear_qa_file_path} "
        f"--process_field_num=-1"
    )

    if self._run_command(cmd, "qa_quality"):
        logging.info("QA质量处理阶段完成")
        return True
    else:
        logging.error("QA质量处理阶段失败")
        return False


def stage_6_5_generic_quality(self):
    """阶段6.5：通用质量后处理（仅 enable_context_enrichment=true 时执行）。"""
    if not self.enable_context_enrichment:
        logging.info("跳过通用质量后处理（enable_context_enrichment=false）")
        return True
    if not os.path.exists(self.reclear_qa_file_path):
        logging.warning(f"通用质量后处理跳过：未找到 {self.reclear_qa_file_path}")
        return True

    self.status_updater.update_task_stage(self.task_id, "generic_quality")
    logging.info("开始阶段6.5：通用质量后处理")
    try:
        from kdb.mining.common.quality.generic import repair_self_contained_knowledge_rows
        from kdb.mining.common.quality.generic import filter_business_quality_rows

        business_context = None
        if os.path.exists(self.business_context_path):
            with open(self.business_context_path, 'r', encoding='utf-8') as f:
                business_context = json.load(f)

        report = {"files": {}, "total_repaired": 0, "total_rejected": 0}
        with open(self.reclear_qa_file_path, 'r', encoding='utf-8') as f:
            mapping_lines = [l.strip() for l in f if l.strip()]

        for line in mapping_lines:
            fields = line.split('\t')
            qa_json_file = fields[-1]
            if not os.path.exists(qa_json_file):
                continue
            with open(qa_json_file, 'r', encoding='utf-8') as jf:
                qa_dict = json.load(jf)

            file_report = {}
            for level in ('high', 'mid', 'low'):
                rows = qa_dict.get(level, []) or []
                if not rows:
                    continue
                repaired, rep_report = repair_self_contained_knowledge_rows(
                    rows, business_context=business_context,
                    source_title_field='from_file_name',
                    title_field='q', content_field='a',
                )
                kept, rejected = filter_business_quality_rows(
                    repaired, quality_profile=self.quality_profile,
                    title_field='q', content_field='a',
                )
                qa_dict[level] = kept
                file_report[level] = {
                    'repaired': rep_report['repaired_count'],
                    'needs_review': rep_report['needs_review_count'],
                    'rejected': len(rejected),
                    'rejected_items': [
                        {'q': r.get('q', ''), 'reason': r.get('reject_reason', '')}
                        for r in rejected
                    ],
                }
                report['total_repaired'] += rep_report['repaired_count']
                report['total_rejected'] += len(rejected)

            with open(qa_json_file, 'w', encoding='utf-8') as jf:
                json.dump(qa_dict, jf, ensure_ascii=False, indent=2)
            report['files'][qa_json_file] = file_report

        with open(self.quality_report_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logging.info(
            f"通用质量后处理完成: 修复 {report['total_repaired']} 条, 拒绝 {report['total_rejected']} 条, "
            f"报告: {self.quality_report_path}"
        )
        return True
    except Exception as e:
        logging.error(f"通用质量后处理失败，降级跳过: {e}")
        traceback.print_exc()
        return True


def stage_7_schema_transform(self):
    """阶段7：QA转ES Schema"""
    self.status_updater.update_task_stage(self.task_id, "schema_transform")
    logging.info("开始阶段7：ES Schema转换")

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.schema "
        f"batch_trans_qa_to_search_data "
        f"--batch_file={self.reclear_qa_file_path} "
        f"--output_file={self.search_data_file_path} "
        f"--field_num=-1 "
        f"--platform_field_num=0"
    )

    # 添加task_id参数
    if self.task_id:
        cmd += f" --task_id={self.task_id}"

    # 添加类目参数（如果存在）
    if self.category_id:
        cmd += f" --category_id={self.category_id}"
    if self.category_name:
        cmd += f" --category_name='{self.category_name}'"

    # 添加多模态映射路径（如果存在）
    if os.path.exists(self.multimodal_data_info_path):
        cmd += f" --multimodal_mapping_path={self.multimodal_data_info_path}"
        logging.info(f"使用多模态映射文件: {self.multimodal_data_info_path}")
    else:
        logging.info("未找到多模态映射文件，跳过多模态内容处理")

    if self._run_command(cmd, "schema_transform"):
        logging.info("ES Schema转换阶段完成")
        return True
    else:
        logging.error("ES Schema转换阶段失败")
        return False


def stage_8_insert_index(self):
    """阶段8：QA插入ES"""
    self.status_updater.update_task_stage(self.task_id, "index_insert")
    logging.info("开始阶段8：ES插入索引")

    # 生成索引配置文件路径
    index_config_path = self._get_index_config_path()
    if not index_config_path:
        logging.error("找不到可用的索引配置文件")
        return False

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.retrieval "
        f"insert_data_to_search_index "
        f"--data_file={self.search_data_file_path} "
        f"--config_path={index_config_path} "
        f"--index_name_assign={self.index_name}"
    )
    if self.insert_is_need_llm is not None:
        cmd += f" --is_need_llm={'true' if self.insert_is_need_llm else 'false'}"
    if self.insert_check_duplicate is not None:
        cmd += f" --check_duplicate={'true' if self.insert_check_duplicate else 'false'}"

    if self._run_command(cmd, "index_insert"):
        logging.info("QA插入ES阶段完成")
        return True

    logging.error("QA插入ES阶段失败")
    return False


def stage_9_generate_segment(self):
    """阶段9：段落知识生成"""
    self.status_updater.update_task_stage(self.task_id, "segment_generation")
    logging.info("开始阶段9：段落知识生成")

    segment_input = self.translated_result_file
    if not os.path.exists(segment_input):
        logging.error(f"段落知识生成失败：输入文件不存在 {segment_input}")
        return False

    # 根据 is_need_translated 选择 process_field_key，与 stage_5 类似
    process_field_key = 'translated_text' if self.is_need_translated else (
        'firecrawl_content'
        if self.skip_multimodal and self.is_use_firecrawl
        else 'content_with_multimodal_unsderstanding'
    )

    segment_output = self.segment_knowledge_file_path
    segment_log = os.path.join(self.log_dir, "segment_generation.log")

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.mining.common.generation.segments "
        f"run_batch_get_segment_knowledge_html_json "
        f"--html_json_batch_file={segment_input} "
        f"--flag={self.task_id} "
        f"--filed_num=-1 "
        f"--platform_field_num=0 "            
        f"--process_field_key={process_field_key} "
        f"{self._qa_context_cli_args()} "
        f"1>{segment_output} 2>{segment_log}"
    )

    if self._run_command(cmd, "segment_generation"):
        if os.path.exists(segment_output) and os.path.getsize(segment_output) > 0:
            logging.info(f"段落知识生成完成，输出文件: {segment_output}")
            return True
        logging.error("段落知识生成失败：未找到输出文件或文件为空")
        return False

    logging.error("段落知识生成阶段失败")
    return False


def stage_10_segment_schema_transform(self):
    """阶段10：段落知识转ES Schema"""
    self.status_updater.update_task_stage(self.task_id, "segment_schema_transform")
    logging.info("开始阶段10：段落知识转ES Schema")

    if not os.path.exists(self.segment_knowledge_file_path):
        logging.error(f"段落知识转ES Schema失败：输入文件不存在 {self.segment_knowledge_file_path}")
        return False

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.schema "
        f"trans_html_segment_to_search_data_for_file "
        f"--input_file={self.segment_knowledge_file_path} "
        f"--output_file={self.segment_search_data_file_path} "
        f"--field_num=0"
    )

    # 添加task_id参数
    if self.task_id:
        cmd += f" --task_id={self.task_id}"

    # 添加类目参数（如果存在）
    if self.category_id:
        cmd += f" --category_id={self.category_id}"
    if self.category_name:
        cmd += f" --category_name='{self.category_name}'"

    # 添加多模态映射路径（如果存在）
    if os.path.exists(self.multimodal_data_info_path):
        cmd += f" --multimodal_mapping_path={self.multimodal_data_info_path}"
        logging.info(f"使用多模态映射文件: {self.multimodal_data_info_path}")
    else:
        logging.info("未找到多模态映射文件，跳过多模态内容处理")

    if self._run_command(cmd, "segment_schema_transform"):
        if os.path.exists(self.segment_search_data_file_path):
            logging.info("段落知识ES Schema转换完成")
            return True
        logging.error("段落知识ES Schema转换失败：未找到输出文件")
        return False

    logging.error("段落知识ES Schema转换阶段失败")
    return False


def stage_11_insert_segment_index(self):
    """阶段11：段落知识插入ES"""
    self.status_updater.update_task_stage(self.task_id, "segment_index_insert")
    logging.info("开始阶段11：段落知识插入ES")

    if not os.path.exists(self.segment_search_data_file_path):
        logging.error(f"段落知识插入ES失败：输入文件不存在 {self.segment_search_data_file_path}")
        return False

    index_config_path = self._get_index_config_path()
    if not index_config_path:
        return False

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.retrieval "
        f"insert_data_to_search_index --data_file={self.segment_search_data_file_path} "
        f"--index_name_assign={self.index_name} "
        f"--config_path={index_config_path}"
    )
    if self.insert_is_need_llm is not None:
        cmd += f" --is_need_llm={'true' if self.insert_is_need_llm else 'false'}"
    if self.insert_check_duplicate is not None:
        cmd += f" --check_duplicate={'true' if self.insert_check_duplicate else 'false'}"

    if self._run_command(cmd, "segment_index_insert"):
        logging.info("段落知识插入ES完成")
        return True

    logging.error("段落知识插入ES阶段失败")
    return False
