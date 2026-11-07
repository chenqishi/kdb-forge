# kdb.mining.generation.processing.knowledge_clear_by_dify_model_longcontent.normalize_segments_in_chunk

## Signature

`normalize_segments_in_chunk(segments, hard_chunk)`

## Description

将 Dify 分段模型返回的页码范围限制在当前硬窗口内，过滤无法解析或完全越界的段落。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| segments | list[dict] | 是 | `parse_dify_segment` 解析出的段落列表，可为空 |
| hard_chunk | dict | 是 | 当前硬窗口，格式 `{"pages": [start_page, end_page]}` |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 归一化后的段落列表，格式 `{"title": str, "pages": [start_page, end_page]}` |

## 行为约束

- 段落开始页小于硬窗口开始页时 clamp 到窗口开始页。
- 段落结束页大于硬窗口结束页时 clamp 到窗口结束页。
- 页码无法转为整数、或 clamp 后 `start_page > end_page` 的段落会被跳过。
- 按起止页排序并去重。

## SQL

不读写数据库。

## Source

`src/kdb/mining/generation/processing/knowledge_clear_by_dify_model_longcontent.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
