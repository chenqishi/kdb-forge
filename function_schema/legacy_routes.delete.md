# legacy_routes.delete

## Inputs

旧 `POST /delete`：`id`、`index_names`、`refresh_imm`。

## Outputs

`DeleteResponse(success,message)`；异常转 success=false。

## SQL

无 SQL；调用 ES8 Service 硬删除。
