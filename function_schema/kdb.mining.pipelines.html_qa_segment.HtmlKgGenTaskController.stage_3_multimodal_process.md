# kdb.mining.pipelines.html_qa_segment.HtmlKgGenTaskController.stage_3_multimodal_process

## Signature

`HtmlKgGenTaskController.stage_3_multimodal_process(self)`

## Description

HTML 任务阶段 3。默认执行图片/OCR多模态处理；`skip_multimodal=true`（或
`firecrawl_only=true` 自动启用）时保留 stage 2 映射并直接成功，避免纯文本网页被图片或视频缩略图阻塞。

## Inputs

- `self.processed_result_file`
- `self.skip_multimodal`
- `self.is_use_firecrawl`

现有参数签名：`self`。控制器继续从 task_info、script_dir、任务文件读取原有字段；不改变默认值或参数位置。

## Outputs

- 默认模式：`self.multimodal_result_file` 与 `self.multimodal_data_info_path`。
- 跳过模式：不生成多模态文件，后续阶段直接使用原映射中的 `firecrawl_content`。
- `bool`: 阶段成功与否。

阶段3：多模态处理

## SQL

仅通过 `TaskStatusUpdater` 更新任务阶段；不直接读写业务表。

## 路径和子进程契约

正式入口使用当前解释器 `sys.executable -m kdb.*`；仅替换旧脚本定位，不修改子命令、业务 argv、重定向、阶段顺序、工作目录、成功/失败返回及异常处理。环境经 `kdb.shared.config.paths.subprocess_env` 继承，仅前置当前 src 到 PYTHONPATH。聊天控制器继续加载可选 LLM env、独立进程组、任务总超时与 TERM/KILL 规则。日志预览仅有界读取头500字符/尾1000字符。

## SQL / ES

本次仅迁移代码入口，无新增 SQL 或 ES 字段。任务状态更新仍经 TaskStatusUpdater，原任务表 dops_task_kggen_info 及 task_id/task_stage/run_status/task_result 等字段不变；索引写入仍由现有 insert_data_to_search_index 接收相同 argv。上下文构建在原开关启用时经现有实现读取 data_chat_history，SQL 与字段遵循被调用函数原 schema。

## Source

`src/kdb/mining/pipelines/html_qa_segment.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
