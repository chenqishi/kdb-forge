# 旧 HTTP 11 路由兼容矩阵

旧服务来源：`knowledge_database_builder/knowledge_database_search_service/src/knowledge_database_search_es.py`。
本矩阵只描述接口和能力边界；所有兼容路径的 ES 请求都由本地 `KnowledgeService` → ES8.17
`RoutedLegacyEngine` 发出。

| 旧路径 | 当前路径 | 请求/响应 | 当前实现 | 主要差异与验证 |
|---|---|---|---|---|
| `POST /search` | `/search` | `SearchRequest` → `SearchResponse` | 已接入 | 需要独立 HTTP Basic；ES8 BM25/native KNN；`tests/test_search_api.py` |
| `POST /insert` | `/insert`；另有 `/knowledge/insert` | `InsertRequest` → `InsertResponse` | 已接入 | 旧字段和 categoryId/categoryName 转换保留；扩展字段进入 Service 归集；fake 路由测试 |
| `POST /delete` | `/delete`；另有 `/knowledge/delete` | `DeleteRequest` → `DeleteResponse` | 已接入 | `_id` 硬删除、refresh_imm 保留；fake 路由测试 |
| `POST /web_search` | `/web_search` | `WebSearchRequest` → `WebSearchResponse` | 已接入 | 需要独立 HTTP Basic；embedding 字段剔除、indexes 只回 text |
| `POST /get_value_collection` | `/get_value_collection`；兼容别名 `/get_unique_values` | `ValueCollectionRequest` → `ValueCollectionResponse` | 已接入 | terms aggregation；include_doc_count 保留 |
| `POST /list_file_names` | `/list_file_names` | `ListFileNamesRequest` → `ListFileNamesResponse` | 已接入 | document/html/manual 范围和 type_count 由兼容层执行 |
| `POST /preview_delete_by_file` | `/preview_delete_by_file` | `PreviewDeleteByFileRequest` → `PreviewDeleteByFileResponse` | 已接入 | 只读；exact/fuzzy 严格校验；返回样例和告警 |
| `POST /delete_by_file` | `/delete_by_file` | `DeleteByFileRequest` → `DeleteByFileResponse` | 已接入 | 软删、删前 JSONL 快照；目标索引由请求传入 |
| `POST /update_by_condition` | `/update_by_condition` | `UpdateByConditionRequest` → `UpdateByConditionResponse` | 已接入 | AND 条件 → ES8 update_by_query；旧接口 updated_count 固定 0 |
| `POST /modify_knowledge_direct_update` | `/modify_knowledge_direct_update`；新计划接口 `/knowledge/modify_direct_update` | `ModifyKnowledgeRequest` → `ModifyKnowledgeResponse` | 条件接入 | 旧路由依赖 Dify recall/modify；只有注入 modifier 才执行，未配置返回 success=false，防止误报写入 |
| `POST /modify_knowledge` | `/modify_knowledge` | `ModifyKnowledgeRequest` → `ModifyKnowledgeResponse` | 条件接入 | 同上；`old_query_info` 必填；未配置不伪造 LLM 结果 |

## 运行边界

- 导入 `kdb.api.app`、OpenAPI 生成和离线测试不会构造 ES client。
- `/preview_delete_by_file` 只读；`/delete_by_file` 会写快照并软删；`/insert`、`/delete`、`/update_by_condition` 会写 ES8。
- 旧 `/search` 和 `/web_search` 现在受独立 HTTP Basic 保护，凭据只从进程环境读取。
- Dify 依赖不通过 HTTP 参数或仓库配置自动初始化。保留旧能力的部署需要向
  `kdb.api.legacy_routes._modifier` 注入兼容对象，且对象提供旧的两个方法签名。

## 离线验证

```bash
pytest -q tests/test_legacy_http_routes.py tests/test_search_api.py
```

测试只使用 fake service/modifier，不连接 Elasticsearch，不写迁移目标或生产索引。
