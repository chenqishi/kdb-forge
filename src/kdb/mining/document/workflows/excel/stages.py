from kdb.mining.common.schema.excel_import import classify_excel_upload
from kdb.shared.config.global_config import GLOBAL_CONFIG
from kdb.shared.config.paths import subprocess_env
from kdb.shared.config.private_values import private_value as _private_value
import json
import logging
import os
import shlex
import subprocess
import sys
import traceback

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
            '-m', 'kdb.entrypoints.cli.schema',
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
        '-m', 'kdb.mining.common.multimodal.image_paths',
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
            '-m', 'kdb.entrypoints.cli.retrieval',
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
