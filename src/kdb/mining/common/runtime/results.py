import json
import logging
import os
import traceback

def count_qa_results(self):
    """统计阶段7中生成的高质量QA数据数量"""
    logging.info("开始统计任务结果...")

    if not os.path.exists(self.search_data_file_path):
        logging.warning(f"统计文件不存在: {self.search_data_file_path}")
        return {"qa_num": 0}

    try:
        qa_count = 0
        total_count = 0

        with open(self.search_data_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    total_count += 1

                    # 检查是否为高质量QA数据
                    quality_level = data.get('quality_level', '')
                    data_type = data.get('data_type', '')

                    if quality_level == 'high' and data_type == 'qa':
                        qa_count += 1

                except json.JSONDecodeError as e:
                    logging.warning(f"第{line_num}行JSON解析失败: {e}")
                    continue

        result = {"qa_num": qa_count}
        logging.info(f"统计完成: 总数据量={total_count}, 高质量QA数量={qa_count}")
        return result

    except Exception as e:
        logging.error(f"统计任务结果时发生异常: {e}")
        traceback.print_exc()
        return {"qa_num": 0}
