# RoutedLegacyEngine

## 所属文件
`src/kdb/es/engine.py`

## Inputs
- ES engine 配置路径或已加载配置。
- `index_name` 默认索引、`vector_fields`、`extra_params.recall_mode`。
- `IndexClientRouter` 可注入测试 client。

## Outputs
兼容旧接口形状的 ES8.17 CRUD、混合检索、双路召回、分页检索和聚合接口；生产实现使用 named API 与 native KNN，不调用旧 ES7 `body/script_score`。
新增 `get_client_by_index(index_name)` 返回对应 ES8 client。

## Behavior
本地引擎负责 ES8 DSL、native KNN mapping、BM25/vector 分路及 `_index + _id` 合并；
跨 provider 多索引请求按 provider 分组，结果按分组顺序合并，total 求和。默认
`recall_mode` 为 `dual`；`search_multi_by_page` 保持 BM25 分页语义。

## SQL
无。
