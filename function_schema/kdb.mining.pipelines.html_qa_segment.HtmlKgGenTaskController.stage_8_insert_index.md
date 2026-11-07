# kdb.mining.pipelines.html_qa_segment.HtmlKgGenTaskController.stage_8_insert_index

## Signature

`HtmlKgGenTaskController.stage_8_insert_index(self)`

## Description

HTML 任务阶段 8：把 QA search-data 写入目标 ES 索引。任务可通过
`insert_is_need_llm` 覆盖索引配置中的重复知识 LLM 精判开关。

## Inputs

- `self.search_data_file_path`
- `self.index_name`
- `self.insert_is_need_llm`: `None` 时不追加命令行参数；布尔值时追加
  `--is_need_llm=true|false`。
- `self.insert_check_duplicate`: `None` 沿用索引配置；布尔值时追加
  `--check_duplicate=true|false`。

`False` 只关闭外部 LLM 精判，仍保留向量查重和数值阈值规则，不等于关闭查重。
`insert_check_duplicate=False` 才会完全关闭跨库查重；只应用于来源 URL 已去重、且按国家/租户
类目过滤时必须保留独立知识副本的任务。

现有参数签名：`self`。控制器继续从 task_info、script_dir、任务文件读取原有字段；不改变默认值或参数位置。

## Outputs

- `bool`: 入库子命令成功返回 True，否则 False。

阶段8：QA插入ES

## SQL / ES

不直接读写 SQL。通过 `insert_data_to_search_index` 写 `self.index_name` 指定的 ES 索引。

本次仅迁移代码入口，无新增 SQL 或 ES 字段。任务状态更新仍经 TaskStatusUpdater，原任务表 dops_task_kggen_info 及 task_id/task_stage/run_status/task_result 等字段不变；索引写入仍由现有 insert_data_to_search_index 接收相同 argv。上下文构建在原开关启用时经现有实现读取 data_chat_history，SQL 与字段遵循被调用函数原 schema。

## 路径和子进程契约

正式入口使用当前解释器 `sys.executable -m kdb.*`；仅替换旧脚本定位，不修改子命令、业务 argv、重定向、阶段顺序、工作目录、成功/失败返回及异常处理。环境经 `kdb.shared.config.paths.subprocess_env` 继承，仅前置当前 src 到 PYTHONPATH。聊天控制器继续加载可选 LLM env、独立进程组、任务总超时与 TERM/KILL 规则。日志预览仅有界读取头500字符/尾1000字符。

## Source

`src/kdb/mining/pipelines/html_qa_segment.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
