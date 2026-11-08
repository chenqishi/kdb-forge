# kdb.mining.web.workflows.qa_segment.stages.stage_6_qa_quality

## Signature

`stage_6_qa_quality(self)`

## Inputs

现有参数签名：`self`。控制器继续从 task_info、script_dir、任务文件读取原有字段；不改变默认值或参数位置。

## Outputs

阶段6：QA质量处理

## 路径和子进程契约

正式入口使用当前解释器 `sys.executable -m kdb.*`；仅替换旧脚本定位，不修改子命令、业务 argv、重定向、阶段顺序、工作目录、成功/失败返回及异常处理。环境经 `kdb.shared.config.paths.subprocess_env` 继承，仅前置当前 src 到 PYTHONPATH。聊天控制器继续加载可选 LLM env、独立进程组、任务总超时与 TERM/KILL 规则。日志预览仅有界读取头500字符/尾1000字符。

## SQL / ES

本次仅迁移代码入口，无新增 SQL 或 ES 字段。任务状态更新仍经 TaskStatusUpdater，原任务表 dops_task_kggen_info 及 task_id/task_stage/run_status/task_result 等字段不变；索引写入仍由现有 insert_data_to_search_index 接收相同 argv。上下文构建在原开关启用时经现有实现读取 data_chat_history，SQL 与字段遵循被调用函数原 schema。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.mining.web.pipeline.HtmlKgGenTaskController.stage_6_qa_quality`

## Source

`src/kdb/mining/web/workflows/qa_segment/stages.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
