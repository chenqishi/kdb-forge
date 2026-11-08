# kdb.mining.common.generation.long_qa.fallback_page_segments

## Signature

`fallback_page_segments(hard_chunk, max_pages=QA_MAX_PAGES)`

## Description

Dify 分段模型无有效输出时，按固定页数为当前硬窗口生成兜底段落，保证后续 QA 抽取仍能继续。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| hard_chunk | dict | 是 | 当前硬窗口，格式 `{"pages": [start_page, end_page]}` |
| max_pages | int | 否 | 兜底段落最大页数，默认 10 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 兜底段落列表，格式 `{"title": "第x-y页", "pages": [x, y]}` |

## 行为约束

- 只按页边界切分，不拆页。
- 覆盖整个硬窗口，不重叠、不跳页。

## SQL

不读写数据库。

## Source

`src/kdb/mining/common/generation/long_qa.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
