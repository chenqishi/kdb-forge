# kdb.mining.common.generation.long_qa.parse_dify_segment

## Signature

`parse_dify_segment(segment_answer)`

## Description

解析 Dify 分段模型返回文本，提取标题与页码范围。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| segment_answer | str\|None | 是 | Dify 分段返回文本；为空或非字符串时返回空列表 |

## Outputs

| 类型 | 说明 |
|------|------|
| list[dict] | 每项格式 `{"title": str, "pages": [start_page, end_page]}` |

## 行为

- 当前匹配格式为 `<标题> 第x页 第y页`。
- `segment_answer` 为空或非字符串时仅记录 warning，不抛异常。

## SQL

不读写数据库。

## Source

`src/kdb/mining/common/generation/long_qa.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
