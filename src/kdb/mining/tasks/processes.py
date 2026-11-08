from datetime import datetime
from kdb.mining.tasks.records import get_task_info
from kdb.mining.tasks.records import update_task_status
from kdb.mining.tasks.resources import release_task_resources
from kdb.shared.config.paths import source_path as _source_path
from kdb.shared.config.paths import subprocess_env
import json
import kdb.mining.tasks.state as runtime_state
import logging
import os
import psutil
import subprocess
import sys
import threading
import time

def start_mining_task(task_type, task_info, task_id):
    """启动挖掘任务"""
    if task_type == "document_qa_mining":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = str(_source_path('kdb', 'mining', 'document', 'pipelines', 'qa.py'))
        module_name = 'kdb.entrypoints.cli.mining.document_qa'
        task_info_json = json.dumps(task_info, ensure_ascii=False)

        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"挖掘脚本不存在: {script_path}")
                return None

            # 创建任务日志目录
            task_log_dir = os.path.join(runtime_state.script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)

            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')

            # 构建正确的命令行参数
            cmd = [
                sys.executable, '-m', module_name,
                '--script-dir', runtime_state.script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]

            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')

            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {runtime_state.script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()

            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=runtime_state.script_base_dir,
                env=subprocess_env(),  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )

            logging.info(f"任务启动成功，执行命令: {' '.join(cmd)}")
            logging.info(f"文档QA挖掘任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {runtime_state.script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}")

            return process.pid
        except FileNotFoundError:
            logging.error(f"挖掘脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None

    elif task_type == "document_qa_segment_mining":
        script_path = str(_source_path('kdb', 'mining', 'document', 'pipelines', 'qa_segment.py'))
        module_name = 'kdb.entrypoints.cli.mining.document_qa_segment'
        task_info_json = json.dumps(task_info, ensure_ascii=False)

        try:
            if not os.path.exists(script_path):
                logging.error(f"文档段落QA挖掘脚本不存在: {script_path}")
                return None

            task_log_dir = os.path.join(runtime_state.script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)

            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')

            cmd = [
                sys.executable, '-m', module_name,
                '--script-dir', runtime_state.script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]

            log_file = open(task_log_file, 'w', encoding='utf-8')

            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {runtime_state.script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()

            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=runtime_state.script_base_dir,
                env=subprocess_env(),
                text=True,
                bufsize=1
            )

            logging.info(f"文档段落QA挖掘任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {runtime_state.script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}")

            return process.pid
        except FileNotFoundError:
            logging.error(f"文档段落QA挖掘脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None

    elif task_type == "chat_qa_mining":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = str(_source_path('kdb', 'mining', 'chat', 'pipeline.py'))
        module_name = 'kdb.entrypoints.cli.mining.chat_qa'
        task_info_json = json.dumps(task_info, ensure_ascii=False)

        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"聊天QA挖掘脚本不存在: {script_path}")
                return None

            # 创建任务日志目录
            task_log_dir = os.path.join(runtime_state.script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)

            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')

            # 构建正确的命令行参数
            cmd = [
                sys.executable, '-m', module_name,
                '--script-dir', runtime_state.script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]

            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')

            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {runtime_state.script_base_dir}\n")
            log_file.write(f"任务信息: 客户={task_info.get('client', '未知')}, 用户={task_info.get('user', '未知')}, 索引={task_info.get('index', task_info.get('client', '未知'))}, 应用ID={task_info.get('app_id', '未知')}\n")
            log_file.write(f"时间范围: {task_info.get('start_time', '未知')} - {task_info.get('end_time', '未知')}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()

            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=runtime_state.script_base_dir,
                env=subprocess_env(),  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )

            logging.info(f"聊天QA挖掘任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {runtime_state.script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 客户={task_info.get('client', '未知')}, 用户={task_info.get('user', '未知')}, 索引={task_info.get('index', task_info.get('client', '未知'))}, 应用ID={task_info.get('app_id', '未知')}")
            logging.info(f"时间范围: {task_info.get('start_time', '未知')} - {task_info.get('end_time', '未知')}")

            return process.pid
        except FileNotFoundError:
            logging.error(f"聊天QA挖掘脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None

    elif task_type == "html_qa_segment_mining":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = str(_source_path('kdb', 'mining', 'web', 'pipeline.py'))
        module_name = 'kdb.entrypoints.cli.mining.html_qa_segment'
        task_info_json = json.dumps(task_info, ensure_ascii=False)

        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"HTML知识生成脚本不存在: {script_path}")
                return None

            # 创建任务日志目录
            task_log_dir = os.path.join(runtime_state.script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)

            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')

            # 构建正确的命令行参数
            cmd = [
                sys.executable, '-m', module_name,
                '--script-dir', runtime_state.script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]

            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')

            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {runtime_state.script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, URL数量={len(task_info.get('url_infos', []))}\n")
            log_file.write(f"客户: {task_info.get('client', '未知')}\n")
            log_file.write(f"使用Firecrawl: {task_info.get('is_use_firecrawl', False)}\n")
            log_file.write(f"需要翻译: {task_info.get('is_need_translated', False)}\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()

            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=runtime_state.script_base_dir,
                env=subprocess_env(),  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )

            logging.info(f"HTML知识生成任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {runtime_state.script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, URL数量={len(task_info.get('url_infos', []))}")
            logging.info(f"客户: {task_info.get('client', '未知')}")
            logging.info(f"使用Firecrawl: {task_info.get('is_use_firecrawl', False)}")
            logging.info(f"需要翻译: {task_info.get('is_need_translated', False)}")

            return process.pid
        except FileNotFoundError:
            logging.error(f"HTML知识生成脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None

    elif task_type == "excel_qa_segment_upload":
        # 构建启动命令 - 使用配置的脚本基础目录
        script_path = str(_source_path('kdb', 'mining', 'document', 'pipelines', 'excel.py'))
        module_name = 'kdb.entrypoints.cli.mining.excel_qa_segment_upload'
        task_info_json = json.dumps(task_info, ensure_ascii=False)

        try:
            # 检查脚本是否存在
            if not os.path.exists(script_path):
                logging.error(f"Excel QA上传脚本不存在: {script_path}")
                return None

            # 创建任务日志目录
            task_log_dir = os.path.join(runtime_state.script_base_dir, 'log', 'off_task')
            os.makedirs(task_log_dir, exist_ok=True)

            # 创建任务日志文件路径
            task_log_file = os.path.join(task_log_dir, f'{task_id}.log')

            # 构建正确的命令行参数
            cmd = [
                sys.executable, '-m', module_name,
                '--script-dir', runtime_state.script_base_dir,
                '--task-id', task_id,
                '--task-info', task_info_json
            ]

            # 打开日志文件用于写入（不使用with语句，避免子进程启动后文件句柄被关闭）
            log_file = open(task_log_file, 'w', encoding='utf-8')

            # 写入任务启动信息
            log_file.write(f"=== 任务启动信息 ===\n")
            log_file.write(f"任务ID: {task_id}\n")
            log_file.write(f"任务类型: {task_type}\n")
            log_file.write(f"启动时间: {datetime.now().isoformat()}\n")
            log_file.write(f"启动命令: {' '.join(cmd)}\n")
            log_file.write(f"工作目录: {runtime_state.script_base_dir}\n")
            log_file.write(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}\n")
            log_file.write(f"客户: {task_info.get('client', '未知')}\n")
            log_file.write(f"类目: {task_info.get('category_name', '未知')} (ID: {task_info.get('category_id', '未知')})\n")
            log_file.write(f"=== 任务执行日志 ===\n")
            log_file.flush()

            # 启动子进程，将标准输出和错误输出都重定向到日志文件
            # 注意：log_file会被子进程继承，子进程结束时会自动关闭
            process = subprocess.Popen(
                cmd,
                stdout=log_file,
                stderr=subprocess.STDOUT,  # 将stderr合并到stdout
                cwd=runtime_state.script_base_dir,
                env=subprocess_env(),  # 设置工作目录为脚本基础目录
                text=True,
                bufsize=1  # 行缓冲，确保日志及时写入
            )

            logging.info(f"Excel QA上传任务启动成功，PID: {process.pid}")
            logging.info(f"启动脚本: {script_path}")
            logging.info(f"脚本基础目录: {runtime_state.script_base_dir}")
            logging.info(f"任务ID: {task_id}")
            logging.info(f"任务日志文件: {task_log_file}")
            logging.info(f"任务信息: 索引名称={task_info.get('index_name', '未知')}, 文件数量={len(task_info.get('files', []))}")
            logging.info(f"客户: {task_info.get('client', '未知')}")
            logging.info(f"类目: {task_info.get('category_name', '未知')} (ID: {task_info.get('category_id', '未知')})")

            return process.pid
        except FileNotFoundError:
            logging.error(f"Excel QA上传脚本不存在: {script_path}")
            return None
        except Exception as e:
            logging.error(f"启动任务失败: {e}")
            return None

    else:
        logging.error(f"不支持的任务类型: {task_type}")
        return None


def monitor_tasks():
    """监控任务运行状态"""
    while runtime_state.should_monitor:
        try:
            # 检查所有正在运行的任务
            for task_id, pid in list(runtime_state.task_pid_mapping.items()):
                try:
                    # 检查进程是否还存在
                    if psutil.pid_exists(pid):
                        process = psutil.Process(pid)
                        process_status = process.status()

                        # 如果进程是僵尸进程，说明已经结束
                        if process_status == psutil.STATUS_ZOMBIE:
                            # 获取退出码
                            try:
                                returncode = process.wait(timeout=1)  # 等待1秒获取退出码
                            except psutil.TimeoutExpired:
                                returncode = None

                            # 从映射中移除
                            runtime_state.task_pid_mapping.pop(task_id, None)

                            # 释放资源
                            release_task_resources(task_id)

                            # 根据退出码判断成功或失败
                            if returncode == 0:
                                update_task_status(task_id, 3, "运行完成")
                                logging.info(f"任务 {task_id} (PID: {pid}) 运行完成，退出码: {returncode}")
                            else:
                                update_task_status(task_id, 1, "运行错误")
                                logging.error(f"任务 {task_id} (PID: {pid}) 运行错误，退出码: {returncode}")

                        # 如果进程状态正常，继续监控
                        elif process_status in [psutil.STATUS_RUNNING, psutil.STATUS_SLEEPING]:
                            # 进程正在运行，无需操作，继续监控
                            pass
                        else:
                            # 其他异常状态
                            logging.warning(f"任务 {task_id} (PID: {pid}) 进程状态异常: {process_status}")

                    else:
                        # 进程不存在，先检查数据库中的任务状态
                        task_info = get_task_info(task_id)
                        if task_info:
                            current_status = task_info.get('run_status')
                            # 如果任务已经是结束状态（3完成, 1异常），则不需要修改
                            if current_status in [3, 1]:
                                runtime_state.task_pid_mapping.pop(task_id, None)
                                release_task_resources(task_id)
                                logging.info(f"任务 {task_id} (PID: {pid}) 进程不存在，数据库状态已为结束状态: {current_status}")
                            elif current_status == 4:
                                # 任务状态为等待（排队中），不应该在task_pid_mapping中，清理映射
                                runtime_state.task_pid_mapping.pop(task_id, None)
                                release_task_resources(task_id)
                                logging.warning(f"任务 {task_id} (PID: {pid}) 进程不存在但状态为等待，清理映射")
                            else:
                                # 任务还在运行状态（状态为2），但进程不存在，标记为异常
                                runtime_state.task_pid_mapping.pop(task_id, None)
                                release_task_resources(task_id)
                                update_task_status(task_id, 1, "运行错误")
                                logging.warning(f"任务 {task_id} (PID: {pid}) 进程不存在但状态为运行中，标记为异常")
                        else:
                            # 无法获取任务信息，释放资源
                            runtime_state.task_pid_mapping.pop(task_id, None)
                            release_task_resources(task_id)
                            logging.warning(f"任务 {task_id} (PID: {pid}) 进程不存在且无法获取任务信息")

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    # 进程已经结束或无权限访问
                    runtime_state.task_pid_mapping.pop(task_id, None)
                    # 释放资源
                    release_task_resources(task_id)
                    update_task_status(task_id, 3, "运行完成")
                    logging.info(f"任务 {task_id} (PID: {pid}) 进程已结束")

                except Exception as task_error:
                    logging.error(f"监控任务 {task_id} (PID: {pid}) 时出错: {task_error}")

            # 休眠10秒再检查
            time.sleep(10)
        except Exception as e:
            logging.error(f"监控任务时出错: {e}")
            time.sleep(10)


def start_monitoring():
    """启动监控线程"""

    if runtime_state.monitoring_thread is None or not runtime_state.monitoring_thread.is_alive():
        runtime_state.monitoring_thread = threading.Thread(target=monitor_tasks, daemon=True)
        runtime_state.monitoring_thread.start()
        logging.info("任务监控线程启动成功")


def stop_monitoring():
    """停止监控线程"""

    runtime_state.should_monitor = False
    logging.info("任务监控线程停止")
