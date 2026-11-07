# html_kg_gen_task_control._qa_context_cli_args

## 描述
构造 HTML QA 与 HTML segment 脚本的上下文参数字符串。未启用上下文增强时返回空字符串。

## Inputs
无显式参数，读取 `self.enable_context_enrichment`、`self.business_context_path`、`self.quality_profile`、`self.llm_backend`、`self.llm_model_name`、`self.llm_provider`。

## Outputs

| 类型 | 说明 |
|------|------|
| str | shell CLI 参数片段，路径和文本字段经 `shlex.quote` 处理 |

## SQL
不读写 SQL。
