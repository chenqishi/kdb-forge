from flask import Flask
from kdb.entrypoints.http.tasks.bootstrap import parse_args
from kdb.entrypoints.http.tasks.routes import register_routes
from kdb.mining.tasks.processes import start_monitoring
from kdb.mining.tasks.processes import stop_monitoring
from kdb.mining.tasks.queue import start_task_worker
from kdb.mining.tasks.queue import stop_task_worker
from kdb.mining.tasks.records import init_mysql_connector
from kdb.mining.tasks.resources import load_task_resource_config
from kdb.mining.tasks.runtime import init_script_base_dir
from kdb.shared.config.paths import source_path as _source_path
import kdb.mining.tasks.state as runtime_state
import logging

app = Flask(__name__, root_path=str(_source_path('kdb', 'entrypoints', 'http', 'tasks')))


"""
Authors: qishichen(263436967@qq.com)
Date: 2024-01-01
"""


logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] [%(asctime)s] [%(threadName)s] [%(name)s] '
           '[%(filename)s:%(funcName)s:%(lineno)d]: %(message)s'
)


register_routes(app)


if __name__ == '__main__':
    # 解析命令行参数
    args = parse_args()

    # 初始化脚本基础目录
    init_script_base_dir(args.script_dir)

    # 设置最大并发数
    if args.max_concurrency:
        runtime_state.max_total_concurrency = args.max_concurrency

    # 加载任务资源配置
    load_task_resource_config(args.resource_config)

    # 初始化MySQL连接
    init_mysql_connector()

    # 启动任务工作线程
    start_task_worker()

    # 启动监控线程
    start_monitoring()

    try:
        logging.info(f"启动任务控制服务，监听地址: {args.host}:{args.port}")
        logging.info(f"最大并发数: {runtime_state.max_total_concurrency}")
        logging.info(f"任务资源占用配置: {runtime_state.task_resource_usage}")
        # 启动Flask应用
        app.run(host=args.host, port=args.port, debug=False, threaded=True)
    except KeyboardInterrupt:
        logging.info("接收到中断信号，正在关闭服务...")
        stop_task_worker()
        stop_monitoring()
    except Exception as e:
        logging.error(f"启动服务时出错: {e}")
        stop_task_worker()
        stop_monitoring()
