import logging
import os
import shlex
import sys
import traceback

def stage_1_extract_data_from_sql(self):
    """阶段1：从SQL数据库提取聊天数据"""
    self.status_updater.update_task_stage(self.task_id, "data_extraction")
    logging.info("开始阶段1：从SQL数据库提取聊天数据")

    try:
        # 从SQL数据库提取数据
        data_content, config_content = self.data_extractor.extract_chat_data(
            client=self.client,
            user=self.user,
            index=self.index,
            app_id=self.app_id,
            start_time=self.start_time,
            end_time=self.end_time,
            black_nick_name=self.black_nick_name,
            need_process_name=self.need_process_name,
            mining_type=self.mining_type,
            scene_type=self.scene_type
        )

        if data_content is None or config_content is None:
            logging.error("从SQL数据库提取数据失败")
            return False

        # 保存数据文件
        with open(self.data_file_path, 'w', encoding='utf-8') as f:
            f.write(data_content)

        # 保存配置文件
        with open(self.robot_room_type_config_path, 'w', encoding='utf-8') as f:
            f.write(config_content)

        # 创建robot_data_map_file，格式为robot_name\tclient\tdata_file
        robot_data_map_content = f"{self.user}\t{self.client}\t1\t{self.data_file_path}"
        with open(self.robot_data_map_file_path, 'w', encoding='utf-8') as f:
            f.write(robot_data_map_content)

        # 创建空的处理记录文件和白名单文件
        with open(self.robot_room_process_record_path, 'w', encoding='utf-8') as f:
            f.write("")

        with open(self.robot_room_white_name_path, 'w', encoding='utf-8') as f:
            f.write("")

        # 生成prompt文件
        prompt_file_path = self._generate_prompt_file()
        if not prompt_file_path:
            logging.error("生成prompt文件失败")
            return False

        # 使用任务私有prompt映射，避免并发任务覆盖全局config/prompt_file_map.txt。
        with open(self.prompt_file_map_path, 'w', encoding='utf-8') as f:
            f.write(f"{self.client}\t{prompt_file_path}")

        # 统计数据量
        data_lines = data_content.strip().split('\n') if data_content.strip() else []
        logging.info(f"数据提取阶段完成，共提取 {len(data_lines)} 条聊天记录")
        logging.info(f"robot_data_map_file: {robot_data_map_content}")
        logging.info(f"prompt文件生成完成: {prompt_file_path}")
        return True

    except Exception as e:
        logging.error(f"数据提取阶段发生异常: {e}")
        traceback.print_exc()
        return False


def stage_2_generate_qa(self):
    """阶段2：生成QA"""
    self.status_updater.update_task_stage(self.task_id, "qa_generation")
    logging.info("开始阶段2：生成QA")

    try:
        # 构建命令，使用robot_data_map_file
        cmd = f"""{shlex.quote(sys.executable)} -m kdb.mining.chat.generation.batch run_batch_robot_chat_data \
                --data_file={self.robot_data_map_file_path} \
                --output_dir={self.data_dir} \
                --data_file_field_num=3 \
                --robot_room_type_config_file={self.robot_room_type_config_path} \
                --robot_process_record_file={self.robot_room_process_record_path} \
                --robot_white_list_file={self.robot_room_white_name_path} \
                --filter_group_name=all \
                --prompt_file_map={self.prompt_file_map_path} \
                --llm_stats_file={self.llm_stats_file_path} \
                --flag={self.task_id}"""

        # 修改命令，将stdout重定向到qa_file_path文件
        cmd_with_output = f"{cmd} > {self.qa_file_path}"

        if self._run_command(cmd_with_output, "qa_generation"):
            # 检查输出文件是否存在
            if os.path.exists(self.qa_file_path):
                logging.info(f"QA生成阶段完成，输出文件: {self.qa_file_path}")
                return True
            else:
                logging.error("QA生成阶段失败：未找到输出文件")
                return False
        else:
            logging.error("QA生成阶段失败")
            return False

    except Exception as e:
        logging.error(f"QA生成阶段发生异常: {e}")
        traceback.print_exc()
        return False


def stage_3_qa_quality(self):
    """阶段3：独立模型质量审核（失败关闭，不会误入库）。"""
    self.status_updater.update_task_stage(self.task_id, "qa_quality")
    logging.info("开始阶段3：QA独立质量审核")

    cmd = f"""{shlex.quote(sys.executable)} -m kdb.mining.chat.quality.reviewer review_batch \
                --batch_file={shlex.quote(self.qa_file_path)} \
                --output_batch_file={shlex.quote(self.qa_quality_file_path)} \
                --process_field_num=4 \
                --client={shlex.quote(self.client)} \
                --stats_file={shlex.quote(self.review_stats_file_path)}"""

    if self._run_command(cmd, "qa_quality"):
        logging.info("QA质量处理阶段完成")
        return True
    else:
        logging.error("QA质量处理阶段失败")
        return False


def stage_4_schema_transform(self):
    """阶段4：ES Schema转换"""
    self.status_updater.update_task_stage(self.task_id, "schema_transform")
    logging.info("开始阶段4：ES Schema转换")

    cmd = f"""{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.schema batch_trans_qa_to_search_data \
            --batch_file={self.qa_quality_file_path} \
            --output_file={self.search_data_file_path} \
            --field_num=5 \
            --platform_field_num=1 \
            --from_type=chat_auto \
            --task-id={self.task_id}"""

    # 兼容 webhook/手工任务传入的 category。Payoneer Olive 会用平台名作为类目名。
    if self.category_id:
        cmd += f" --category_id={shlex.quote(self.category_id)}"
    if self.category_name:
        cmd += f" --category_name={shlex.quote(str(self.category_name))}"

    if self._run_command(cmd, "schema_transform"):
        logging.info("ES Schema转换阶段完成")
        return True
    else:
        logging.error("ES Schema转换阶段失败")
        return False


def stage_5_insert_index(self):
    """阶段5：ES插入索引"""
    self.status_updater.update_task_stage(self.task_id, "index_insert")
    logging.info("开始阶段5：ES插入索引")

    # 生成索引配置文件路径
    index_config_path = os.path.join(self.config_dir, f'{self.client}_config.json')
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

    target_index_name = self.index_name or self.index or self.client
    logging.info(f"ES目标索引: {target_index_name}")
    if not self._validate_search_data_client_scope(target_index_name):
        return False
    cmd = f"""{shlex.quote(sys.executable)} -m kdb.entrypoints.cli.retrieval insert_data_to_search_index \
            --data_file={self.search_data_file_path} \
            --config_path={index_config_path} \
            --index_name_assign={target_index_name} \
            --is_only_title=true \
            --allowed_quality_levels=high \
            --required_review_decision=accept \
            --result_file={shlex.quote(self.insert_result_file_path)}"""

    if self._run_command(cmd, "index_insert"):
        logging.info("ES插入索引阶段完成")
        return True
    else:
        logging.error("ES插入索引阶段失败")
        return False
