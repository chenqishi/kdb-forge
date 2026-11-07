# kdb.services.forge_compat.api.legacy_routes.insert

## Signature

`insert(request: InsertRequest) -> InsertResponse`

## Inputs

旧 `POST /insert` 请求体：`index_names` 必填，其他字段与 InsertRequest。

## Outputs

`InsertResponse(success,message)`；写入失败仍 HTTP 200，参数缺失 HTTP 422/400。

## SQL

无 SQL；调用 ES8 Service `insert_data`。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
