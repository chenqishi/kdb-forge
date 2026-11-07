# kdb.services.forge_compat.api.legacy_routes._category_infos

## Signature

`_category_infos(request: InsertRequest) -> Optional[List[Dict[str, Any]]]`

## Inputs

`InsertRequest` 的 categoryId/categoryName 或 category_infos。

## Outputs

返回归一化 category_infos；ID 转字符串；数量不一致抛 HTTP 400。

## SQL

无。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
