# html_kg_gen_task_control.stage_4_translate_documents

## 描述
HTML 任务阶段 4。常规模式翻译 `content_with_multimodal_unsderstanding`；纯文本跳过多模态且
启用 Firecrawl 时，直接翻译 `firecrawl_content`。

## Inputs

- `self.processed_result_file`
- `self.is_need_translated`
- `self.skip_multimodal`
- `self.is_use_firecrawl`

## Outputs

- `self.translated_result_file`
- `bool`: 阶段成功与否。

## SQL

不读写 SQL。
