# excel_qa_segment_upload_control.run_all_stages

## 描述
执行 Excel QA 上传任务的完整阶段链路。结构化路径执行下载、识别/转换、图片理解、入库和结果统计；不可映射 Excel 会在转换阶段切到文档知识流程，并跳过后续结构化阶段。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| self.task_id | str | 是 | 当前任务 ID |
| self.document_fallback_completed | bool | 否 | 非结构化 fallback 是否已完成 |

## Outputs

| 类型 | 说明 |
|------|------|
| bool | 全流程成功返回 True；任一阶段失败返回 False |

## 逻辑

1. 任务开始时预测成本。
2. 依次执行：文件下载、Excel 识别/转换、结构化图片理解、插入索引。
3. 任一阶段失败则更新任务状态为 error 并返回 False。
4. 若 `stage_2_excel_to_json` 已完成非结构化 document fallback，则直接返回 True，不再执行结构化后续阶段。
5. 结构化路径完成后计算实际成本、统计上传结果、写入 task_result，并将任务状态更新为 completed。

## SQL
不直接访问 SQL；任务状态和结果通过 `TaskStatusUpdater` 更新。
