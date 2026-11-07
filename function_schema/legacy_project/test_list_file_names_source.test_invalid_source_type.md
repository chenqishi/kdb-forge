# test_list_file_names_source.test_invalid_source_type

## Inputs / Outputs
真实 HTTP 模型收到数组、对象、数字、布尔等非字符串来源时返回 422，
不调用聚合。合法空值语义由 test_http_source_filter 覆盖。

## Side effects / SQL
复用离线 fixture_service；无真实网络或数据库读写，无 SQL。
