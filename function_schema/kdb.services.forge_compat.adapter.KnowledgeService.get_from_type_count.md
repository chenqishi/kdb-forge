# kdb.services.forge_compat.adapter.KnowledgeService.get_from_type_count

## Signature

`KnowledgeService.get_from_type_count(self, index_name: Optional[str], start: Optional[str]=None, end: Optional[str]=None, from_type: str='chat_auto') -> Tuple[bool, int, str]`

## Inputs

`self, index_name: Optional[str], start: Optional[str]=None, end: Optional[str]=None, from_type: str='chat_auto'`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

`index_name: Optional[str]`，`start=None`，`end=None`，`from_type="chat_auto"`。
原始单索引与参数先校验，再构建固定 high 来源统计 DSL。

## Outputs

Return an exact count for high-quality records of the requested source.

`Tuple[bool, int, str]`。空/null 索引为 `(True, 0, "")`；合法请求委托真实 Repository 严格 native count。
不存在的索引、ES/配置/分片错误为 `(False, 0, "统计失败")`。
日志只记录错误类型，不记录异常正文、堆栈、连接地址或凭据。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

无；只读 Elasticsearch `_count`，不生成向量、不建库、不检索文档。

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
