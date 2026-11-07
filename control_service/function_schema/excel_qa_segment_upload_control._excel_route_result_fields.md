# excel_qa_segment_upload_control._excel_route_result_fields

## 描述
返回 Excel 自动路由元信息，供结构化上传统计结果和非结构化 fallback 任务结果统一写入 `task_result`。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| self.excel_process_mode | str | 否 | 当前 Excel 路由模式 |
| self.excel_classification | Dict[str, Any] | 否 | `classify_excel_upload` 的完整结果 |

## Outputs

| 类型 | 说明 |
|------|------|
| Dict[str, Any] | 包含 `excel_process_mode`、`mapping_confidence`、`mapping_reason` |

## SQL
无。
