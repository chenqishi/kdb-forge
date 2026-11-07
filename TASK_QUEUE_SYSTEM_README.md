# 任务队列系统说明

## 概述

`off_task_control_service.py` 已经升级为支持任务队列和并发控制的系统。主要改进包括：

1. **任务队列机制**：任务不再立即执行，而是加入队列等待处理
2. **并发控制**：支持总并发数限制和每类任务的资源占用配置
3. **FIFO原则**：任务按照先进先出的原则执行
4. **资源管理**：自动管理任务资源的分配和释放

## 主要变更

### 1. start_task API 变更

**之前**：任务立即启动执行
**现在**：任务加入队列，立即返回

```json
{
    "code": 0,
    "msg": "任务已加入队列",
    "data": {
        "task_id": "abc123...",
        "queue_size": 3,
        "current_resource_usage": 5,
        "max_concurrency": 10
    }
}
```

### 2. 新增全局变量

```python
# 任务队列相关变量
task_queue = Queue()  # 任务队列
task_worker_thread = None  # 任务工作线程
should_process_tasks = True  # 控制任务处理线程
task_resource_usage = {}  # 每类任务的资源占用配置
max_total_concurrency = 10  # 总并发数限制
current_resource_usage = 0  # 当前资源使用量
resource_lock = threading.Lock()  # 资源使用量锁
```

### 3. 新增函数

- `load_task_resource_config()`: 加载任务资源配置
- `get_task_resource_usage()`: 获取任务类型的资源占用量
- `task_worker()`: 任务工作线程，从队列中取出任务并执行
- `add_task_to_queue()`: 将任务添加到队列中
- `start_task_worker()`: 启动任务工作线程
- `stop_task_worker()`: 停止任务工作线程
- `release_task_resources()`: 释放任务占用的资源

## 配置文件

### 任务资源配置文件 (config/task_resource_config.json)

```json
{
    "max_total_concurrency": 10,
    "task_resource_usage": {
        "document_qa_mining": 2,
        "chat_qa_mining": 1
    }
}
```

**配置说明**：
- `max_total_concurrency`: 总并发数限制
- `task_resource_usage`: 每类任务的资源占用量
  - 如果配置文件中没有某个任务类型，默认资源占用量为1

## 启动参数

新增的命令行参数：

```bash
python off_task_control_service.py \
    --script-dir /path/to/project \
    --port 6000 \
    --host 0.0.0.0 \
    --resource-config /path/to/task_resource_config.json \
    --max-concurrency 15
```

**参数说明**：
- `--resource-config`: 任务资源配置文件路径（可选）
- `--max-concurrency`: 最大并发数（可选，默认10）

## 工作流程

1. **任务提交**：客户端调用 `/start_task` API
2. **任务验证**：验证任务类型和参数
3. **生成ID**：生成唯一的任务ID
4. **插入记录**：在数据库中插入任务记录，状态为"排队中"
5. **加入队列**：将任务信息加入队列
6. **立即返回**：返回任务ID和队列状态信息

7. **队列处理**：工作线程从队列中取出任务
8. **资源检查**：检查是否有足够的资源执行任务
9. **资源分配**：如果资源足够，分配资源并启动任务
10. **任务执行**：启动实际的任务进程
11. **资源释放**：任务完成后释放占用的资源

## 并发控制机制

### 资源占用计算

- 每个任务类型都有对应的资源占用量
- 总资源使用量 = Σ(运行中任务数 × 对应资源占用量)
- 只有当 `当前资源使用量 + 新任务资源占用量 ≤ 最大并发数` 时，任务才能启动

### 示例

假设配置如下：
```json
{
    "max_total_concurrency": 10,
    "task_resource_usage": {
        "document_qa_mining": 2,
        "chat_qa_mining": 1
    }
}
```

当前运行状态：
- 3个 document_qa_mining 任务：占用 3 × 2 = 6 个资源
- 2个 chat_qa_mining 任务：占用 2 × 1 = 2 个资源
- 总使用：8 个资源

新任务检查：
- 新的 document_qa_mining 任务：需要 2 个资源，8 + 2 = 10 ≤ 10，可以启动
- 新的 chat_qa_mining 任务：需要 1 个资源，8 + 1 = 9 ≤ 10，可以启动

## 监控和状态

### 健康检查 API

`GET /health` 现在返回更详细的信息：

```json
{
    "code": 0,
    "msg": "服务正常",
    "data": {
        "timestamp": "2024-01-01T12:00:00",
        "active_tasks": 5,
        "queue_size": 3,
        "current_resource_usage": 8,
        "max_concurrency": 10,
        "resource_utilization": "80.0%"
    }
}
```

### 任务状态

任务在数据库中的状态变化：
1. "排队中" - 任务已加入队列
2. "运行中" - 任务正在执行
3. "运行完成" - 任务成功完成
4. "运行错误" - 任务执行失败
5. "手动停止" - 任务被手动停止

## 测试

使用提供的测试脚本：

```bash
python test_queue_system.py
```

测试脚本会：
1. 检查服务健康状态
2. 提交不同类型的任务
3. 查看队列和资源使用情况

## 注意事项

1. **资源释放**：任务完成后会自动释放资源，包括正常完成、异常退出和手动停止
2. **队列持久化**：当前队列是内存队列，服务重启后队列中的任务会丢失
3. **任务重复**：相同参数的任务会生成相同的ID，避免重复执行
4. **错误处理**：任务启动失败时会自动释放已分配的资源
5. **线程安全**：使用锁机制确保资源计数的线程安全

## 兼容性

- 现有的 `/task_info` 和 `/stop_task` API 保持不变
- 数据库表结构无需修改
- 客户端代码需要适配新的返回格式（任务不再立即执行）
