# kdb.services.forge_compat.api.legacy_routes._insert_document

## Signature

`_insert_document(request: InsertRequest) -> Dict[str, Any]`

## Inputs

旧 `InsertRequest`。

## Outputs

构造透传给 `KnowledgeService.insert_data` 的文档；路由控制字段移除，扩展字段保留。

## SQL

无；后续写 ES8。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
