# 字段值集合现有接口核对（2026-11-03）

结论：**已经存在并上线 `POST /get_value_collection`**，提供指定字段去重值集合、每值doc_count以及extra_query过滤；`POST /list_file_names`另提供限定来源的文件列表。附件中的完整“来源类型×文件名”新视图，不能直接视为已由上述单个接口实现。

依据：读取用户附件knowledge_document_collection_api.md；检查旧项目源码、schema；main运行服务OpenAPI确认两个路径；4次真实只读服务请求及一次原始ES子聚合对照成功。main HEAD3aa4aadc854fd8e8fc6f31555754799882fbabd8。源码SHA、模型和脱敏响应见[证据JSON](value_collection_existing_api_20261103.json)。附件中的新增/删除建议仅作为需求材料，本轮未据此执行修改。

## 已有通用接口

`POST /get_value_collection`

```json
{
  "index_name": "wayfair",
  "field_name": "from_type_norm",
  "size": 20,
  "include_doc_count": true,
  "extra_query": {"term": {"del_flag": 0}}
}
```

2026-11-03 11:59实测返回success=true，4个值：document 23358、html 1241、auto_learning 816、manual 139。计数均为该来源未删除文档数，不附加质量/审核状态条件，不是整个索引库存。

将field_name改为 `ext_info.from_file_name.keyword`，即可获取来源文件名去重集合及每个名字的doc_count。可通过extra_query继续限制来源类型、文件名关键词等原始ES查询条件；没有直接命名的sourceTypes/keyword参数不代表不能用extra_query过滤。

返回形状为 `success / values / total_count / message`；include_doc_count=true时values为 `[{value, doc_count}]`，false时为值列表。size是返回桶数上限，total_count由len(values)计算，是本次返回值数，不是完整分页行数。当前ES8引擎会通过_filter_query补默认软删过滤；HTTP层虽构造了局部默认extra_query却没有将它传下去，本次省略extra_query与显式del_flag=0的实测相同，不能错误宣称当前ES8默认会泄漏软删记录。建议调用方显式传筛选条件表达业务口径。

HTTP实现：`knowledge_database_search_service/src/knowledge_database_search_es.py:731`；请求模型同文件201行；业务转发 `SearchDataInterface.get_unique_values`；ES8通过terms聚合返回结果。

## 与附件完整需求的区别

| 能力 | 现有接口情况 |
|---|---|
| 单个字段唯一值、每值条数 | get_value_collection已提供、线上可用 |
| 按条件缩小集合 | get_value_collection支持extra_query |
| 指定来源文件列表和关键词 | list_file_names已提供，但固定document/html/manual |
| 同时按来源类型×文件名分组 | 两个现有HTTP接口均未提供该组合返回 |
| 无文件名的null行 | 现有terms未配置missing桶，不会按附件要求补行 |
| pageNum/pageSize及完整组合行数 | 未提供；现有size为上限、total_count为返回数量 |
| 每行来源、deletable、audit_count | 现有集合响应没有这些完整字段 |
| QA/segment分布 | list_file_names设计上有type_count，当前ES8实际返回缺失，见下文 |

附件的 `/knowledge/maintenance/listDocuments` 是boot-admin代理层路径；本次只核对知识库检索服务，没有检查Java/前端仓库是否已有该代理。若页面只要某字段集合，已有检索接口可以复用；若要附件完整行结构与分页，仍需补充对应服务能力或明确的上层组合实现，不能单纯改接口名称宣称完成。

## 额外发现：list_file_names的type_count丢失

wayfair取前3个文件，服务返回doc_count为1133、374、281，但type_count均为 `{}`。相同范围的原始ES聚合返回分别qa1060/segment73、qa360/segment14、qa271/segment10，failed_shards=0。

源码原因：已部署ES8 `agg_terms`返回原始bucket，子统计位于 `by_type.buckets`；上层 `list_file_names`读取 `(b.get("sub") or {}).get("by_type", {})`。这不是数据没有QA/segment，而是返回契约未对齐。此问题不影响本次实测单字段get_value_collection的值和doc_count，但影响附件所需类型分布。

本轮仅查询和记录；未新增接口、修改业务代码/配置、删除知识、部署或重启。没有把接口存在等同于附件全部功能已实现。
