# 按来源文件名删除知识 —— API 说明

> ⚠️ **本文档已过时**（描述的是带 `confirm_token` 双校验的早期设计）。
> 最新接口说明见 **`docs/知识库检索服务_线上API文档.md`**，那份覆盖线上全部 11 个接口。
> 2026-09-17 起 `/delete_by_file` 入参与 `/preview_delete_by_file` 一致，不再需要 token。


面向前端的「按来源文件批量下架知识」能力，3 个接口：**列名称 → 预览 → 删除**。
文档中所有请求/响应**均为本地实跑 `payoneer_olive` 抓取的真实报文**，非手写示例。

- 服务：`knowledge_database_search_service`（线上 `http://120.77.147.247:8003`）
- 协议：`POST` + `application/json`
- 实现方案与实测依据：`docs/按文件名删除知识服务_方案.md`

---

## 0. 使用流程

```
①  POST /list_file_names          用户从真实存在的文件名里挑（推荐入口，避免手写出错）
     ↓
②  POST /preview_delete_by_file   看清楚会删几条、都是什么 → 拿到 confirm_token
     ↓  （把 by_file / samples 展示给用户确认）
③  POST /delete_by_file           带 confirm_token + expected_count 执行软删
```

**② 是必经步骤**，`confirm_token` 只能从预览拿到。

## 1. 全局规则（三条硬约束）

### 1.1 只处理非对话来源

只作用于 `from_type_norm ∈ {document, html, manual}`，即"来源于文件 / 网页 / 免审录入"的知识。
**对话自动学习来的知识（`auto_learning`）不在范围内**，按文件名删不到（它的"文件名"是群名）。

这是**服务端写死的过滤，不是请求参数**，前端无法绕过。

> 实测 `payoneer_olive`：该范围 8423 条 / 214 个文件名；全库 13151 条 / 1022 个文件名。
> 即 81% 的文件名来自对话，都被挡在外面。

### 1.2 `match_mode` 严格二选一，**没有兜底**

| 值 | 行为 |
|---|---|
| `exact`（默认） | 只做精确匹配。**查不到就是查不到，不会自动转模糊** |
| `fuzzy` | 只做模糊匹配（Dice 相似度 ≥ 0.9 且取最大）。**达不到阈值就是没找到，不会退回精确** |

### 1.3 一律软删

只把 `del_flag` 置 1，**不物理删除**，不提供 `hard_delete`。删除前自动写快照可回滚。

### 1.4 索引由参数指定

`index_name` 三个接口都**必填**，由调用方显式指定查/删哪个索引，没有默认值。

---

## 2. `POST /list_file_names` —— 获取可删除的文件名集合

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `index_name` | string | ✅ | — | 索引名，必填 |
| `keyword` | string | ❌ | null | 文件名关键词筛选（子串、大小写不敏感）；为空则列全部 |
| `size` | int | ❌ | 200 | 最多返回多少个，范围 1~1000 |

### 响应

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 是否成功 |
| `values` | array | 文件名列表，按条数倒序 |
| `values[].value` | string | 文件名（完整，可直接用于后续接口） |
| `values[].doc_count` | int | 该文件下的知识条数 |
| `values[].type_count` | object | 按 `data_type` 拆分，如 `{"qa":320,"segment":36}` |
| `total_count` | int | 本次返回的文件名个数 |
| `message` | string | 提示文案 |

### 实例

```jsonc
// 请求
{"index_name": "payoneer_olive", "keyword": "Newegg", "size": 3}
```
```jsonc
// HTTP 200
{
  "success": true,
  "values": [
    {"value": "Newegg Seller-Portal卖家使用指南（中文版）.pdf",
     "doc_count": 356, "type_count": {"qa": 320, "segment": 36}},
    {"value": "2024-Newegg.pdf",
     "doc_count": 65,  "type_count": {"qa": 55, "segment": 10}},
    {"value": "Newegg-派安盈资料.docx",
     "doc_count": 11,  "type_count": {"qa": 10, "segment": 1}}
  ],
  "total_count": 3,
  "message": "共 3 个来源文件（仅统计 document/html/manual 来源）"
}
```

不传 `keyword` 时按条数倒序列全部：

```jsonc
// 请求
{"index_name": "payoneer_olive", "size": 2}
// HTTP 200
{
  "success": true,
  "values": [
    {"value": "印尼行业资质对照表（对外）", "doc_count": 477,
     "type_count": {"qa": 435, "segment": 42}},
    {"value": "印尼 TikTok Shop-印尼", "doc_count": 429,
     "type_count": {"qa": 429}}
  ],
  "total_count": 2,
  "message": "共 2 个来源文件（仅统计 document/html/manual 来源）"
}
```

---

## 3. `POST /preview_delete_by_file` —— 预览（只读，必经）

### 请求

| 字段 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `index_name` | string | ✅ | — | 索引名，必填 |
| `file_names` | string[] | ✅ | — | 要删除的来源文件名，可多个 |
| `match_mode` | string | ❌ | `"exact"` | `exact` 或 `fuzzy`，其它值 400 |
| `data_types` | string[] | ❌ | null | 限定类型，如 `["qa"]` / `["segment"]`；不传则 **qa+segment 都删** |
| `audit_results` | int[] | ❌ | null | 限定审核状态；不传则**不限**（全删） |
| `sample_size` | int | ❌ | 10 | 返回几条样例供人工确认，0~50 |

### 响应

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 是否成功 |
| `total_count` | int | **预计删除总条数**（去重后所有匹配文件的合计） |
| `by_file` | array | 每个输入文件名的解析结果，见下表 |
| `type_count` | object | 合计的类型分布 `{"qa":n,"segment":m}` |
| `samples` | array | 样例知识（含 `_id`/`title`/`content` 截断 120 字/`data_type`/`audit_result` 等） |
| `warnings` | string[] | **需要前端展示给用户**的提示（未匹配、模糊匹配到别的名字） |
| `confirm_token` | string | 16 位，调删除接口必填 |
| `message` | string | 提示文案 |

`by_file[]` 每项：

| 字段 | 类型 | 说明 |
|---|---|---|
| `input_name` | string | 用户输入的名字 |
| `matched` | bool | 是否匹配到 |
| `matched_name` | string\|null | **实际会删的完整文件名**（fuzzy 时可能与输入不同） |
| `dice` | float | 相似度，exact 命中恒为 1.0 |
| `count` | int | 该文件命中条数 |
| `type_count` | object | 该文件的类型分布 |
| `audit_count` | object | 该文件的审核状态分布，如 `{"2":131,"0":18}` |
| `reason` | string | **仅未匹配时出现**，说明原因 |

### 实例

**exact 命中**：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["Text.docx"], "sample_size": 1}
// HTTP 200
{
  "success": true,
  "total_count": 149,
  "by_file": [{
    "input_name": "Text.docx", "matched": true, "matched_name": "Text.docx",
    "dice": 1.0, "count": 149,
    "type_count": {"qa": 149},
    "audit_count": {"2": 131, "0": 18}
  }],
  "type_count": {"qa": 149},
  "samples": [{
    "data_type": "qa",
    "title": "环球大视野直播的卖家沟通流程是怎样的？",
    "ext_info": {"from_file_name": "Text.docx"},
    "audit_result": 0,
    "from_type_norm": "document",
    "content": "卖家您好，\n请问您想入驻哪个平台？...",
    "_id": "d989e6de1cc9680a8e9e87685ff12b77"
  }],
  "warnings": [],
  "confirm_token": "2707477898f51626",
  "message": "预计软删除 149 条，确认后请带 confirm_token 与 expected_count 调用 /delete_by_file"
}
```

**exact 查不到 —— 不会自动转模糊**：

```jsonc
// 请求（文件名多打了一个 x）
{"index_name": "payoneer_olive", "file_names": ["Text.docxx"], "sample_size": 0}
// HTTP 200
{
  "success": true, "total_count": 0,
  "by_file": [{"input_name": "Text.docxx", "matched": false, "matched_name": null,
               "dice": 0.0, "count": 0, "type_count": {}, "audit_count": {},
               "reason": "精确匹配无结果"}],
  "type_count": {}, "samples": [],
  "warnings": ["「Text.docxx」未匹配到：精确匹配无结果"],
  "confirm_token": "2cba88020b807c50",
  "message": "预计软删除 0 条，..."
}
```

**同样的输入换 fuzzy —— 救回来了**：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["Text.docxx"],
 "match_mode": "fuzzy", "sample_size": 0}
// HTTP 200
{
  "success": true, "total_count": 149,
  "by_file": [{"input_name": "Text.docxx", "matched": true,
               "matched_name": "Text.docx",       // ← 实际会删的是这个
               "dice": 0.9412, "count": 149,
               "type_count": {"qa": 149}, "audit_count": {"2": 131, "0": 18}}],
  "type_count": {"qa": 149}, "samples": [],
  "warnings": ["「Text.docxx」模糊匹配到「Text.docx」(相似度 0.9412，149 条)，请确认"],
  "confirm_token": "2707477898f51626",
  "message": "预计软删除 149 条，..."
}
```

> ⚠️ **前端必须把这条 warning 和 `matched_name` 显示给用户确认**，
> 因为实际删的文件名与用户输入的不是同一个。

**fuzzy 未达阈值**：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["完全不存在xyz"],
 "match_mode": "fuzzy", "sample_size": 0}
// HTTP 200 —— total_count=0
{"by_file": [{"matched": false, "dice": 0.0,
              "reason": "模糊匹配最高相似度 0.0000 未达阈值 0.9"}], ...}
```

**对话来源的文件名 —— 被来源白名单挡住**（即使名字真实存在）：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["群聊总结知识_合并版_20260905"],
 "match_mode": "fuzzy", "sample_size": 0}
// HTTP 200 —— total_count=0，查不到
{"by_file": [{"matched": false, "reason": "模糊匹配最高相似度 0.0000 未达阈值 0.9"}], ...}
```

**只删 segment**：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["入驻会议_260724ver.pdf"],
 "data_types": ["segment"], "sample_size": 0}
// HTTP 200
{"success": true, "total_count": 28,
 "by_file": [{"matched_name": "入驻会议_260724ver.pdf", "count": 28,
              "type_count": {"segment": 28}, "audit_count": {"2": 28}}],
 "type_count": {"segment": 28},
 "confirm_token": "1b05bf86f10328e6", ...}
```
（该文件共 267 条 = qa 239 + segment 28，限定后只命中 28 条）

**参数非法 → HTTP 400**：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["a"], "match_mode": "smart"}
// HTTP 400
{"detail": "match_mode 只能是 exact 或 fuzzy"}
```

---

## 4. `POST /delete_by_file` —— 执行删除（软删）

### 请求

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `index_name` | string | ✅ | 必须与预览时一致 |
| `file_names` | string[] | ✅ | 必须与预览时一致 |
| `match_mode` | string | ❌ | 默认 `exact`；**必须与预览时一致**，否则 token 对不上 |
| `data_types` | string[] | ❌ | **必须与预览时一致** |
| `audit_results` | int[] | ❌ | **必须与预览时一致** |
| `confirm_token` | string | ✅ | 来自预览响应 |
| `expected_count` | int | ✅ | 来自预览响应的 `total_count` |

### 响应

| 字段 | 类型 | 说明 |
|---|---|---|
| `success` | bool | 是否真的执行了删除 |
| `deleted_count` | int | 实际软删条数 |
| `snapshot_path` | string\|null | 快照文件路径（jsonl，不含向量），可用于回滚 |
| `message` | string | 结果说明 |

### 双重校验

两道都必须过，任一失败都 **不做任何写操作**：

**token 不匹配**（条件被改过）：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["Text.docx"],
 "confirm_token": "0000000000000000", "expected_count": 149}
// HTTP 200
{"success": false, "deleted_count": 0, "snapshot_path": null,
 "message": "confirm_token 不匹配（条件或数据已变化），请重新预览后再删除"}
```

**条数漂移**（预览之后库里数据变了）：

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["Text.docx"],
 "confirm_token": "2707477898f51626", "expected_count": 999999}
// HTTP 200
{"success": false, "deleted_count": 0, "snapshot_path": null,
 "message": "实际命中 149 条，与 expected_count 999999 不一致，请重新预览"}
```

### 成功示例（端到端实测，用一次性测试数据）

```jsonc
// 请求
{"index_name": "payoneer_olive", "file_names": ["__e2e_测试文件__.pdf"],
 "confirm_token": "83357053ae983401", "expected_count": 5}
// HTTP 200
{"success": true, "deleted_count": 5,
 "snapshot_path": "data/deleted_snapshots/payoneer_olive_20260916_181703.jsonl",
 "message": "已软删除 5 条"}
```

删除后：5 条的 `del_flag` 全部变为 1，再次预览 `total_count=0`，
快照 5 行、不含向量字段。

并发写入导致版本冲突时，message 会附加说明：
`"已软删除 N 条（版本冲突 M 条已跳过）"`。

---

## 5. 错误码

| 场景 | HTTP | 返回 |
|---|---|---|
| `file_names` 为空 | 400 | `{"detail": "file_names 不能为空"}` |
| `match_mode` 非法 | 400 | `{"detail": "match_mode 只能是 exact 或 fuzzy"}` |
| `confirm_token` 为空 | 400 | `{"detail": "confirm_token 不能为空，请先调用 /preview_delete_by_file"}` |
| `size` / `sample_size` 越界 | 422 | pydantic 校验错误 |
| 服务内部异常 | 200 | `{"success": false, "message": "...失败: ..."}` |

> 注意：业务层失败（token 不符、条数不符、文件名没匹配上）返回 **HTTP 200 + `success:false`**，
> 只有参数校验问题才是 4xx。前端应以 `success` 字段判断成败。

---

## 6. 前端接入建议

1. **入口用 `/list_file_names`**，让用户从真实存在的名字里勾选，而不是手输 —— 这样永远走 `exact`，最稳。
2. **`fuzzy` 只用于"名字记不全"的补救**。用了就必须把 `matched_name`、`dice`、`count`
   和 `warnings` 显示出来让用户确认，因为实际删的可能不是他输入的那个名字。
3. **预览结果要展示 `by_file` 而不只是 `total_count`**，多文件时用户需要逐个看清楚。
4. **`confirm_token` 不要缓存**：删除前重新预览一次拿最新 token，否则条数一变就会被拒。
5. 删除成功后建议把 `snapshot_path` 记录下来，万一删错可据此回滚。

---

## 7. 已知边界

| 情况 | 行为 |
|---|---|
| 文件名超过 256 字符 | 拒绝并说明（keyword 的 `ignore_above` 限制，不做匹配免得"以为删了其实没删"） |
| 没有 `from_file_name` 的旧数据（实测 262 条） | 本功能够不着，需要其它方式清理 |
| 对话来源知识 | 不在范围内，查不到也删不掉 |
| 一次删除的条数 | 无上限，服务端走 `update_by_query` 批处理并限流；实测单文件最多 1337 条 |
