import logging
import os
import traceback

def calculate_credits(self):
    """计算任务实际成本（阶段结束后）"""
    logging.info("开始计算任务实际成本...")

    try:
        # 检查爬取结果文件是否存在
        if not os.path.exists(self.crawler_result_file):
            logging.warning(f"爬取结果文件不存在: {self.crawler_result_file}")
            # 如果文件不存在，使用url_infos的数量作为备选
            url_count = len(self.url_infos) if self.url_infos else 0
            logging.info(f"使用url_infos数量作为备选: {url_count}")
        else:
            # 读取爬取结果文件，统计实际爬取的URL数量（与stage_1_crawl_urls中的计算方法一致）
            with open(self.crawler_result_file, 'r', encoding='utf-8') as f:
                url_count = sum(1 for line in f if line.strip())

        # 计算实际成本：URL数量 * 5
        actual_credits = url_count * 5

        # 更新数据库中的实际成本
        self.status_updater.update_actual_credits(self.task_id, actual_credits)

        logging.info(f"任务实际成本计算完成: 爬取URL数量={url_count}, 实际成本={actual_credits}")
        return True

    except Exception as e:
        logging.error(f"计算任务实际成本时发生异常: {e}")
        traceback.print_exc()
        return False
