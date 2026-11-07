# kdb.mining.query_analysis.wayfair_unanswered_review.rewrite_queries

## Signature

`rewrite_queries(queries: Sequence[str], model: str=DEFAULT_REWRITE_MODEL, batch_size: int=10, max_retries: int=3) -> Dict[str, dict]`

## Description

用 DeepSeek 官方模型把聊天口语 query 做「多次转换/补全」，产出用于检索的多条改写 query。
目的是提升召回：原始聊天 query 常有指代不明、缺平台词、错别字、口语缩写，直接检索会假阴性
（明明库里有知识却检索不到，被误判成「知识缺失」）。

每条原始 query 产出：
- `normalized`：补全平台/主语后的自包含问句（1 条）
- `variants`：换同义表述/术语的等价问法（<=3 条）
- `keywords`：核心关键词串（1 条）
无效 query（寒暄、纯噪声、无法判断意图）标 `skip=true`，不进入检索。

批量调用（默认 10 条/批）以省 token；模型输出坏 JSON 时按括号配平截取 + 重试，
参考 `MEMORY.md` 中 payoneer 去重的教训（flash 类模型约 20% 会吐坏 JSON）。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| queries | list[str] | 是 | 去重后的原始 query |
| model | str | 否 | 默认 `deepseek-v4-flash` |
| batch_size | int | 否 | 每批条数，默认 10 |
| max_retries | int | 否 | 坏 JSON 重试次数，默认 3 |

## Outputs

| 类型 | 说明 |
|------|------|
| dict[str, dict] | `{原始query: {"normalized": str, "variants": list[str], "keywords": str, "skip": bool, "skip_reason": str}}`；模型失败时降级为 `{"normalized": 原文, "variants": [], "keywords": ""}` |

## SQL

无。

## Source

`src/kdb/mining/query_analysis/wayfair_unanswered_review.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
