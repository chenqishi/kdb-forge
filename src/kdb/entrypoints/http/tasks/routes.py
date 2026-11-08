from datetime import datetime
from flask import jsonify
from flask import request
from kdb.mining.tasks.estimation.document import asscess_document_clear_price
from kdb.mining.tasks.identifiers import generate_task_id
from kdb.mining.tasks.queue import add_task_to_queue
from kdb.mining.tasks.records import get_task_full_info
from kdb.mining.tasks.records import get_task_info
from kdb.mining.tasks.records import insert_task_record
from kdb.mining.tasks.records import reset_task_status
from kdb.mining.tasks.records import update_task_status
from kdb.mining.tasks.resources import release_task_resources
import kdb.mining.tasks.state as runtime_state
import logging
import psutil
import traceback

def start_task():
    """启动任务API"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空"}), 400

        task_type = data.get('task_type')
        task_info = data.get('task_info')

        if not task_type or not task_info:
            return jsonify({"code": 400, "msg": "task_type和task_info参数不能为空"}), 400

        # 验证task_type
        if task_type not in ['document_qa_mining', 'document_qa_segment_mining', 'chat_qa_mining', 'html_qa_segment_mining', 'excel_qa_segment_upload']:
            return jsonify({"code": 400, "msg": f"不支持的任务类型: {task_type}"}), 400

        # 验证task_info格式
        if task_type in ['document_qa_mining', 'document_qa_segment_mining', 'excel_qa_segment_upload']:
            if 'files' not in task_info or 'index_name' not in task_info:
                return jsonify({"code": 400, "msg": f"{task_type}类型需要files和index_name参数"}), 400
        elif task_type == 'chat_qa_mining':
            required_fields = ['client', 'user', 'app_id', 'start_time', 'end_time']
            missing_fields = [field for field in required_fields if field not in task_info]
            if missing_fields:
                return jsonify({"code": 400, "msg": f"chat_qa_mining类型需要以下参数: {', '.join(missing_fields)}"}), 400

        # 生成task_id
        task_id = generate_task_id(task_type, task_info)

        # 检查任务是否已存在
        existing_task = get_task_info(task_id)
        if existing_task:
            return jsonify({
                "code": 409,
                "msg": "任务已存在",
                "data": {"task_id": task_id}
            }), 409

        # 插入任务记录
        if not insert_task_record(task_id, task_type, task_info):
            return jsonify({"code": 500, "msg": "创建任务记录失败"}), 500

        # 将任务添加到队列中
        add_task_to_queue(task_id, task_type, task_info)

        return jsonify({
            "code": 0,
            "msg": "任务已加入队列",
            "data": {
                "task_id": task_id,
                "queue_size": runtime_state.task_queue.qsize(),
                "current_resource_usage": runtime_state.current_resource_usage,
                "max_concurrency": runtime_state.max_total_concurrency
            }
        })

    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"启动任务时出错: {e}")
        logging.error(f"错误堆栈: {tb}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500


def query_task_info():
    """查询任务信息API - 支持GET和POST请求"""
    try:
        # 根据请求方法获取参数
        if request.method == 'GET':
            task_id = request.args.get('task_id')
        else:  # POST请求
            data = request.get_json()
            if not data:
                return jsonify({"code": 400, "msg": "POST请求参数不能为空"}), 400
            task_id = data.get('task_id')

        if not task_id:
            return jsonify({"code": 400, "msg": "task_id参数不能为空"}), 400

        # 查询任务信息
        task_info = get_task_info(task_id)
        if task_info is None:
            return jsonify({"code": 404, "msg": "任务不存在"}), 404

        return jsonify({
            "code": 0,
            "msg": "查询成功",
            "data": task_info
        })

    except Exception as e:
        logging.error(f"查询任务信息时出错: {e}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500


def stop_task():
    """停止任务API"""
    try:
        # force=True允许不同Content-Type，silent=True在解析失败时返回None而不抛出异常
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空或JSON格式错误"}), 400

        task_id = data.get('task_id')
        if not task_id:
            return jsonify({"code": 400, "msg": "task_id参数不能为空"}), 400

        # 检查任务是否存在
        if task_id not in runtime_state.task_pid_mapping:
            return jsonify({"code": 404, "msg": "任务不存在或未在运行"}), 404

        pid = runtime_state.task_pid_mapping[task_id]

        try:
            # 检查进程是否存在
            if psutil.pid_exists(pid):
                process = psutil.Process(pid)

                # 首先尝试优雅停止
                process.terminate()

                # 等待3秒，如果进程仍然存在则强制杀死
                try:
                    process.wait(timeout=3)
                except psutil.TimeoutExpired:
                    process.kill()
                    logging.warning(f"任务 {task_id} (PID: {pid}) 强制终止")

                # 从映射中移除
                runtime_state.task_pid_mapping.pop(task_id, None)

                # 释放资源
                release_task_resources(task_id)

                # 更新数据库状态（状态编码：1-异常）
                update_task_status(task_id, 1, "手动停止")

                logging.info(f"任务 {task_id} (PID: {pid}) 已停止")
                return jsonify({
                    "code": 0,
                    "msg": "任务停止成功",
                    "data": {"task_id": task_id}
                })
            else:
                # 进程不存在，清理映射
                runtime_state.task_pid_mapping.pop(task_id, None)
                return jsonify({"code": 404, "msg": "进程不存在"}), 404

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            # 进程已经结束或无权限
            runtime_state.task_pid_mapping.pop(task_id, None)
            return jsonify({"code": 404, "msg": f"无法访问进程: {str(e)}"}), 404

    except Exception as e:
        logging.error(f"停止任务时出错: {e}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500


def restart_task():
    """重启任务API"""
    try:
        # 获取请求参数
        data = request.get_json(force=True, silent=True)
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空或JSON格式错误"}), 400

        task_id = data.get('task_id')
        if not task_id:
            return jsonify({"code": 400, "msg": "task_id参数不能为空"}), 400

        logging.info(f"开始重启任务: {task_id}")

        # 1. 从数据库获取任务完整信息
        task_full_info = get_task_full_info(task_id)
        if task_full_info is None:
            return jsonify({"code": 404, "msg": "任务不存在"}), 404

        task_type = task_full_info.get('task_type')
        task_info = task_full_info.get('task_info')

        if not task_type or not task_info:
            return jsonify({"code": 400, "msg": "任务信息不完整，缺少task_type或task_info"}), 400

        logging.info(f"任务信息获取成功: task_type={task_type}")

        # 检查任务是否正在运行
        if task_id in runtime_state.task_pid_mapping:
            pid = runtime_state.task_pid_mapping[task_id]
            if psutil.pid_exists(pid):
                return jsonify({
                    "code": 409,
                    "msg": "任务正在运行中，无法重启。请先停止任务。",
                    "data": {"task_id": task_id, "pid": pid}
                }), 409
            else:
                # 进程不存在但在映射中，清理映射
                runtime_state.task_pid_mapping.pop(task_id, None)
                release_task_resources(task_id)

        # 2. 重置任务状态
        if not reset_task_status(task_id):
            return jsonify({"code": 500, "msg": "重置任务状态失败"}), 500

        logging.info(f"任务状态重置成功: {task_id}")

        # 3. 将任务加入队列
        add_task_to_queue(task_id, task_type, task_info)

        logging.info(f"任务已重新加入队列: {task_id}")

        return jsonify({
            "code": 0,
            "msg": "任务重启成功，已加入队列",
            "data": {
                "task_id": task_id,
                "task_type": task_type,
                "queue_size": runtime_state.task_queue.qsize(),
                "current_resource_usage": runtime_state.current_resource_usage,
                "max_concurrency": runtime_state.max_total_concurrency
            }
        })

    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"重启任务时出错: {e}")
        logging.error(f"错误堆栈: {tb}")
        return jsonify({"code": 500, "msg": f"内部服务器错误: {str(e)}"}), 500


def health_check():
    """健康检查API"""
    return jsonify({
        "code": 0,
        "msg": "服务正常",
        "data": {
            "timestamp": datetime.now().isoformat(),
            "active_tasks": len(runtime_state.task_pid_mapping),
            "queue_size": runtime_state.task_queue.qsize(),
            "current_resource_usage": runtime_state.current_resource_usage,
            "max_concurrency": runtime_state.max_total_concurrency,
            "resource_utilization": f"{(runtime_state.current_resource_usage / runtime_state.max_total_concurrency * 100):.1f}%" if runtime_state.max_total_concurrency > 0 else "0%"
        }
    })


def task_access():
    """任务成本评估API"""
    try:
        # 获取请求参数
        data = request.get_json()
        if not data:
            return jsonify({"code": 400, "msg": "请求参数不能为空"}), 400

        task_type = data.get('task_type')
        task_info = data.get('task_info')

        if not task_type or not task_info:
            return jsonify({"code": 400, "msg": "task_type和task_info参数不能为空"}), 400

        # 目前只实现document_qa_segment_mining的估算
        if task_type == 'document_qa_segment_mining':
            # 验证task_info中是否包含files参数
            if 'files' not in task_info:
                return jsonify({"code": 400, "msg": "task_info中缺少files参数"}), 400

            files = task_info.get('files', [])
            if not isinstance(files, list):
                return jsonify({"code": 400, "msg": "files参数必须是列表类型"}), 400

            if len(files) == 0:
                return jsonify({"code": 400, "msg": "files列表不能为空"}), 400

            # 获取图片大小阈值（可选参数，默认1KB）
            image_size_limit = task_info.get('image_size_limit', 1024)

            logging.info(f"开始评估任务成本: task_type={task_type}, 文件数量={len(files)}")

            # 调用文档成本评估函数
            try:
                result = asscess_document_clear_price(files, image_size_limit)

                logging.info(f"任务成本评估完成: 总积分={result['total_credits']:.2f}, "
                           f"总字符数={result['total_chars']}, 总Token数={result['total_tokens']}, "
                           f"总图片数={result['total_images']}")

                return jsonify({
                    "code": 0,
                    "msg": "评估成功",
                    "data": {
                        "task_type": task_type,
                        "total_credits": round(result['total_credits'], 2),
                        "total_chars": result['total_chars'],
                        "total_tokens": result['total_tokens'],
                        "total_images": result['total_images'],
                        "detail_info": result['detail_info'],
                        "error_files": result['error_files'],
                        "success_count": len(result['detail_info']),
                        "error_count": len(result['error_files'])
                    }
                })

            except Exception as e:
                tb = traceback.format_exc()
                logging.error(f"评估任务成本时出错: {e}")
                logging.error(f"错误堆栈: {tb}")
                return jsonify({
                    "code": 500,
                    "msg": f"评估失败: {str(e)}"
                }), 500

        else:
            # 其他任务类型暂不支持
            return jsonify({
                "code": 400,
                "msg": f"暂不支持评估的任务类型: {task_type}，目前只支持document_qa_segment_mining"
            }), 400

    except Exception as e:
        tb = traceback.format_exc()
        logging.error(f"处理task_access请求时出错: {e}")
        logging.error(f"错误堆栈: {tb}")
        return jsonify({"code": 500, "msg": "内部服务器错误"}), 500


def register_routes(app):
    """Register the original handlers on the single entrypoint app."""
    app.route('/start_task', methods=['POST'])(start_task)
    app.route('/task_info', methods=['GET', 'POST'])(query_task_info)
    app.route('/stop_task', methods=['POST'])(stop_task)
    app.route('/restart_task', methods=['POST'])(restart_task)
    app.route('/health', methods=['GET'])(health_check)
    app.route('/task_access', methods=['POST'])(task_access)
