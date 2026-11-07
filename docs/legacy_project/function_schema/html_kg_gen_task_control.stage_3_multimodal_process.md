# html_kg_gen_task_control.stage_3_multimodal_process

## 描述
HTML 任务阶段 3。默认执行图片/OCR多模态处理；`skip_multimodal=true`（或
`firecrawl_only=true` 自动启用）时保留 stage 2 映射并直接成功，避免纯文本网页被图片或视频缩略图阻塞。

## Inputs

- `self.processed_result_file`
- `self.skip_multimodal`
- `self.is_use_firecrawl`

## Outputs

- 默认模式：`self.multimodal_result_file` 与 `self.multimodal_data_info_path`。
- 跳过模式：不生成多模态文件，后续阶段直接使用原映射中的 `firecrawl_content`。
- `bool`: 阶段成功与否。

## SQL

仅通过 `TaskStatusUpdater` 更新任务阶段；不直接读写业务表。
