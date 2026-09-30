# LegacySearchDataInterfaceMixin

## 功能
为 `KnowledgeService` 提供旧 `SearchDataInterface` 的公开方法名和参数契约。方法不得绕过
`KnowledgeRepository`/ES8.17 路由引擎，不得重新接入 ES7 `body=` API。
兼容范围不包含挖掘侧的 Payoneer Olive 自动类目推断。

## Inputs/Outputs
- `insert_data`、`batch_insert_data`：保留旧插入参数和 `(success, message)` 返回值。
- `search_data`：保留旧原始查询入口，返回文档列表。
- `search_data_by_query`、`search_data_by_multi_query`、`web_search_data`：保留旧参数、返回
  `(docs, total)`，并保留条件转换、相似度、分页、score 归一化和多模态 URL 副作用。
- 类目、查重、文件名预览/软删除方法：保留旧参数和返回结构；ES 请求统一由
  `RoutedLegacyEngine` 的 ES8 named API 执行。

## SQL
无 SQL。数据读写对象为 Elasticsearch index/document。
