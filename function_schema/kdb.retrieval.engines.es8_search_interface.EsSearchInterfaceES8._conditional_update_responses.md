# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._conditional_update_responses

## Signature

`EsSearchInterfaceES8._conditional_update_responses(self, binding: SimpleNamespace, names: Sequence[str], query: Dict[str, Any], update_fields: Dict[str, Any], requests_per_second: int, conflicts: str) -> Iterator[Dict[str, Any]]`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: validated provider binding, original physical indexes, raw query, ordered update fields, requests_per_second, abort/proceed. Outputs: checked response(s); Serverless uses existing PIT/full-source/CAS bulk adapter; PaaS retains native update_by_query script and original parameters. Full-source guard prevents destructive replacement of an index whose stored source is disabled or filtered; migration has rebuilt target indexes with complete stored source. Do not modify provider/name/config, broaden query, or fall back after partial failure. Errors visible to existing caller contract. No SQL. Real writes not authorized this turn.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
