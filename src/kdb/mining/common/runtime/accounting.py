import logging
import traceback

def predict_credits(self):
    """预测任务成本（阶段开始前）"""
    logging.info("开始预测任务成本...")
    try:
        # 当前无逻辑，直接在SQL填-1
        self.status_updater.update_predict_credits(self.task_id, -1)
        logging.info("任务预测成本已设置为 -1")
        return True
    except Exception as e:
        logging.error(f"预测任务成本失败: {e}")
        traceback.print_exc()
        return False
