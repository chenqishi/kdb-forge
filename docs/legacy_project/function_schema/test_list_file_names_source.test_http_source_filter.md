# test_list_file_names_source.test_http_source_filter

## Inputs / Outputs
复用 `fixture_service` 和 `post_query`，真实 FastAPI 模型/处理器与业务方法；
以 Mock 替换 engine.agg_terms 聚合边界。参数化省略、null、空串、空白、
document/html/manual/auto_learning/未知值，以及两种 provider 的索引。
断言 HTTP 200、原有返回结构、ES 查询包含 del_flag=0 和准确的可选来源 term、
文件名 wildcard 转义、size 和子聚合传递，删除白名单仍保留。

## Side effects / SQL
仅进程内测试；不连接 ES，不写业务数据，不启动服务；无 SQL。
