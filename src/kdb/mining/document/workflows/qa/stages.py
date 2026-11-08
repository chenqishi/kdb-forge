import logging
import os
import shlex
import sys

def stage_3_translate_documents(self):
    """阶段3：文本翻译（可选）"""
    if self.need_translate != 1:
        logging.info("跳过翻译阶段（need_translate != 1）")
        # 直接复制内容映射文件
        import shutil
        shutil.copy2(self.content_mapping_path, self.translated_mapping_path)
        return True

    self.status_updater.update_task_stage(self.task_id, "document_translate")
    logging.info("开始阶段3：文本翻译")

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


def stage_4_generate_qa(self):
    """阶段4：QA生成"""
    self.status_updater.update_task_stage(self.task_id, "qa_generation")
    logging.info("开始阶段4：QA生成")

    # 确定输入文件
    input_file = self.translated_mapping_path if os.path.exists(self.translated_mapping_path) else self.content_mapping_path

    # 计算文件名字段位置（从0开始计数）
    # 映射格式：{platform}\t{file_name}\t{file_path}\t{content_json_path}
    # file_name在第1列（索引1）
    file_name_field_num = 1
    data_file = self.qa_file_path
    log_file = self.log_dir + '/qa_generation.log'
    cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.common.generation.long_qa run_batch_clear_pdf_json_content {input_file} {self.task_id} {file_name_field_num} 1>{data_file} 2>{log_file}"

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


def stage_5_qa_quality(self):
    """阶段5：QA质量处理"""
    self.status_updater.update_task_stage(self.task_id, "qa_quality")
    logging.info("开始阶段5：QA质量处理")

    cmd = f"{shlex.quote(sys.executable)} -m kdb.mining.common.quality.qa run_batch_re_clear_qa_info --input_file={self.qa_file_path} --output_file={self.reclear_qa_file_path} --process_field_num=-1"

    if self._run_command(cmd, "qa_quality"):
        logging.info("QA质量处理阶段完成")
        return True
    else:
        logging.error("QA质量处理阶段失败")
        return False


def stage_6_schema_transform(self):
    """阶段6：ES Schema转换"""
    self.status_updater.update_task_stage(self.task_id, "schema_transform")
    logging.info("开始阶段6：ES Schema转换")

    cmd = f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.schema batch_trans_qa_to_search_data --batch_file={self.reclear_qa_file_path} --output_file={self.search_data_file_path} --field_num=9 --platform_field_num=0"

    # 添加task_id参数
    if self.task_id:
        cmd += f" --task_id={self.task_id}"

    # 添加类目参数（如果存在）
    if self.category_id:
        cmd += f" --category_id={self.category_id}"
    if self.category_name:
        cmd += f" --category_name='{self.category_name}'"

    if self._run_command(cmd, "schema_transform"):
        logging.info("ES Schema转换阶段完成")
        return True
    else:
        logging.error("ES Schema转换阶段失败")
        return False


def stage_7_insert_index(self):
    """阶段7：ES插入索引"""
    self.status_updater.update_task_stage(self.task_id, "index_insert")
    logging.info("开始阶段7：ES插入索引")

    # 生成索引配置文件路径
    index_config_path = os.path.join(self.config_dir, f'{self.index_name}_config.json')
    if not os.path.exists(index_config_path):
        logging.warning(f"索引配置文件不存在: {index_config_path}，尝试使用默认配置")
        # 可以尝试使用通用配置文件
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
            return False

    cmd = f"{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.retrieval insert_data_to_search_index --data_file={self.search_data_file_path} --config_path={index_config_path} --index_name_assign={self.index_name}"

    if self._run_command(cmd, "index_insert"):
        logging.info("ES插入索引阶段完成")
        return True
    else:
        logging.error("ES插入索引阶段失败")
        return False
