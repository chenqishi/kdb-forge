# kdb.services.forge_compat.repository.KnowledgeRepository.get

## Signature

`KnowledgeRepository.get(self, data_id: str, index_name: Optional[str]=None) -> Optional[Dict[str, Any]]`

## Inputs

`self, data_id: str, index_name: Optional[str]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

按 _id 取文档；返回 `{"_id":..., **_source}` 或 None。委托旧 `engine.get`。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
