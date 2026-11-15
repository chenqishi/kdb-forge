# tests.retrieval.test_multimodal_content_assembly.test_join_multimodal_empty_text_retains_distinct_maintenance_behavior

## Signature

`test_join_multimodal_empty_text_retains_distinct_maintenance_behavior(part)`

## Inputs

只有一个 text 项的列表；content 为 None 或缺少 content 字段。

## Outputs

正式拼接函数保留 None 返回，维护工具拼接函数返回空字符串。该断言记录已有差异，防止把两份实现直接当作完全等价合并。

## SQL

无 SQL、网络、模型或子进程。

## Source

`tests/retrieval/test_multimodal_content_assembly.py`
