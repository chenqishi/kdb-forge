import json
import logging
import os
import traceback

def predict_credits(self):
    """预测任务成本（阶段开始前）"""
    logging.info("开始预测任务成本...")
    try:
        # Excel上传任务不需要成本，设置为0
        self.status_updater.update_predict_credits(self.task_id, 0)
        logging.info("任务预测成本已设置为 0")
        return True
    except Exception as e:
        logging.error(f"预测任务成本失败: {e}")
        traceback.print_exc()
        return False


def calculate_credits(self):
    """计算任务实际成本（阶段结束后）"""
    logging.info("开始计算任务实际成本...")
    try:
        # Excel上传任务不需要成本，设置为0
        self.status_updater.update_actual_credits(self.task_id, 0)
        logging.info("任务实际成本已设置为 0")
        return True
    except Exception as e:
        logging.error(f"计算任务实际成本失败: {e}")
        traceback.print_exc()
        return False


def count_upload_results(self):
    """统计上传结果"""
    logging.info("开始统计任务结果...")

    if not os.path.exists(self.index_input_file_path):
        logging.warning(f"统计文件不存在: {self.index_input_file_path}")
        result = {"upload_count": 0}
        result.update(self._excel_route_result_fields())
        return result

    try:
        upload_count = 0

        with open(self.index_input_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    upload_count += 1
                except json.JSONDecodeError as e:
                    logging.warning(f"JSON解析失败: {e}")
                    continue

        result = {"upload_count": upload_count}
        result.update(self._excel_route_result_fields())
        logging.info(f"统计完成: 上传数据量={upload_count}")
        return result

    except Exception as e:
        logging.error(f"统计任务结果时发生异常: {e}")
        traceback.print_exc()
        result = {"upload_count": 0}
        result.update(self._excel_route_result_fields())
        return result
