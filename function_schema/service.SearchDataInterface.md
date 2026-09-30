# SearchDataInterface

## Inputs
兼容旧构造函数：`SearchDataInterface(search_engine=None, config_path=None, **kwargs)`。
`config_path` 可以指向旧 `config_for_search_index.json`；其中的单地址 ES 配置会在内存中
转换为 ES8.17 provider 配置，实际请求由 `RoutedLegacyEngine` 发送。

## Outputs
暴露旧 `SearchDataInterface` 的公开方法名和参数契约，包含 `insert_data`、
`search_data_by_query`、`search_data_by_multi_query`、`web_search_data`、批量插入、
查重、类目、文件名查询/预览/软删除等。

## SQL
无；数据读写 Elasticsearch，删除快照写 JSONL 文件。
