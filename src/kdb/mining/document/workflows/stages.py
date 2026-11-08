import logging
import os
import sys
import traceback

def stage_1_download_files(self):
    """阶段1：文件下载"""
    self.status_updater.update_task_stage(self.task_id, "file_download")
    logging.info("开始阶段1：文件下载")

    try:
        downloaded_files = []

        for file_info in self.files:
            file_name = file_info.get('name', '')
            file_ext = file_info.get('ext', '')
            store_method = file_info.get('store_method', '')
            address = file_info.get('address', '')

            if not file_name or not address:
                logging.warning(f"文件信息不完整，跳过: {file_info}")
                continue

            # 生成本地文件路径
            local_filename = f"{file_name}.{file_ext}" if file_ext else file_name
            local_path = os.path.join(self.data_dir, 'downloaded_files', local_filename)

            # 下载文件
            logging.info(f"开始下载文件: {file_name}")
            logging.info(f"存储方式: {store_method}, 地址: {address}")
            logging.info(f"本地路径: {local_path}")

            success = self.downloader.download_file(file_info, local_path)

            if success and os.path.exists(local_path):
                # 记录文件映射：{platform}\t{file_name}\t{file_ext}\t{file_path}
                mapping_line = f"{self.client}\t{file_name}\t{file_ext}\t{local_path}"
                downloaded_files.append(mapping_line)
                logging.info(f"文件下载成功: {file_name} -> {local_path}")
            else:
                logging.error(f"文件下载失败: {file_name}")
                return False

        # 保存文件映射
        with open(self.file_mapping_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(downloaded_files))

        logging.info(f"文件下载阶段完成，共下载 {len(downloaded_files)} 个文件")
        return True

    except Exception as e:
        logging.error(f"文件下载阶段发生异常: {e}")
        traceback.print_exc()
        return False


def stage_2_parse_documents(self):
    """阶段2：文件解析"""
    self.status_updater.update_task_stage(self.task_id, "document_parse")
    logging.info("开始阶段2：文件解析")

    try:
        # 使用batch_map_files_trans函数进行批量文件解析
        # 该函数接受文件映射文件作为输入，输出内容映射文件
        # 文件映射格式：{platform}\t{file_name}\t{file_ext}\t{file_path}
        # file_path位于第3列（从0开始计数）
        file_path_field = 3
        cmd = [
            sys.executable,
            '-m', 'kdb.mining.common.parsing.documents',
            'batch_map_files_trans',
            f'--wait_process_file={self.file_mapping_path}',
            f'--output_file={self.content_mapping_path}',
            f'--file_path_field={file_path_field}',
        ]

        if self._run_command(cmd, "document_parse"):
            # 检查输出文件是否存在
            if os.path.exists(self.content_mapping_path):
                # 统计解析的文件数量
                with open(self.content_mapping_path, 'r', encoding='utf-8') as f:
                    parsed_count = sum(1 for line in f if line.strip())

                logging.info(f"文件解析阶段完成，共解析 {parsed_count} 个文件")
                return True
            else:
                logging.error("文档解析失败：输出文件不存在")
                return False
        else:
            logging.error("文档解析阶段失败")
            return False

    except Exception as e:
        logging.error(f"文件解析阶段发生异常: {e}")
        traceback.print_exc()
        return False
