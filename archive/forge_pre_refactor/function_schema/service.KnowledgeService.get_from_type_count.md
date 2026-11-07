# KnowledgeService.get_from_type_count

## Inputs
`index_name: Optional[str]`，`start=None`，`end=None`，`from_type="chat_auto"`。
原始单索引与参数先校验，再构建固定 high 来源统计 DSL。

## Outputs
`Tuple[bool, int, str]`。空/null 索引为 `(True, 0, "")`；合法请求委托真实 Repository 严格 native count。
不存在的索引、ES/配置/分片错误为 `(False, 0, "统计失败")`。
日志只记录错误类型，不记录异常正文、堆栈、连接地址或凭据。

## SQL
无；只读 Elasticsearch `_count`，不生成向量、不建库、不检索文档。
