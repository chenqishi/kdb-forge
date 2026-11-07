# ES8 检索与索引路由

检索后端及 Python SDK 均为 Elasticsearch 8.17.x，PaaS 和 Serverless 使用同一实现。配置中的 `legacy` 召回模式是 ES8 单路融合模式的兼容别名，不表示支持 ES7。

## 引擎配置

`config/config_es_engine.json.example` 提供当前字段。单集群可使用 `hosts`、`username`、`password`；多集群使用命名 provider 与索引路由：

```json
{
  "es_version": "8.17",
  "index_name": "dedicated_test_index",
  "vector_fields": {"indexes_embedding": 1024},
  "default_provider": "serverless",
  "providers": {
    "serverless": {"hosts": ["https://serverless.example:9200"]},
    "paas": {"hosts": ["https://paas.example:9200"]}
  },
  "index_routes": {"qa_*": "serverless", "archive_*": "paas"},
  "extra_params": {"recall_mode": "dual"}
}
```

凭据使用实际私有配置。路由依次匹配精确索引、`fnmatch` 通配规则、默认 provider；同一 provider 共用 client。`pass` 是 `paas` 的兼容别名。

## 请求与数据行为

`retrieval/engines` 使用 ES8 named parameters，执行 BM25 与 native nested KNN；dual 模式分别召回并按 `_index + _id` 去重。分页接口采用 BM25，避免将 KNN 与深分页混用。原有响应完整性和分片检查必须保留，不把部分响应当作完整结果。

新建索引的 `indexes.embedding` 为可索引 `dense_vector`，使用 cosine 与 HNSW。向量维度来自实际配置与模型，不能猜测。已有索引不满足 native KNN mapping 时应显式失败；dense_vector 的索引属性不能原地更改，需要先建立正确目标 mapping，再在明确范围内 reindex 并修改路由，不能先删除原索引。

`SearchDataInterface` 保留类目归一化、条件、数据处理及缓存行为；独立 Forge 协议通过适配器委托同一实现。count-only 工厂不初始化 embedding 或创建索引。`get_from_type_count` 要求调用方提供单个原物理索引名，参数校验拒绝通配符、多索引表达式和非法名称；双时间才添加本地秒级闭区间，不隐式添加审核或软删条件。

真实集成验证需要有效的 ES8.17 凭据、确认过 mapping 的专用测试索引，以及明确的读写范围。离线请求契约测试不等同真实召回质量验证。
