# modify.apply_modify_plan 函数 Schema

## 函数名称
`apply_modify_plan(knowledge_service, plan, dry_run=False) -> ModifyResult`
（`kdb.modify.service`）

## 功能描述
把一份**已决策好的写入计划** `ModifyPlan` 忠实落到**一个** `es_index`。纯数据写入：
- 按 `document_id` 局部更新 `title/content`（`KnowledgeService.update(..., regenerate_embedding=True, refresh=True)`）。
- 可选插入一条新 QA（仅 `allow_insert=True` 且 `plan.insert` 非空，`insert_text(..., refresh_imm=True)`）。
- `dry_run=True`：不真写，仅返回计划（`applied=False`）。

**零 LLM / 零检索 / 零权限**——抽取/选库/精排/改写/权限/确认全在上游 sell_agent；本层只执行。
单库由调用方保证（`ModifyPlan.es_index` 只有一个）；es_index 为空直接拒绝。

## Inputs
| 参数 | 类型 | 说明 |
|------|------|------|
| knowledge_service | KnowledgeService | 共享 repo+embedding；index 按 `plan.es_index` 传入各 CRUD 调用 |
| plan | ModifyPlan | `{es_index, updates:[UpdateItem], insert:InsertItem?, allow_insert}` |
| dry_run | bool | True 不写，仅回计划 |

`UpdateItem`: `{document_id, new_content, new_title?, old_title?, old_content?}`
`InsertItem`: `{title, content, data_type="qa"}`

## Outputs：ModifyResult.to_dict()
`{success, has_correction, message, es_index, dry_run, updated_items[], inserted_item, errors[]}`
- `updated_items[i].applied` / `inserted_item.applied`：该条是否真写成功。
- `errors`：失败明细（update_failed/insert_failed/异常）。

## HTTP 封装
`POST /knowledge/modify_direct_update`（`kdb.api.knowledge_routes`）请求体 = `{es_index, updates, insert, allow_insert, dry_run}`，响应 = `ModifyResult.to_dict()`。dry_run 分支不构建真 KnowledgeService。

## SQL / ES
写 ES：`update`(by _id, 重算向量) / `insert_text`(新 QA)。索引 = `plan.es_index`。不读写关系库。
