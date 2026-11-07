# kdb.services.forge_compat.api.legacy_routes.InsertRequest.get_ext_info_with_extra_fields

## Signature

`InsertRequest.get_ext_info_with_extra_fields(self, defined_fields: Optional[List[str]]=None) -> Dict[str, Any]`

## Inputs

可选 `defined_fields` 字段名列表；请求体中的显式 `ext_info` 与 Pydantic extra 字段。

## Outputs

返回合并后的 `ext_info` 字典；`categoryId`/`categoryName` 不进入扩展字段。

## SQL

无。

## Source

`src/kdb/services/forge_compat/api/legacy_routes.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
