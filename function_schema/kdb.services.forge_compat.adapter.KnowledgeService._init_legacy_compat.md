# kdb.services.forge_compat.adapter.KnowledgeService._init_legacy_compat

## Signature

`KnowledgeService._init_legacy_compat(self, legacy_config: Optional[Mapping[str, Any]]=None) -> None`

## Inputs

`self, legacy_config: Optional[Mapping[str, Any]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

Initialise attributes expected by old callers.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
