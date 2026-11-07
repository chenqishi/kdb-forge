# kdb.services.forge_compat.api.legacy_routes.delete

## Signature

`delete(request: DeleteRequest) -> DeleteResponse`

## Inputs

旧 `POST /delete`：`id`、`index_names`、`refresh_imm`。

## Outputs

`DeleteResponse(success,message)`；异常转 success=false。

## SQL

无 SQL；调用 ES8 Service 硬删除。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
