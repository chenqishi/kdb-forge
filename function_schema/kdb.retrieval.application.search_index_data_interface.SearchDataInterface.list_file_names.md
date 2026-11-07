# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.list_file_names

## Signature

`SearchDataInterface.list_file_names(self, index_name: str, keyword: str=None, size: int=200, from_type_norm: Optional[str]=None) -> List[Dict[str, Any]]`

## Inputs

`index_name: str, keyword: str=None, size: int=200, from_type_norm: Optional[str]=None`。
新增参数置于末尾，保留旧的三个位置参数顺序。
`from_type_norm` 省略/null/空串/仅空白时不施加来源条件；非空时按 trim 后的值执行 term 精确过滤。

索引、可选关键词和 size。

## Outputs

保持 `[{value, doc_count, type_count}]` 和按文件名聚合的行为。
同名文件在当前筛选范围内合并；无文件名记录不补 missing 桶。

文件名、文档数和 data_type 分布列表。

## SQL / Storage

无 SQL。ES 只读 `agg_terms`：始终 `del_flag=0`，可选
`term(from_type_norm)`、转义并限长的文件名 wildcard，原 data_type 子聚合。
不用共享 `_scope_filters` 构造本接口查询；后者继续供删除相关操作使用，
固定来源白名单 document/html/manual 不变。

## Compatibility

用户明确要求空值不筛来源，因此旧调用省略参数时也改为列全部来源。
这不授权扩大删除范围，也不修复既存 ES8 子聚合 type_count 契约问题。

## SQL

无；读 Elasticsearch aggregation。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
