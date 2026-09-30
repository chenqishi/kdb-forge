# legacy_routes.InsertRequest.get_ext_info_with_extra_fields

## Inputs

可选 `defined_fields` 字段名列表；请求体中的显式 `ext_info` 与 Pydantic extra 字段。

## Outputs

返回合并后的 `ext_info` 字典；`categoryId`/`categoryName` 不进入扩展字段。

## SQL

无。
