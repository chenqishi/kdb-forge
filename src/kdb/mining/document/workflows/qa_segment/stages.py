import json
import logging
import os
import shlex
import sys
import traceback

def stage_3_multimodal_process(self):
    """阶段3：多模态处理"""
    self.status_updater.update_task_stage(self.task_id, "multimodal_process")
    logging.info("开始阶段3：多模态处理")

    if not os.path.exists(self.content_mapping_path):
        logging.error(f"多模态处理失败：内容映射文件不存在: {self.content_mapping_path}")
        return False

    if not os.path.exists(self.multimodal_config_path):
        logging.error(f"多模态处理失败：配置文件不存在 {self.multimodal_config_path}")
        return False

    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.mining.common.multimodal.process "
        f"batch_process_multimodal_data_file "
        f"--config_path={self.multimodal_config_path} "
        f"--data_map_file={self.content_mapping_path} "
        f"--field_num={self.multimodal_file_num} "
        f"--new_mapfile_path={self.multimodal_mapping_path} "
        f"--multimodal_data_info_path={self.multimodal_data_info_path} "
        f"--is_local=False"
    )

    if self._run_command(cmd, "multimodal_process"):
        if os.path.exists(self.multimodal_mapping_path):
            self.content_mapping_path = self.multimodal_mapping_path
            logging.info(f"多模态处理完成，映射文件更新为: {self.multimodal_mapping_path}")
            try:
                with open(self.content_mapping_path, 'r', encoding='utf-8') as f:
                    updated_count = sum(1 for line in f if line.strip())
                logging.info(f"多模态映射记录数: {updated_count}")
            except Exception as e:
                logging.warning(f"统计多模态映射记录数失败: {e}")
        else:
            logging.info("多模态处理未生成新的映射文件，将继续使用原始内容映射文件")
        return True

    logging.error("多模态处理阶段失败")
    return False


def stage_4_translate_documents(self):
    """阶段4：文本翻译（可选）"""
    if self.need_translate != 1:
        logging.info("跳过翻译阶段（need_translate != 1）")
        # 直接复制内容映射文件
        import shutil
        shutil.copy2(self.content_mapping_path, self.translated_mapping_path)
        return True

    self.status_updater.update_task_stage(self.task_id, "document_translate")
    logging.info("开始阶段4：文本翻译")

    cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.common.translation.documents run_batch_translate_pdf_json_content {self.content_mapping_path}"

    if self._run_command(cmd, "translate"):
        # 翻译成功，检查可能的输出文件位置
        possible_outputs = [
            os.path.join(self.data_dir, 'translated_content_mapping.txt'),
            f"{self.content_mapping_path}_translated.txt",
            os.path.join(self.script_dir, 'data', f'{self.task_id}_translated.txt')
        ]

        output_found = False
        for translated_output in possible_outputs:
            if os.path.exists(translated_output):
                import shutil
                shutil.move(translated_output, self.translated_mapping_path)
                logging.info(f"翻译文件移动成功: {translated_output} -> {self.translated_mapping_path}")
                output_found = True
                break

        if not output_found:
            # 如果没有生成翻译文件，使用原文件
            import shutil
            shutil.copy2(self.content_mapping_path, self.translated_mapping_path)
            logging.info("未找到翻译输出文件，使用原始内容映射文件")

        logging.info("文本翻译阶段完成")
        return True
    else:
        logging.error("文本翻译阶段失败")
        return False


def stage_4_5_build_business_context(self):
    """阶段4.5：构建业务上下文（仅 enable_context_enrichment=true 时执行）。

    不启用时为 no-op（不生成上下文文件、不改 prompt），保证旧任务行为不变。
    任一子来源（chat history / web）失败都会降级，不影响主流程。
    """
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
            f"intents={len(ctx.get('query_intents', []))}"
        )
        return True
    except Exception as e:
        # 上下文构建是增强项，失败时降级为不增强，不中断任务
        logging.error(f"业务上下文构建失败，降级为不增强: {e}")
        traceback.print_exc()
        return True


def stage_5_generate_qa(self):
    """阶段5：QA生成"""
    self.status_updater.update_task_stage(self.task_id, "qa_generation")
    logging.info("开始阶段5：QA生成")

    # 确定输入文件
    input_file = self.translated_mapping_path if os.path.exists(self.translated_mapping_path) else self.content_mapping_path

    # 计算文件名字段位置（从0开始计数）
    # 映射格式：{platform}\t{file_name}\t{file_path}\tparse_save_dir\t{content_json_path}\t{multimodal_json_path}
    # file_name在第1列（索引1）
    file_name_field_num = 1
    data_file = self.qa_file_path
    log_file = self.log_dir + '/qa_generation.log'
    context_args = self._qa_context_cli_args()
    cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.common.generation.long_qa run_batch_clear_pdf_json_content {input_file} {self.task_id} {file_name_field_num} 1{context_args} 1>{data_file} 2>{log_file}"

    if self._run_command(cmd, "qa_generation"):
        # 检查可能的输出文件位置
        possible_outputs = [
            os.path.join(self.data_dir, 'all_clear_qa_file.txt'),
            os.path.join(self.script_dir, 'data', 'all_clear_qa_file.txt'),
            os.path.join(self.script_dir, f'data/all_clear_qa_file_{self.task_id}.txt')
        ]

        output_found = False
        for expected_output in possible_outputs:
            if os.path.exists(expected_output):
                import shutil
                if expected_output != self.qa_file_path:
                    shutil.move(expected_output, self.qa_file_path)
                logging.info(f"QA生成阶段完成，输出文件: {expected_output}")
                output_found = True
                break

        if output_found:
            return True
        else:
            logging.error("QA生成阶段失败：未找到输出文件")
            return False
    else:
        logging.error("QA生成阶段失败")
        return False


def stage_6_qa_quality(self):
    """阶段6：QA质量处理"""
    self.status_updater.update_task_stage(self.task_id, "qa_quality")
    logging.info("开始阶段6：QA质量处理")

    cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.common.quality.qa run_batch_re_clear_qa_info --input_file={self.qa_file_path} --output_file={self.reclear_qa_file_path} --process_field_num=-1"

    if self._run_command(cmd, "qa_quality"):
        logging.info("QA质量处理阶段完成")
        return True
    else:
        logging.error("QA质量处理阶段失败")
        return False


def stage_6_5_generic_quality(self):
    """阶段6.5：通用质量后处理（仅 enable_context_enrichment=true 时执行）。

    对 stage_6 产出的 re_clear QA 文件（field -1 指向的 {high,mid,low} JSON）做：
      - 悬空指代 / 栏目式泛标题修复（repair_self_contained_knowledge_rows）；
      - boilerplate / 单薄 / 不可自包含过滤（filter_business_quality_rows）。
    被拒条目移出 high，并写入 self.quality_report_path，不静默修改。
    不启用时为 no-op，旧任务行为不变。
    """
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
                # QA 字段为 q/a，映射为 title/content 做通用处理
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
        # 后处理失败不应中断主任务（已有 dify 质量过滤兜底）
        logging.error(f"通用质量后处理失败，降级跳过: {e}")
        traceback.print_exc()
        return True


def stage_7_schema_transform(self):
    """阶段7：QA转ES Schema"""
    self.status_updater.update_task_stage(self.task_id, "schema_transform")
    logging.info("开始阶段7：ES Schema转换")

    cmd = f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.schema batch_trans_qa_to_search_data --batch_file={self.reclear_qa_file_path} --output_file={self.search_data_file_path} --field_num=9 --platform_field_num=0"

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

    # 关查重：文档重跑走"先插后删"时，旧版本知识此刻仍然存活（del_flag=0），
    # 开查重会把新知识判成与旧版本重复而直接跳过插入（insert_data_to_search_index
    # 在 is_update_data=False 时 return (False,'数据重复')）——改写幅度越小越容易被吞，
    # 最后旧的删了、新的没进来，知识直接丢失。
    # 旧知识由调用方按文件名/标记精确软删，不依赖语义判重。
    cmd = (f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.retrieval "
           f"insert_data_to_search_index --data_file={self.search_data_file_path} "
           f"--config_path={index_config_path} --index_name_assign={self.index_name} "
           f"--check_duplicate=False")

    if self._run_command(cmd, "index_insert"):
        logging.info("QA插入ES阶段完成")
        return True

    logging.error("QA插入ES阶段失败")
    return False


def stage_9_generate_segment(self):
    """阶段9：段落知识生成"""
    self.status_updater.update_task_stage(self.task_id, "segment_generation")
    logging.info("开始阶段9：段落知识生成")

    segment_input = self.translated_mapping_path
    if not os.path.exists(segment_input):
        logging.error(f"段落知识生成失败：输入文件不存在 {segment_input}")
        return False

    segment_flag = self.task_id or self.index_name or "segment"
    segment_output = self.segment_knowledge_file_path
    segment_log = os.path.join(self.log_dir, "segment_generation.log")
    context_args = self._qa_context_cli_args()
    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.mining.common.generation.segments "
        f"run_batch_get_segment_knowledge {segment_input} {segment_flag} 1 0 1 1{context_args} "
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
        f"trans_segment_to_search_data_for_file "
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

    # segment 没有 title，判重的 min(title_sim, content_sim) 恒为 -1，数值规则永不触发，
    # 结果全由主题级 LLM 决定，会把同一篇文档的不同页判成重复（见
    # insert_data_to_search_index 的 docstring）。所以这里必须关查重，
    # 旧 segment 由调用方按文件名精确清理，而不是靠语义判重。
    cmd = (
        f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.retrieval "
        f"insert_data_to_search_index --data_file={self.segment_search_data_file_path} "
        f"--config_path={index_config_path} --index_name_assign={self.index_name} "
        f"--check_duplicate=False"
    )

    if self._run_command(cmd, "segment_index_insert"):
        logging.info("段落知识插入ES完成")
        return True

    logging.error("段落知识插入ES阶段失败")
    return False
