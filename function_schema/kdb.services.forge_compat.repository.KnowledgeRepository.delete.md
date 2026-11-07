# kdb.services.forge_compat.repository.KnowledgeRepository.delete

## Signature

`KnowledgeRepository.delete(self, data_id: str, index_name: Optional[str]=None, refresh: bool=False) -> bool`

## Inputs

`self, data_id: str, index_name: Optional[str]=None, refresh: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

按 _id 硬删除。委托旧 `engine.delete`。

操作下仍可能 read-after-delete 看到旧版本，故 refresh=True 时额外
强制刷新索引一次，保证立即不可见。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
