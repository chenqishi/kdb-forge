from kdb.mining.tasks.estimation.document import access_document_clear_price
import logging
import os
import traceback

def calculate_credits(self):
    """计算任务实际成本（阶段结束后）"""
    logging.info("开始计算任务实际成本...")

    try:
        # 检查文件映射文件是否存在
        if not os.path.exists(self.file_mapping_path):
            logging.warning(f"文件映射文件不存在: {self.file_mapping_path}")
            return False

        # 读取文件映射，获取所有下载的文件路径
        downloaded_file_paths = []
        with open(self.file_mapping_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # 文件映射格式：{platform}\t{file_name}\t{file_ext}\t{file_path}
                parts = line.split('\t')
                if len(parts) >= 4:
                    file_path = parts[3]  # file_path在第3列（索引3）
                    if os.path.exists(file_path):
                        downloaded_file_paths.append(file_path)
                    else:
                        logging.warning(f"文件不存在，跳过: {file_path}")

        if not downloaded_file_paths:
            logging.warning("没有找到已下载的文件")
            return False

        logging.info(f"找到 {len(downloaded_file_paths)} 个已下载的文件，开始计算成本...")

        # 计算每个文件的成本并累加
        total_credits = 0.0
        total_chars = 0
        total_tokens = 0
        total_images = 0
        image_size_limit = 1024  # 默认1KB

        for file_path in downloaded_file_paths:
            try:
                logging.info(f"正在计算文件成本: {file_path}")
                # 调用access_document_clear_price，设置re_parse=False避免重复解析
                stats = access_document_clear_price(file_path, image_size_limit, re_parse=False)

                if stats and 'error' not in stats:
                    total_credits += stats.get('credits', 0)
                    total_chars += stats.get('char_count', 0)
                    total_tokens += stats.get('token_count', 0)
                    total_images += stats.get('image_count', 0)
                    logging.info(f"文件 {os.path.basename(file_path)} 成本计算完成: "
                               f"积分={stats.get('credits', 0):.2f}, "
                               f"字符数={stats.get('char_count', 0)}, "
                               f"Token数={stats.get('token_count', 0)}, "
                               f"图片数={stats.get('image_count', 0)}")
                else:
                    error_msg = stats.get('error', '未知错误') if stats else '统计失败'
                    logging.warning(f"文件 {os.path.basename(file_path)} 成本计算失败: {error_msg}")

            except Exception as e:
                logging.error(f"计算文件 {file_path} 成本时发生异常: {e}")
                traceback.print_exc()
                continue

        # 更新数据库中的实际成本
        actual_credits = round(total_credits, 2)
        self.status_updater.update_actual_credits(self.task_id, actual_credits)

        logging.info(f"任务实际成本计算完成: 总积分={actual_credits:.2f}, "
                   f"总字符数={total_chars}, 总Token数={total_tokens}, "
                   f"总图片数={total_images}")
        return True

    except Exception as e:
        logging.error(f"计算任务实际成本时发生异常: {e}")
        traceback.print_exc()
        return False
