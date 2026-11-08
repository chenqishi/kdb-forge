from kdb.mining.tasks.processes import start_mining_task
from kdb.mining.tasks.records import update_task_status
from kdb.mining.tasks.resources import get_task_resource_usage
from queue import Empty
import kdb.mining.tasks.state as runtime_state
import logging
import threading
import time

def task_worker():
    """任务工作线程，从队列中取出任务并执行"""


    while runtime_state.should_process_tasks:
        try:
            # 从队列中获取任务，超时1秒
            task_data = runtime_state.task_queue.get(timeout=1)

            task_id = task_data['task_id']
            task_type = task_data['task_type']
            task_info = task_data['task_info']

            logging.info(f"从队列中取出任务: {task_id}, 类型: {task_type}")

            # 检查资源是否足够
            required_resources = get_task_resource_usage(task_type)

            with runtime_state.resource_lock:
                if runtime_state.current_resource_usage + required_resources > runtime_state.max_total_concurrency:
                    # 资源不足，将任务重新放回队列
                    runtime_state.task_queue.put(task_data)
                    logging.info(f"资源不足，任务 {task_id} 重新入队。当前使用: {runtime_state.current_resource_usage}, 需要: {required_resources}, 最大: {runtime_state.max_total_concurrency}")
                    time.sleep(5)  # 等待5秒后重试
                    continue

                # 资源足够，占用资源
                runtime_state.current_resource_usage += required_resources
                logging.info(f"任务 {task_id} 开始执行，占用资源: {required_resources}, 当前总使用: {runtime_state.current_resource_usage}")

            # 更新任务状态为运行中（状态编码：2-运行中）
            update_task_status(task_id, 2, "运行中")

            # 启动任务
            pid = start_mining_task(task_type, task_info, task_id)
            if pid is None:
                # 启动失败，释放资源并更新状态（状态编码：1-异常）
                with runtime_state.resource_lock:
                    runtime_state.current_resource_usage -= required_resources
                update_task_status(task_id, 1, "启动失败")
                logging.error(f"任务 {task_id} 启动失败")
            else:
                # 启动成功，记录PID映射
                runtime_state.task_pid_mapping[task_id] = pid
                logging.info(f"任务 {task_id} 启动成功，PID: {pid}")

            # 标记任务完成
            runtime_state.task_queue.task_done()

        except Empty:
            # 队列为空，继续循环
            continue
        except Exception as e:
            logging.error(f"任务工作线程处理任务时出错: {e}")
            # 如果任务数据存在，标记完成以避免队列阻塞
            if 'task_data' in locals():
                runtime_state.task_queue.task_done()
            time.sleep(1)


def add_task_to_queue(task_id, task_type, task_info):
    """将任务添加到队列中"""
    task_data = {
        'task_id': task_id,
        'task_type': task_type,
        'task_info': task_info
    }
    runtime_state.task_queue.put(task_data)
    # 更新任务状态为排队中（状态编码：4-等待）
    update_task_status(task_id, 4, "排队中")
    logging.info(f"任务 {task_id} 已添加到队列，队列大小: {runtime_state.task_queue.qsize()}")


def start_task_worker():
    """启动任务工作线程"""

    if runtime_state.task_worker_thread is None or not runtime_state.task_worker_thread.is_alive():
        runtime_state.task_worker_thread = threading.Thread(target=task_worker, daemon=True)
        runtime_state.task_worker_thread.start()
        logging.info("任务工作线程启动成功")


def stop_task_worker():
    """停止任务工作线程"""

    runtime_state.should_process_tasks = False
    logging.info("任务工作线程停止")
