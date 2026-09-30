# knowledge_routes.insert_doc

`POST /knowledge/insert` — 单文档 upsert，支持 `synonyms_title`(list)。

## 背景 / 动机

旧检索服务 `:8003/insert`（knowledge_database_builder
`knowledge_database_search_service/src/knowledge_database_search_es.py`）的路由层
把 `synonyms_title` **静默丢弃**：`InsertRequest` 无该字段（extra 进 ext_info 且
`insert_to_service(... ext_info=None)` 又把 ext_info 丢掉），`insert_to_service`
的形参里也没有 synonyms_title（该文件 386-460 行），导致灌库方即使按底层
`process_one_data` 契约传了 `synonyms_title` 列表，存进 ES 的 doc 也没有该字段、
`indexes` 只有 title 一条。本路由直通 `KnowledgeService.insert_data` →
`_prepare_document`，`synonyms_title` 正确落库（单 doc + indexes 每个同义问法一条
带 embedding 的 entry），检索侧（BM25 `synonyms_title` boost 1.8 + nested
`indexes.embedding` 向量）即可按同义问法召回**同一条文档**。

## Inputs（request body, JSON）

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| es_index | str | 是 | 目标库（单库），如 `individual_20` |
| doc | dict | 是 | 完整文档：`_id`(定 id 幂等 upsert)/`title`/`synonyms_title`(List[str])/`content`/`data_type`/`from_type`/`audit_result`/`del_flag`/`tags`/... 非 schema 字段自动归集进 `ext_info`（`kdb.crud.models.SCHEMA_FIELDS`） |
| check_duplicate | bool? | 否 | 缺省 `null`=取服务配置缺省；`false`=跳过查重（固定 `_id` 幂等灌库场景应传 false） |
| is_update_data | bool | 否(false) | 查重命中时软删旧数据后覆盖插入（透传 insert_data） |
| refresh_imm | bool | 否(false) | 写后立即刷新索引（读己之写需要） |

## Outputs

```json
{"success": true, "message": "", "document_id": "payoneer_demo_d1_b2", "es_index": "individual_20"}
```

- 失败：`success=false` + `message`（"数据重复"/"数据处理失败"/`insert failed: <exc>`），HTTP 恒 200（与 modify_direct_update 风格一致）。
- `document_id` 回显 `doc._id`（未传则 null；此时服务端会 gen_data_id，但**不回传**——灌库脚本应自带 `_id`）。

## SQL / 存储

- 无 SQL。写 ES（引擎/索引由 `KDB_FORGE_CONFIG` → `engine_config_path` 决定，
  生产与 :8003 检索服务同一套 aliyun ES serverless）。
- doc 经 `_prepare_document`：synonyms_title→indexes(+embedding)、title/content embedding、
  keywords、时间字段、del_flag=0 缺省等（见 function_schema/service.KnowledgeService.md）。

## 调用方

- `sell_agents/scripts/seed_payoneer_demo_kb.py`（payoneer demo 灌库：单文档+synonyms_title 模式）。
