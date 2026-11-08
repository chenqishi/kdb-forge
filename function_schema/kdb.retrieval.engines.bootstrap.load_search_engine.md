# kdb.retrieval.engines.bootstrap.load_search_engine

## Signature

`load_search_engine(self, config_path: str, **kwargs) -> SearchEngine`

## Inputs

旧 ES 配置路径与旧 loader 的可选 kwargs。

## Outputs

通过 `kdb.retrieval.engines.factory.EsSearchInterface` 工厂构造的原业务检索引擎；当前运行配置使用 ES8.17。配置路径和额外参数按原调用传入，不增加另一套服务或引擎适配层。

## SQL

无；读取本地配置并连接 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.load_search_engine`

## Source

`src/kdb/retrieval/engines/bootstrap.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
