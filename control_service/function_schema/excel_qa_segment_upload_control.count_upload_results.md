# excel_qa_segment_upload_control.count_upload_results

## 描述
统计结构化 Excel 上传入库文件的 JSON Lines 行数，并附加 Excel 自动路由元信息。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| self.index_input_file_path | str | 是 | 当前入库 JSON Lines 文件 |
| self.excel_classification | Dict[str, Any] | 否 | Excel 路由结果 |

## Outputs

| 类型 | 说明 |
|------|------|
| Dict[str, Any] | `upload_count` 加 `excel_process_mode`、`mapping_confidence`、`mapping_reason` |

## 逻辑

1. 若统计文件不存在，返回 `upload_count=0` 并附加路由元信息。
2. 逐行解析 JSON Lines，成功解析一行计数一次，坏行跳过并记录 warning。
3. 返回统计结果和 `_excel_route_result_fields()`。

## SQL
无。
