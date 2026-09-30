# knowledge_routes.delete_doc

`POST /knowledge/delete` — 按 `_id` 硬删除一条文档。

## Inputs（request body, JSON）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| es_index | str | 是 | 目标库（单库） |
| document_id | str | 是 | 文档 `_id` |
| refresh | bool | 否(false) | 删除后立即刷新索引（读己之写需要） |

## Outputs

```json
{"success": true, "document_id": "payoneer_demo_d1_c1b", "es_index": "individual_20"}
```

- `success=false`：文档不存在或引擎删除失败；异常兜成 `success=false + message`，HTTP 恒 200。
- 语义 = `KnowledgeService.delete`（`repo.delete` 硬删，非 del_flag 软删）。

## SQL / 存储

无 SQL；写 ES（同 insert_doc，索引由 KDB_FORGE_CONFIG 决定）。

## 调用方

- `sell_agents/scripts/seed_payoneer_demo_kb.py --cleanup`（demo 数据还原）。
