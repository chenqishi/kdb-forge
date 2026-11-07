# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.load_search_engine

## Signature

`SearchDataInterface.load_search_engine(self, config_path: str, **kwargs) -> SearchEngine`

## Inputs

旧 ES 配置路径与旧 loader 的可选 kwargs。

## Outputs

ES8.17 `RoutedLegacyEngine`。

## SQL

无；读取本地配置并连接 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
