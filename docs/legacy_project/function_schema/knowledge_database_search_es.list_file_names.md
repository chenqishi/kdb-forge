# knowledge_database_search_es.list_file_names

## Inputs
POST `/list_file_names`, `ListFileNamesRequest`：`index_name: str` 必填；
`keyword: Optional[str]=None`；`size: int=200`（1..1000）；
新增 `from_type_norm: Optional[str]=None`，单个来源字符串。
省略、null、空串、仅空白均表示不限制来源；非空值去除首尾空白后精确匹配。

## Outputs
原有 `success / values / total_count / message` 结构保持。
转发全部四个参数至真实业务 `SearchDataInterface.list_file_names`；
成功提示不再声称仅统计 document/html/manual。异常仍沿用原失败响应。

## Side effects / SQL
只读聚合，不涉及 SQL。始终只列未软删除记录（del_flag=0）。
仅改变列表来源过滤，不改变预览、文件名解析或删除方法的来源白名单。
