# search_routes.FromTypeCountRequest

## Inputs
JSON：index_name/indexName 可选字符串或 null；from_type 缺省 chat_auto；start/end 可选时间或 null。

## Outputs
Pydantic 请求对象。未知字段拒绝（422）。两索引别名同时存在必须相同；相同时删除副键后校验。
check_index_aliases 检查冲突；check_index/check_source/check_time 分别调用纯本地校验函数。
显式 from_type null/空/非字符串、非法单边时间等均返回 422，空索引不能绕过参数校验。

## SQL
无；校验不初始化 Service、不请求 ES。
