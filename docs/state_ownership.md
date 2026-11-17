# 状态所有权

结构迁移保持既有进程模型、初始化顺序和对象数量；目录拆分不创建第二套业务服务。

## 检索与管道

`SearchDataInterface` 是唯一检索门面。构造函数继续创建/接收同一 engine、embedding_tools、simility_tools，以及类目缓存和原配置字段。职责模块中的方法绑定到这个类，调用时接收同一个 self；职责模块不创建第二份引擎或缓存。原类级文件过滤常量与静态方法描述符保持不变。

五条挖掘管道各自保留原控制器、构造函数和 run 调度；stages、execution、accounting 中的方法使用原实例。不同管道的重试、超时、退出码和降级规则分别保留；两条文档管道完全相同的命令执行器共用 document/workflows/execution.py，其余执行器分别保留。相同的日志设置、预测成本与结果计数下沉 common/runtime，仍使用调用者原实例。

## HTTP 服务状态

检索 HTTP 服务的 `SEARCH_DATA_INTERFACE` 和 `MODIFY_KNOWLEDGE_HANDLE` 由 `retrieval/application/runtime.py` 单独持有；入口与 lifespan 按原顺序初始化它们。保持父进程启动和 worker 启动的既有语义，不以单进程计数替代 worker 验证。

业务本体的 `retrieval/ontology/repository.py` 用锁保护进程级 `_CONNECTOR` 的首次初始化，复用 `shared.database.mysql.MySQLConnector`（pool_size=5）；首次数据库请求才创建，不在导入、路由注册或 `/ontology/meta` 时连接。每次请求的 service/repository 无业务缓存；连接和字典游标在调用结束/异常时归还，写事务显式 REPEATABLE READ。不同 worker 各有一个池，配置变更后需按既有流程重启生效；不影响检索门面与 ES 对象生命周期。

任务服务的唯一状态模块为 `mining/tasks/state.py`：mysql_connector、task_pid_mapping、monitoring_thread、should_monitor、script_base_dir、task_queue、task_worker_thread、should_process_tasks、task_resource_usage、max_total_concurrency、current_resource_usage、resource_lock。业务函数读写模块属性；不按值导入会被重新赋值的计数或停止标志。保留原锁的保护范围、队列实现、线程启动/停止与 SQL 更新顺序。

语言模型由 `multilingual/runtime.py` 持有，加载过程仍在原启动流程发生。文件服务运行配置由 `shared/storage/runtime_state.py` 持有，缓存客户端与清缓存操作在 `shared/storage/service_runtime.py` 中各保留一份。

路由注册接受入口创建的 app；业务模块不创建 Flask/FastAPI 应用，不反向导入入口模块。HTTP 路径、方法、参数、返回、认证与异常传播保持既有协议。
