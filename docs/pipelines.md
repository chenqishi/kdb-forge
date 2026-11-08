# 挖掘管道与任务队列

五条管道的业务实现分别归入 document、web、chat，通过工程入口启动，使用当前解释器和明确的运行目录：

| `task_type` | 模块 |
|---|---|
| `document_qa_mining` | `kdb.entrypoints.cli.mining.document_qa` |
| `document_qa_segment_mining` | `kdb.entrypoints.cli.mining.document_qa_segment` |
| `chat_qa_mining` | `kdb.entrypoints.cli.mining.chat_qa` |
| `html_qa_segment_mining` | `kdb.entrypoints.cli.mining.html_qa_segment` |
| `excel_qa_segment_upload` | `kdb.entrypoints.cli.mining.excel_qa_segment_upload` |

```bash
python -m kdb.entrypoints.cli.mining.document_qa_segment --script-dir "$PWD" --task-id TASK_ID --task-info '{"files":[],"index_name":"dedicated_test_index"}'
python -m kdb.mining.tasks.submission.local_batch --tasks-file /absolute/path/to/tasks.json --workers 3
```

示例展示参数形式，空文件列表不会产生有效任务。真实 `task_info` 应来自调用方或已有数据，不能猜测字段格式。配置、输入、任务状态与输出均按实际运行目录解析；本地批量入口可使用 `KDB_PYTHON` 覆盖解释器。管道会调用真实 SQL、模型、抓取、对象存储和 ES，不能直接运行当离线 smoke。

## HTTP 任务队列

`off_task` 的 `POST /start_task` 接收 `task_type` 和 `task_info`，先写 SQL 任务记录再入队，立即返回 `task_id` 与队列/资源占用状态。`GET|POST /task_info` 查询，`POST /stop_task` 停止，`POST /restart_task` 重新排队，`GET /health` 返回队列和资源信息。`POST /task_access` 当前只估算 `document_qa_segment_mining`。

`config/task_resource_config.json` 可设置 `max_total_concurrency` 与 `task_resource_usage`。运行中各任务的资源权重总和不得超出上限，任务结束、失败或停止后释放资源。缺配置的任务权重为 1。资源文件加载可能覆盖 `--max-concurrency`，以实际生效配置为准。

队列位于内存，服务重启不会自动恢复待执行条目；SQL 记录保存状态，不等同完整队列持久化。任务 ID 包含生成时刻，不承诺相同请求自动去重。重启或重提任务前应核对原任务、子进程和产物状态。

## 阶段与具体开关

文档与 HTML 的 QA/segment 管道依次执行解析或抓取、多模态处理、翻译、QA 生成、质量处理、格式转换、QA 插入、段落生成及段落插入。Excel 上传按表头/样本识别后选择标准 QA、列映射或非结构化文档处理分支。各阶段通过任务目录中的 JSON/JSONL 文件交接，实际阶段顺序由相应控制器的 `run_all_stages` 定义。

`document_qa_segment` 与 `html_qa_segment` 的 `task_info` 支持以下开关：

| 字段 | 缺省值与实际行为 |
|---|---|
| `enable_context_enrichment` | `false`；启用后执行业务上下文构建及通用质量后处理阶段 |
| `enable_chat_query_context` | `false`；是否将聊天问题意图加入业务上下文 |
| `enable_web_context` | `false`；是否启用外部网页上下文 |
| `llm_backend` | `dify`；向生成阶段传递后端选择 |
| `review_only` | `false`；为 true 时从执行计划中去掉 QA/段落 ES 插入阶段，仍产生中间/审核文件 |

业务上下文构建与通用质量后处理失败时，这两条管道会沿现有逻辑降级跳过，不能将启用开关视为完整质量验收。其他管道及直接入库 API 各自保留原有参数、默认索引与处理规则。

聊天 QA 的本地抽取/质量模块从 `resources/prompts/mining/chat_qa_extract/` 读取通用模板及匹配 client 的模板；模板选择、答案来源处理和字段格式分别以 `kdb.mining.chat.generation.extractor`、`kdb.mining.common.quality`、`kdb.mining.chat.generation.batch` 及其函数契约为准。

## 定时入口

定时接线位于 `kdb.entrypoints.scheduled`，业务实现位于 mining/tasks、mining/chat/reports 与 retrieval/maintenance，由 `scripts/scheduled/` 启动；主要入口为 `chat_mining.sh`、`auto_audit_all_indexes.sh`、`chat_learning_report.sh`。脚本保留锁、日志、水位和退出码语义，真实运行前配置解释器与当前运行资源。修改代码不会自动注册 cron 或启动任务。
