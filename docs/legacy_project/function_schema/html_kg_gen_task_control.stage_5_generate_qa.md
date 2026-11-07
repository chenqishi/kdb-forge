# html_kg_gen_task_control.stage_5_generate_qa

## 描述
HTML 任务阶段 5：调用 `knowledge_html_clear_by_dify.run_batch_clear_html_content` 生成 QA。新增上下文参数透传；未启用时命令与旧逻辑等价。

## Inputs
无显式参数，读取翻译/处理后的映射文件、`is_need_translated`、`skip_multimodal`、
`is_use_firecrawl` 和 `_qa_context_cli_args()`。未翻译的纯文本任务直接读取 `firecrawl_content`。

## Outputs

| 产物 | 说明 |
|------|------|
| self.qa_result_file | QA 映射文件 |
| bool | 阶段成功与否 |

## SQL
不读写 SQL。
