# excel_qa_segment_upload_control.stage_2_excel_to_json

## 描述
将下载到本地的 Excel 审核文件先做统一识别路由，再按路由结果处理：

- `standard_qa` / `mapped_qa`：转换为搜索入库前的 canonical JSON Lines 文件。
- `unstructured_excel`：不报错中断，切换到 `document_qa_segment_mining` 非结构化文档知识流程。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| self.downloaded_excel_path | str | 是 | 阶段 1 下载后的 Excel 本地路径，支持文件名包含空格 |
| self.json_file_path | str | 是 | 输出 JSON Lines 文件路径 |
| self.task_info | Dict[str, Any] | 是 | 任务参数，除 `files` 外会作为 extra 字段传给转换脚本 |
| self.task_id | str | 是 | 任务 ID，用于更新阶段状态和日志 |
| self.excel_classification | Dict[str, Any] | 否 | 函数内写入 `classify_excel_upload` 的结果 |
| self.excel_process_mode | str | 否 | 函数内写入 `standard_qa` / `mapped_qa` / `unstructured_excel` |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 结构化转换成功且输出文件存在时返回 True；非结构化 fallback 完成时返回 True；失败返回 False |

## 逻辑

1. 将任务阶段更新为 `excel_to_json`。
2. 校验 `downloaded_excel_path` 存在。
3. 调用 `commons.schema_trans.classify_excel_upload(downloaded_excel_path)` 读取表头/sample rows 并写入路由结果。
4. 当 mode 为 `unstructured_excel` 时，调用 `_run_unstructured_document_fallback()`，成功后设置 `document_fallback_completed=True` 并返回。
5. 当 mode 为 `standard_qa` / `mapped_qa` 时，从 `task_info` 中移除 `files`，构造 `extra_field_name_dict`，默认补齐 `audit_result=1`。
6. 使用参数列表构造 `commons/schema_trans.py trans_web_excel_to_json_file` 命令，避免 Excel 文件名中的空格被 shell 拆分。
7. 调用 `_run_command` 执行转换。
8. 检查输出文件存在，统计 JSON Lines 行数，并将 `index_input_file_path` 指向结构化 JSONL。

## SQL

不直接访问 SQL；阶段状态更新由 `TaskStatusUpdater.update_task_stage` 负责。
