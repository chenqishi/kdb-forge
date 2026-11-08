# kdb.mining.tasks.submission.local_batch.main

## Signature

`main()`

## Description

本机批量跑文档挖掘（不投递线上任务服务）。

## Inputs

- `--tasks-file` (必填): `build_doc_mining_tasks.py` 产出的 tasks.json
- `--out`: task_id 记录文件（撤回用），默认与 tasks-file 同目录
- `--workers` (默认 3) / `--limit` / `--log-level`
- `--skip`: 逗号分隔的文件名，跳过这些篇
- `--skip-from`: 已跑记录 json，自动跳过其中 `rc==0` 的篇目

现有参数签名：``。控制器继续从 task_info、script_dir、任务文件读取原有字段；不改变默认值或参数位置。

## Outputs

- 每篇一条 `{name, task_id, rc, secs, log}`，写入 `--out`（**每篇都落盘**，中途被杀也能撤回）

现有函数返回值与副作用保持不变。

## 注意

- `--limit 0` 是**假值**、会跑全量；限定篇目要用 `--skip` / `--skip-from`
- **`--skip-from` 必须在主批结束后读**：主批边跑边覆写记录文件，
  提前取快照会漏掉后完成的篇目 → 重复灌库
- 三个前置条件见模块 docstring（python shim / PYTHONPATH / py38 解释器）

## SQL

不直接读写 MySQL；下游各阶段写 ES 索引 `payoneer_olive`（知识条目，`del_flag`/`task_id`/`audit_result`）。

## 路径和子进程契约

正式入口使用当前解释器 `sys.executable -m kdb.*`；仅替换旧脚本定位，不修改子命令、业务 argv、重定向、阶段顺序、工作目录、成功/失败返回及异常处理。环境经 `kdb.shared.config.paths.subprocess_env` 继承，仅前置当前 src 到 PYTHONPATH。聊天控制器继续加载可选 LLM env、独立进程组、任务总超时与 TERM/KILL 规则。日志预览仅有界读取头500字符/尾1000字符。

## SQL / ES

本次仅迁移代码入口，无新增 SQL 或 ES 字段。任务状态更新仍经 TaskStatusUpdater，原任务表 dops_task_kggen_info 及 task_id/task_stage/run_status/task_result 等字段不变；索引写入仍由现有 insert_data_to_search_index 接收相同 argv。上下文构建在原开关启用时经现有实现读取 data_chat_history，SQL 与字段遵循被调用函数原 schema。

## Source

`src/kdb/mining/tasks/submission/local_batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
