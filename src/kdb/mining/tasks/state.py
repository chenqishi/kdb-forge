import threading
from queue import Queue

mysql_connector = None

task_pid_mapping = {}  # 存储task_id到pid的映射

monitoring_thread = None

should_monitor = True

script_base_dir = None  # 脚本基础目录

task_queue = Queue()  # 任务队列

task_worker_thread = None  # 任务工作线程

should_process_tasks = True  # 控制任务处理线程

task_resource_usage = {}  # 每类任务的资源占用配置

max_total_concurrency = 10  # 总并发数限制

current_resource_usage = 0  # 当前资源使用量

resource_lock = threading.Lock()  # 资源使用量锁
