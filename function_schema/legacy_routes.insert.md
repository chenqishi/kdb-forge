# legacy_routes.insert

## Inputs

旧 `POST /insert` 请求体：`index_names` 必填，其他字段与 InsertRequest。

## Outputs

`InsertResponse(success,message)`；写入失败仍 HTTP 200，参数缺失 HTTP 422/400。

## SQL

无 SQL；调用 ES8 Service `insert_data`。
