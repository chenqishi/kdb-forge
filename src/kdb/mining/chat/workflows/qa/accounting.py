import json
import logging
import os
import traceback

def calculate_credits(self):
    """计算任务实际成本（阶段结束后）"""
    logging.info("开始计算任务实际成本...")

    try:
        # 检查数据文件是否存在
        if not os.path.exists(self.data_file_path):
            logging.warning(f"数据文件不存在: {self.data_file_path}")
            # 如果文件不存在，成本为0
            actual_credits = 0
        else:
            # 读取数据文件，统计消息条数（非空行数）
            with open(self.data_file_path, 'r', encoding='utf-8') as f:
                message_count = sum(1 for line in f if line.strip())

            # 实际成本 = 消息条数
            actual_credits = message_count

        # 更新数据库中的实际成本
        self.status_updater.update_actual_credits(self.task_id, actual_credits)

        logging.info(f"任务实际成本计算完成: 消息条数={actual_credits}, 实际成本={actual_credits}")
        return True

    except Exception as e:
        logging.error(f"计算任务实际成本时发生异常: {e}")
        traceback.print_exc()
        return False


def count_qa_results(self):
    """统计候选、审核、查重和真实入库口径。"""
    logging.info("开始统计任务结果...")

    llm_call_stats = {}
    llm_stats_file_path = getattr(self, 'llm_stats_file_path', '')
    if llm_stats_file_path and os.path.exists(llm_stats_file_path):
        try:
            with open(llm_stats_file_path, 'r', encoding='utf-8') as f:
                llm_call_stats = (json.load(f).get('totals') or {})
        except Exception as e:
            logging.warning("读取 LLM 调用统计失败: %s", e)

    review_stats = {}
    if os.path.exists(self.review_stats_file_path):
        try:
            with open(self.review_stats_file_path, 'r', encoding='utf-8') as f:
                review_stats = json.load(f)
        except Exception as e:
            logging.warning("读取 QA 审核统计失败: %s", e)

    insert_stats = {}
    if os.path.exists(self.insert_result_file_path):
        try:
            with open(self.insert_result_file_path, 'r', encoding='utf-8') as f:
                insert_stats = json.load(f)
        except Exception as e:
            logging.warning("读取 QA 入库统计失败: %s", e)

    if not os.path.exists(self.search_data_file_path):
        logging.warning(f"统计文件不存在: {self.search_data_file_path}")
        return {
            "qa_num": int(insert_stats.get('insert_success_num') or 0),
            "metrics_complete": bool(insert_stats),
            "llm_call_stats": llm_call_stats,
            "review_stats": review_stats,
            "insert_stats": insert_stats,
        }

    try:
        total_count = 0
        quality_counts = {'high': 0, 'mid': 0, 'low': 0}
        decision_counts = {'accept': 0, 'review': 0, 'reject': 0}

        with open(self.search_data_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                    total_count += 1
                    quality_level = data.get('quality_level', '')
                    if quality_level in quality_counts:
                        quality_counts[quality_level] += 1
                    review_decision = data.get('review_decision') or data.get('ext_info', {}).get('review_decision')
                    if review_decision in decision_counts:
                        decision_counts[review_decision] += 1

                except json.JSONDecodeError as e:
                    logging.warning(f"第{line_num}行JSON解析失败: {e}")
                    continue

        insert_success_num = int(insert_stats.get('insert_success_num') or 0)
        result = {
            # 保留 qa_num 给旧消费方，但修正语义为“真实成功入库数”。
            "qa_num": insert_success_num,
            "metrics_complete": bool(insert_stats),
            "extracted_candidate_num": int(review_stats.get('extracted_candidate_num') or total_count),
            "high_candidate_num": quality_counts['high'],
            "mid_candidate_num": quality_counts['mid'],
            "low_candidate_num": quality_counts['low'],
            "review_accept_num": decision_counts['accept'],
            "review_pending_num": decision_counts['review'],
            "review_reject_num": decision_counts['reject'],
            "insert_attempt_num": int(insert_stats.get('insert_attempt_num') or 0),
            "insert_success_num": insert_success_num,
            "duplicate_skip_num": int(insert_stats.get('duplicate_skip_num') or 0),
            "gate_skip_num": int(insert_stats.get('gate_skip_num') or 0),
            "insert_failure_num": int(insert_stats.get('insert_failure_num') or 0),
            "llm_call_stats": llm_call_stats,
            "review_stats": review_stats,
            "insert_stats": insert_stats,
        }
        logging.info("统计完成: candidate=%s accept=%s inserted=%s duplicate_skip=%s gate_skip=%s",
                     total_count, decision_counts['accept'], insert_success_num,
                     result['duplicate_skip_num'], result['gate_skip_num'])
        return result

    except Exception as e:
        logging.error(f"统计任务结果时发生异常: {e}")
        traceback.print_exc()
        return {
            "qa_num": int(insert_stats.get('insert_success_num') or 0),
            "metrics_complete": False,
            "llm_call_stats": llm_call_stats,
            "review_stats": review_stats,
            "insert_stats": insert_stats,
        }
