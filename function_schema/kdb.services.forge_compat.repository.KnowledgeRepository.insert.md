# kdb.services.forge_compat.repository.KnowledgeRepository.insert

## Signature

`KnowledgeRepository.insert(self, data: Dict[str, Any], index_name: Optional[str]=None, refresh_imm: bool=False) -> bool`

## Inputs

`self, data: Dict[str, Any], index_name: Optional[str]=None, refresh_imm: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

插入/upsert 一条文档。

前置约定：data 必须含 `_id`；`indexes[].embedding` 已是 1024 维 list。
委托 ES8 `engine.insert`（校验维度、过滤零向量、update(doc_as_upsert=True)）。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
