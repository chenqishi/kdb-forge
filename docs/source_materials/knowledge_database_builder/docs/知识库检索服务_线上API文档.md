# 知识库检索服务 —— 线上 API 文档

> 服务地址：`http://120.77.147.247:8003`
> 实现：`knowledge_database_search_service/src/knowledge_database_search_es.py`（FastAPI，单进程 4 worker）
> 本文档所有报文均为 **2026-09-17 对线上实跑抓取**，非手写示例。

所有接口均为 `POST` + `application/json`。

## 接口总览

| 接口 | 用途 | 类型 |
|---|---|---|
| [`/search`](#1-search) | 语义检索知识（线上问答主路） | 读 |
| [`/web_search`](#2-web_search) | 按条件捞原始数据，支持分页 | 读 |
| [`/get_value_collection`](#3-get_value_collection) | 取某字段的唯一值集合 | 读 |
| [`/list_file_names`](#4-list_file_names) | 列出可按文件名删除的来源文件 | 读 |
| [`/preview_delete_by_file`](#5-preview_delete_by_file) | 预览按文件名删除会命中什么 | 读 |
| [`/delete_by_file`](#6-delete_by_file) | 按文件名批量软删除 | 写 |
| [`/insert`](#7-insert) | 插入/更新单条知识 | 写 |
| [`/delete`](#8-delete) | 按 id 删除单条 | 写 |
| [`/update_by_condition`](#9-update_by_condition) | 按条件批量更新字段 | 写 |
| [`/modify_knowledge`](#10-modify_knowledge) | 改写知识（带检索定位） | 写 |
| [`/modify_knowledge_direct_update`](#10-modify_knowledge) | 改写知识（直接更新） | 写 |

---

## 1. `/search`

语义检索，线上问答走这条路。返回按相似度排序的知识。

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | ✅ | — | 查询文本，为空返回 400 |
| `top_k` | int | ❌ | **1000** | 返回条数上限 |
| `score_threshold` | float | ❌ | -1 | 分数阈值，-1 表示不过滤 |
| `index_names` | string | ❌ | null | 索引名，多个用逗号分隔 |
| `condition_dicts` | array | ❌ | null | 属性过滤，组间 OR，组内 AND |
| `search_type` | string | ❌ | `"qa"` | `qa` / `segment` |
| `data_type` | string | ❌ | `"text"` | 含 `image` 时参与图片相似度 |
| `use_synonyms` | bool | ❌ | **false** | 是否启用同义问法扩展 |

> ⚠️ **`top_k` 默认 1000**。结果集越大越可能触发 ES 分片取消（见 [附录 A](#附录-a-es-分片静默取消)），
> 建议显式传 40~100。

### 响应

```jsonc
{"results": [{
  "id": "9cd0d235397ede6dab8dc56e03edfca3",
  "dataset": "payoneer_olive",
  "insert_time": "2026-09-06 18:35:26",
  "update_time": "2026-09-06 18:35:26",
  "q": "Bol跨境店的开店要求有哪些？",     // 标题
  "a": "Bol跨境店开店要求：1. 使用Bol官方仓...",  // 正文
  "ext_info": {...},
  "score": 1.12                            // similarity，非 ES 原始分
}]}
```

### 实例

```jsonc
// 请求
{"text": "Bol入驻要求", "index_names": "payoneer_olive", "top_k": 2,
 "condition_dicts": [{"del_flag": 0, "audit_result": [1, 2]}],
 "use_synonyms": true}
// HTTP 200，返回 2 条
```

---

## 2. `/web_search`

按条件捞原始数据，支持分页。返回的是**完整文档字段**（已剔除所有向量字段）。

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `text` | string | ❌ | `""` | 为空则纯按条件过滤 |
| `page_size` | int | ❌ | **10000** | 每页条数 |
| `page_num` | int | ❌ | 1 | 页码，从 1 开始 |
| `index_names` | string | ❌ | null | 索引名 |
| `client` | string | ❌ | null | 客户标识 |
| `need_from_history` | bool | ❌ | false | 是否保留 `ext_info.from_chat_history` |
| `condition_dicts` | array | ❌ | `[]` | 属性过滤 |
| `score_threshold` | float | ❌ | 5.3 | 分数阈值 |

> ⚠️ **`page_size` 默认 10000**，是最容易触发分片取消的用法。建议显式传 100~500 分页取。

### 响应

```jsonc
{"results": [{"_id": "...", "score": 1.0, "title": "...", "content": "...",
              "data_type": "qa", "del_flag": 0, "audit_result": 2,
              "synonyms_title": [], "keywords": [...],
              "category_infos": [{"category_name": "默认分组", "category_id": "1"}],
              "ext_info": {"from_file_name": "...", "from_page": [10]},
              "indexes": ["标题", "同义问法1"]}],   // 只有 text，无向量
 "total_count": 149, "current_count": 2}
```

### 实例

```jsonc
// 按来源文件捞
{"text": "", "index_names": "payoneer_olive",
 "condition_dicts": [{"from_file_name": "Text.docx"}],
 "page_num": 1, "page_size": 2}
```

`condition_dicts` 支持的特殊字段映射：
- `from_file_name` → `ext_info.from_file_name.keyword`
- `category_names` → 自动转 `category_ids`
- `category_path` / `cate1_name` 等 → 自动加 `primary_category.` 前缀

---

## 3. `/get_value_collection`

取某个字段的全部唯一值（terms 聚合）。

### 请求

| 字段 | 类型 | 必填 | 默认 |
|---|---|---|---|
| `index_name` | string | ✅ | — |
| `field_name` | string | ✅ | — |
| `size` | int | ❌ | 10000 |
| `include_doc_count` | bool | ❌ | false |
| `extra_query` | object | ❌ | `{"term":{"del_flag":0}}` |

### 实例

```jsonc
// 请求
{"index_name": "payoneer_olive", "field_name": "from_type_norm",
 "size": 10, "include_doc_count": true}
// HTTP 200
{"success": true,
 "values": [{"value": "document", "doc_count": 8080}, ...],
 "total_count": 7,
 "message": "成功获取字段 from_type_norm 的值集合，共 7 个值"}
```

---

# 按来源文件名删除知识（4~6）

前端「这份文档不要了」的批量下架能力。流程：**列名称 → 预览 → 删除**。

## 三条硬约束

**① 只处理非对话来源**：仅 `from_type_norm ∈ {document, html, manual}`。
对话自动学习的知识（`auto_learning`）按文件名删不到（它的"文件名"是群名）。
服务端写死，前端无法绕过。

**② `match_mode` 严格二选一，无兜底**：

| 值 | 行为 |
|---|---|
| `exact`（默认） | 只精确匹配。**查不到就是查不到，不会转模糊** |
| `fuzzy` | 只模糊匹配（Dice ≥ 0.9 取最大）。**达不到阈值就是没找到，不会退回精确** |

**③ 一律软删**：只把 `del_flag` 置 1，不物理删除，无 `hard_delete`。删前自动写快照。

---

## 4. `/list_file_names`

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `index_name` | string | ✅ | — | 索引名，无默认值 |
| `keyword` | string | ❌ | null | 文件名关键词（子串，大小写不敏感） |
| `size` | int | ❌ | 200 | 1~1000 |

### 实例

```jsonc
// 请求
{"index_name": "payoneer_olive", "keyword": "Newegg", "size": 3}
// HTTP 200
{"success": true,
 "values": [
   {"value": "Newegg Seller-Portal卖家使用指南（中文版）.pdf",
    "doc_count": 356, "type_count": {"qa": 320, "segment": 36}},
   {"value": "2024-Newegg.pdf", "doc_count": 65, "type_count": {"qa": 55, "segment": 10}},
   {"value": "Newegg-派安盈资料.docx", "doc_count": 11, "type_count": {"qa": 10, "segment": 1}}
 ],
 "total_count": 3,
 "message": "共 3 个来源文件（仅统计 document/html/manual 来源）"}
```

---

## 5. `/preview_delete_by_file`

只读，看清楚会删什么。**入参与 `/delete_by_file` 一致**（多一个 `sample_size`）。

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `index_name` | string | ✅ | — | 索引名 |
| `file_names` | string[] | ✅ | — | 来源文件名，可多个 |
| `match_mode` | string | ❌ | `"exact"` | `exact` / `fuzzy`，其它值 400 |
| `data_types` | string[] | ❌ | null | 不传则 **qa + segment 都删** |
| `audit_results` | int[] | ❌ | null | 不传则**不限**（全删） |
| `sample_size` | int | ❌ | 10 | 样例条数，0~50 |

### 响应字段

| 字段 | 说明 |
|---|---|
| `total_count` | 预计删除总条数 |
| `by_file[]` | 每个输入名的解析结果 |
| `by_file[].matched_name` | **实际会删的完整文件名**（fuzzy 时可能≠输入） |
| `by_file[].dice` | 相似度，exact 命中恒为 1.0 |
| `by_file[].type_count` / `audit_count` | 该文件的类型/审核状态分布 |
| `by_file[].reason` | **仅未匹配时出现** |
| `type_count` | 合计类型分布 |
| `samples[]` | 样例知识（`content` 截断 120 字） |
| `warnings[]` | **必须展示给用户** |

### 实例

**exact 命中**：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["Text.docx"], "sample_size": 1}
// HTTP 200
{"success": true, "total_count": 149,
 "by_file": [{"input_name": "Text.docx", "matched": true, "matched_name": "Text.docx",
              "dice": 1.0, "count": 149, "type_count": {"qa": 149},
              "audit_count": {"2": 131, "0": 18}}],
 "type_count": {"qa": 149},
 "warnings": [],
 "message": "预计软删除 149 条，确认后用相同参数调用 /delete_by_file"}
```

**exact 打错字 —— 不兜底**：

```jsonc
// 请求（多打一个 x）
{"index_name": "payoneer_olive", "file_names": ["Text.docxx"], "sample_size": 0}
// HTTP 200
{"total_count": 0,
 "by_file": [{"matched": false, "matched_name": null, "dice": 0.0,
              "reason": "精确匹配无结果"}],
 "warnings": ["「Text.docxx」未匹配到：精确匹配无结果"]}
```

**同样输入换 fuzzy —— 救回**：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["Text.docxx"],
 "match_mode": "fuzzy", "sample_size": 0}
// HTTP 200
{"total_count": 149,
 "by_file": [{"input_name": "Text.docxx",
              "matched_name": "Text.docx",     // ← 实际删的是这个
              "dice": 0.9412, "count": 149,
              "type_count": {"qa": 149}, "audit_count": {"2": 131, "0": 18}}],
 "warnings": ["「Text.docxx」模糊匹配到「Text.docx」(相似度 0.9412，149 条)，请确认"]}
```

> ⚠️ 前端**必须把 `matched_name` 和 warning 展示给用户确认** —— 实际删的不是他输入的名字。

**fuzzy 未达阈值 / 对话来源被挡住**（两者都返回 `total_count: 0`）：

```jsonc
{"index_name": "payoneer_olive", "file_names": ["群聊总结知识_合并版_20260905"],
 "match_mode": "fuzzy", "sample_size": 0}
// → total_count: 0，该文件真实存在但属对话来源，按设计查不到
```

**只删 segment**：

```jsonc
// 请求（该文件共 267 条 = qa 239 + segment 28）
{"index_name": "payoneer_olive", "file_names": ["入驻会议_260724ver.pdf"],
 "data_types": ["segment"], "sample_size": 0}
// HTTP 200 → {"total_count": 28, "type_count": {"segment": 28}}
```

---

## 6. `/delete_by_file`

**入参与 `/preview_delete_by_file` 完全一致**（除 `sample_size`），区别只是这个真删、那个不删。
是否要让用户先看预览再确认，**由前端流程控制**，服务端不强制。

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `index_name` | string | ✅ | — | 索引名 |
| `file_names` | string[] | ✅ | — | 来源文件名，可多个 |
| `match_mode` | string | ❌ | `"exact"` | `exact` / `fuzzy`，其它值 400 |
| `data_types` | string[] | ❌ | null | 不传则 qa + segment 都删 |
| `audit_results` | int[] | ❌ | null | 不传则不限 |

### 响应

| 字段 | 说明 |
|---|---|
| `success` | 是否执行了删除 |
| `deleted_count` | 实际软删条数 |
| `snapshot_path` | 快照路径（jsonl，不含向量），可回滚 |
| `message` | 结果说明 |

### 实例（线上实测，一次性测试数据）

```jsonc
// 请求 —— 与 preview 同样的 body
{"index_name": "payoneer_olive", "file_names": ["__api_e2e_测试_勿用__.pdf"]}
// HTTP 200
{"success": true, "deleted_count": 4,
 "snapshot_path": "data/deleted_snapshots/payoneer_olive_20260917_105636.jsonl",
 "message": "已软删除 4 条"}
```

删后 4 条 `del_flag` 全为 1，再次预览 `total_count: 0`。

**一个文件名都没匹配上时不执行删除**（避免空条件误删）：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["完全不存在zzz"]}
// HTTP 200
{"success": false, "deleted_count": 0, "snapshot_path": null,
 "message": "没有匹配到任何文件名，未执行删除；「完全不存在zzz」未匹配到：精确匹配无结果"}
```

并发冲突时 message 附加：`"已软删除 N 条（版本冲突 M 条已跳过）"`。

---

## 7. `/insert`

插入或更新单条知识。字段较多，常用的：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `index_names` | string | ✅ | 索引名 |
| `_id` / `id` | string | ❌ | 不传则自动生成 |
| `title` / `content` | string | ❌ | 标题 / 正文 |
| `data_type` | string | ❌ | `qa` / `segment` |
| `from_type` / `from_type_norm` | string | ❌ | 来源类型 |
| `audit_result` | int | ❌ | -1未审 / 0不通过 / 1通过 / 2 |
| `del_flag` | int | ❌ | 0正常 / 1已删 |
| `tags` | string[] | ❌ | 标签 |
| `categoryId` / `categoryName` / `category_infos` | — | ❌ | 类目 |
| `ext_info` | object | ❌ | 扩展信息，如 `from_file_name` |
| `refresh_imm` | bool | ❌ | 是否立即刷新可见，默认 false |
| `is_update_data` | bool | ❌ | 默认 true |

**模型允许额外字段**（`extra="allow"`），未定义的字段会被收进 `ext_info`。

响应：`{"success": true, "message": ""}`

---

## 8. `/delete`

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `id` | string | ✅ | 数据 ID |
| `index_names` | string | ✅ | 索引名 |
| `refresh_imm` | bool | ❌ | 是否立即生效 |

> 这是**物理删除单条**。批量下架请用 `/delete_by_file`（软删可回滚）。

---

## 9. `/update_by_condition`

按条件批量更新字段。知识软删/恢复常用它。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `index_name` | string | ✅ | 索引名 |
| `update_fields` | object | ✅ | `{字段: 新值}` |
| `conditions` | array | ✅ | `[{字段: 值}]` |

```jsonc
// 软删单条
{"index_name": "payoneer_olive",
 "update_fields": {"del_flag": 1},
 "conditions": [{"_id": "39adb07e73dc981417154d1a8bec5aab"}]}
// 响应
{"success": true, "updated_count": 1, "message": "..."}
```

---

## 10. `/modify_knowledge` 与 `/modify_knowledge_direct_update`

改写已有知识。

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `es_index` | string | ✅ | 索引名 |
| `new_query_info` | object | ✅ | 新的 `{title, content}` |
| `old_query_info` | object | ⚠️ | `modify_knowledge` **必填**；`_direct_update` 可选 |
| `search_querys` | string[] | ❌ | 用于检索定位待改知识 |
| `write_db_id` | string | ❌ | 仅 `modify_knowledge` 使用 |
| `allow_insert` | bool | ❌ | 没找到旧 QA 时是否插入新的，默认 false |

---

## 附录 A：ES 分片静默取消

阿里云 serverless ES 在**大结果集**请求下会取消部分分片的查询任务，
但整体仍返回 HTTP 200，线索只在响应体的 `_shards.failed`：

```jsonc
"_shards": {"total": 3, "successful": 2, "failed": 1,
            "failures": [{"shard": 0, "reason": {"type": "task_cancelled_exception"}}]}
```

此时 `hits` 不全而 `hits.total` 照报全量。**危害是"查不到"会被误判成"库里没有"**。

实测边界（集群静置、请求间隔 5s）：

| size | 成功率 |
|---|---|
| 100 | 4/4 |
| 500 | 3/4 |
| 2000 | 4/4 |
| 5000 | **0/4** |
| 10000 | **0/4** |

`/search` 的 `top_k` 实测：40 与 100 各 12 次**零缺失**；1000 时 12 次有 2 次目标缺失。

**服务端已做处理**（2026-09-16 上线）：检测 `_shards.failed` → 退避重试 3 次 →
仍失败则抛错而非静默返回空；大 size 自动拆成 500 一批。

**调用方建议**：
- `/search` 显式传 `top_k`（40~100），不要用默认 1000
- `/web_search` 显式传 `page_size`（100~500）分页取，不要用默认 10000

---

## 附录 B：错误码

| 场景 | HTTP | 返回 |
|---|---|---|
| 必填字段缺失 | 422 | `{"detail":[{"type":"missing","loc":["body","index_name"],...}]}` |
| `text` 为空（/search） | 400 | `{"detail": "文本参数不能为空"}` |
| `file_names` 为空 | 400 | `{"detail": "file_names 不能为空"}` |
| `match_mode` 非法 | 400 | `{"detail": "match_mode 只能是 exact 或 fuzzy"}` |
| `size`/`sample_size` 越界 | 422 | pydantic 校验错误 |
| 索引不存在 | 200 | `{"success": false, "message": "...index_not_found_exception..."}` |
| 业务失败（没匹配到文件名等） | 200 | `{"success": false, "message": "..."}` |

> ⚠️ **业务层失败返回 HTTP 200 + `success: false`**，只有参数校验问题才是 4xx。
> 前端应以 `success` 字段判断成败，不能只看状态码。
> （`/search` 和 `/web_search` 无 `success` 字段，以 `results` 是否为空判断。）

---

## 附录 C：线上验证记录（2026-09-17）

新增的三个接口在线上逐项验证：

| 用例 | 结果 |
|---|---|
| `list_file_names` 关键词筛选 | ✅ 200 |
| 不存在的索引 | ✅ 200 + `success:false` + ES 错误信息 |
| 缺 `index_name` | ✅ 422 |
| exact 命中 | ✅ total=149 |
| exact 打错字 | ✅ total=0，不兜底 |
| fuzzy 救回 | ✅ dice=0.9412，带确认 warning |
| fuzzy 不相干 | ✅ total=0 |
| 对话来源被挡 | ✅ total=0 |
| 只删 segment | ✅ total=28 |
| `match_mode` 非法 | ✅ 400 |
| 删除未匹配的文件名 | ✅ 拒绝，无写操作 |
| **真实删除** | ✅ 4 条（2 qa + 2 segment）全部 `del_flag=1`，快照落盘 |
| 原有 `/search` | ✅ 200，返回 40 条 |
| 原有 `/web_search` | ✅ 200，total=2567 |

验证全程使用一次性测试数据（`__prod_e2e_*`），测后已物理清除，残留 0；
`Text.docx`(149)、`入驻会议_260724ver.pdf`(267) 等真实知识条数未变。
