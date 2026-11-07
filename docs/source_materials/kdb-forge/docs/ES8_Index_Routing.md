# ES 8.17 按索引路由

## 支持范围

本项目只运行 Elasticsearch 8.17.x，PaaS 与 Serverless 都使用同一套 ES8 客户端、
schema 和查询实现。不增加 ES7 驱动或降级分支。文中的“旧配置兼容”只指 JSON
字段/业务接口形式；`legacy` 召回模式名只是 ES8 单路融合模式的别名，不代表 ES7。

## 配置

`config/config_es_engine.json` 可以继续使用旧的单地址格式：

```json
{"hosts": ["https://..."], "username": "...", "password": "...", "index_name": "...", "vector_fields": {"indexes_embedding": 1024}}
```

混用 Aliyun Serverless/PaaS 时使用：

```json
{
  "es_version": "8.17",
  "default_provider": "serverless",
  "providers": {
    "serverless": {"hosts": ["https://..."], "username": "...", "password": "..."},
    "paas": {"hosts": ["https://..."], "username": "...", "password": "..."}
  },
  "index_routes": {"qa_*": "serverless", "archive_*": "paas"},
  "vector_fields": {"indexes_embedding": 1024},
  "extra_params": {"recall_mode": "dual"}
}
```

`pass` 是 `paas` 的兼容别名。路由匹配顺序是精确 index、`fnmatch` 通配规则、默认
provider；同一个 provider 的所有 index 共享一个 client。凭据只用于 client 构造，
不应写入日志或提交到代码库。

## 检索行为

`RoutedLegacyEngine` 生产路径不再注入旧 `EsSearchInterfaceOri`。它使用 ES8.17 Python
client 的 named parameters：`search(query=..., from_=..., source_excludes=...)`、
`update(doc=..., doc_as_upsert=...)`、`indices.create(mappings=..., settings=...)`、
`update_by_query(query=..., script=...)`。`search_multi` 在 dual 模式分别执行 BM25
和 native nested KNN，再按 `_index + _id` 去重；分页接口保持 BM25-only，避免把 KNN
和深分页 `from_` 混用。

新建索引时 `indexes.embedding` 是 `dense_vector(index=true, similarity=cosine,
index_options.type=hnsw)`。已有 ES7 索引如果该字段没有 `index=true`，`ensure_index`
会直接报迁移错误，因为 Elasticsearch 不允许原地改变 dense_vector 的索引属性；需要
新建目标索引并 reindex 文档。迁移顺序是：先用 rebuild mapping 创建新 index，再在同一
ES 集群执行 `_reindex`，最后把配置中的 route 指向新 index；不要删除旧 index 作为迁移
第一步。旧 `script_score` 只保留在旧仓库的对齐基线中，不会被重构版生产 CRUD 调用。

```json
POST _reindex
{
  "source": {"index": "old_test_case"},
  "dest": {"index": "test_case_v817"}
}
```

## 验证

```bash
python3 -m pip install 'elasticsearch>=8.17,<8.18'
python3 -m pytest -q -m 'not integration'
```

真实集成测试需要有效的 ES 8.17 凭据，并使用配置中的 `test_index_name`；该测试索引
必须已经是 native KNN mapping。不要用 ES7 旧索引直接测试，也不要用生产索引做写入
回环测试。
