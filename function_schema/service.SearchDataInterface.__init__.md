# SearchDataInterface.__init__

## Inputs
旧构造签名 `search_engine=None, config_path=None, **kwargs`；支持 `index_name`、旧 ES 单地址
配置和注入的 `embedding_client`。

## Outputs
创建带完整旧服务公开接口的 ES8.17 兼容服务实例。

## SQL
无；配置读取本地 JSON，数据操作通过 Elasticsearch。
