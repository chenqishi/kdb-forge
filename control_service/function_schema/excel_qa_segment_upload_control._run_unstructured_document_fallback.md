# excel_qa_segment_upload_control._run_unstructured_document_fallback

## 描述
不可映射 Excel 的 fallback。复用 `control_service.document_qa_segment_mining.DocumentQAMiningTaskController` 完整文档知识流程处理 `.xlsx/.xls`，避免在 Excel 上传控制器中复制文档解析、QA 生成、过滤和入库阶段。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| self.script_dir | str | 是 | 项目脚本目录 |
| self.task_id | str | 是 | 当前任务 ID |
| self.task_info | Dict[str, Any] | 是 | 原任务参数，会原样传入文档控制器 |
| self.excel_classification | Dict[str, Any] | 是 | 路由结果，用于补充 task_result |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 文档流程成功返回 True；导入、执行或结果更新异常返回 False |

## 逻辑

1. 延迟导入 `DocumentQAMiningTaskController`，避免结构化路径加载文档链路依赖。
2. 使用相同 `script_dir/task_id/task_info` 实例化并调用 `run_all_stages()`。
3. 成功后调用文档控制器 `count_qa_results()`，并追加 `_excel_route_result_fields()`。
4. 通过当前控制器的 `status_updater.update_task_result` 写入增强后的 task_result。

## SQL
不直接访问 SQL；文档控制器内部阶段和 `TaskStatusUpdater.update_task_result` 会按既有逻辑更新任务表。
