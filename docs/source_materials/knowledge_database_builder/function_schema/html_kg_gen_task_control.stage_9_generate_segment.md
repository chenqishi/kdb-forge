# html_kg_gen_task_control.stage_9_generate_segment

## 描述
HTML 任务阶段 9：调用 `knowlege_segment_builder_by_dify.run_batch_get_segment_knowledge_html_json` 生成段落知识。新增上下文参数透传；未启用时旧行为不变。

## Inputs
无显式参数，读取翻译后的 HTML 映射文件、`is_need_translated` 和 `_qa_context_cli_args()`。

## Outputs

| 产物 | 说明 |
|------|------|
| self.segment_knowledge_file_path | HTML segment JSONL |
| bool | 阶段成功与否 |

## SQL
不读写 SQL。
