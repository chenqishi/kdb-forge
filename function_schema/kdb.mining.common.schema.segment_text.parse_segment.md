# kdb.mining.common.schema.segment_text.parse_segment

## Signature

`parse_segment(text, use_keywords=True)`

## Inputs

段落文本，use_keywords=True。

## Outputs

按原正则移除关键词/标签/属性行并提取字段；use_keywords=False 时不输出 keywords。

## SQL

无直接 SQL。

## Source

`src/kdb/mining/common/schema/segment_text.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
