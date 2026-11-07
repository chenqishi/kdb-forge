# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._require_full_update_source

## Signature

`EsSearchInterfaceES8._require_full_update_source(client: Any, indexes: Sequence[str]) -> None`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: ES client and physical index names used for conditional writes. Outputs: success only if get_mapping returns mapping entries whose stored _source is enabled and has no includes/excludes. Raise before bulk on disabled/filtered/malformed source metadata; never claim request source=True can recover storage-side exclusion. Full-source reindex migration is an already-required target precondition. Pure metadata read, no SQL/mapping writes. Aliases may resolve several mapping entries; every actual mapping must be complete.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
