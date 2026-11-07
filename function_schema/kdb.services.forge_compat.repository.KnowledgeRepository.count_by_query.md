# kdb.services.forge_compat.repository.KnowledgeRepository.count_by_query

## Signature

`KnowledgeRepository.count_by_query(self, index_name: str, query: Dict[str, Any]) -> int`

## Inputs

`self, index_name: str, query: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

显式原始 `index_name: str` 与原始 `query: Dict[str, Any]`。

## Outputs

Count a supplied index and raw DSL without index creation or defaults.

`int`，直接委托 engine.count_by_query(..., require_complete=True)，错误上抛。
不调用 _idx、不使用默认索引、不归一化或扩展索引、不附加业务条件。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

无；只读 ES8 native `_count`，不 ensure/create。

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
