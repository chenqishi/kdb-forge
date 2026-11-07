# search_index_data_interface — 按来源文件名删除知识

`SearchDataInterface` 上的一组方法，支撑 `/list_file_names`、`/preview_delete_by_file`、
`/delete_by_file` 三个端点。设计与实测依据见 `docs/按文件名删除知识服务_方案.md`。

## 三条硬约束

1. **预览、文件名解析和删除只作用于非对话来源**：`from_type_norm in ["document","html","manual"]`，
   写死在 `FROM_TYPE_SCOPE`，**不做成请求参数**（前端漏传就会删到对话知识）。
   2026-11-03 用户要求列表单独支持可选 `from_type_norm`，空值不限制来源；
   此例外只适用于只读 `list_file_names`，不改变以上删除边界。
2. **`match_mode` 严格二选一**：`exact` 查不到不转模糊，`fuzzy` 不达阈值不退回精确。
3. **一律软删** `del_flag=1`，删前写快照。是否先预览再确认由前端流程决定，服务端不强制。

## 类常量

| 常量 | 值 | 说明 |
|---|---|---|
| `FROM_TYPE_SCOPE` | `["document","html","manual"]` | 来源白名单。**必须是白名单**：存量 `auto_learning` 有中文旧写法「自动学习」（实测 payoneer_olive 334 条），黑名单会漏网 |
| `FILE_NAME_FIELD` | `ext_info.from_file_name` | text 字段，用于 match |
| `FILE_NAME_KEYWORD` | `ext_info.from_file_name.keyword` | keyword 字段，用于 term / wildcard / 聚合 |
| `KEYWORD_IGNORE_ABOVE` | 256 | 超过则未被索引为 keyword，term 查不到且不报错 |
| `MAX_WILDCARD_FRAGMENT` | 48 | `index.max_wildcard_length=50`，留 2 个字符给前后的 `*` |
| `DICE_THRESHOLD` | 0.9 | 模糊匹配采纳阈值 |

## Inputs / Outputs

### `dice_similarity(a, b) -> float`
字符二元组 Dice 系数。两串相同为 1.0。

### `list_file_names(index_name, keyword=None, size=200, from_type_norm=None) -> List[Dict]`
返回 `[{value, doc_count, type_count}]`，`type_count` 是 `{qa: n, segment: m}`。
`keyword` 走 `wildcard`（片段截断到 48 字符，大小写不敏感）。
始终筛选 `del_flag=0`；来源参数省略/null/空串/仅空白时不限制来源，
非空字符串去首尾空白后精确筛选。详见 `search_index_data_interface.list_file_names.md`。

### `resolve_file_name(index_name, name, match_mode="exact") -> Dict`
把用户输入解析成库里真实存在的文件名。
返回 `{matched: bool, matched_name: str|None, doc_count: int, dice: float, reason: str|None}`。

- `exact`：只做 `term` on `.keyword`。**不发起任何模糊召回**（用例锁死）。
- `fuzzy`：四路召回并集 → 逐个算 Dice → 取最大 → `>= 0.9` 才采纳。
  **不回退到精确计数**（用例锁死）。
- `len(name) > 256` 直接拒绝并说明原因，不进入查询。

### `preview_delete_by_file(index_name, file_names, match_mode, data_types, audit_results, sample_size) -> Dict`
返回 `{total_count, by_file[], type_count, samples[], warnings[], resolved_names[]}`。
`by_file` 每项含 `input_name / matched / matched_name / dice / count / type_count / audit_count`。
模糊匹配到别的名字时，`warnings` 里会给出「A 模糊匹配到 B（相似度 x，n 条），请确认」。

### `delete_by_file(index_name, file_names, match_mode, data_types, audit_results, snapshot_dir) -> Dict`
入参与 `preview_delete_by_file` 一致（除 `sample_size`），区别只是这个真删。
返回 `{success, deleted_count, snapshot_path, message}`。
一个文件名都没匹配上时不执行删除（避免空条件误删全库）。

## `ext_info.supersedes_file_name`：文档重跑换名后的连带删除

文档重跑后，新知识用**新文件名**入库，但它取代的是另一个名字的旧文档：

```
库里旧名: 基础运营_管理我的团队页面.docx          （带分类前缀）
新包同篇: 管理"我的团队 (My Team)"页面.docx      （不带前缀）
```

实测 wayfair：391 个待更新文件里 160 个属于这种情况，纯文件名对不上
（Dice ≥0.9 的是 0 个，是整体改名不是细微差异）。

若不处理，前端按旧文件名删除时只删掉旧知识，**新知识仍留在库里**，等于没更新干净；
反过来按新文件名删也删不掉旧的。

### 约定

重跑入库时，把**前身文件名**写进新知识的 `ext_info`：

```json
"ext_info": {
  "from_file_name": "管理\"我的团队 (My Team)\"页面.docx",
  "supersedes_file_name": "基础运营_管理我的团队页面.docx"
}
```

`_build_file_query` 的文件名条件是 **`from_file_name` OR `supersedes_file_name`**
（`should` + `minimum_should_match=1`），所以传任一名字都能把新旧知识一起匹配到。

### 注意

- 该字段是**可选**的，老数据没有不影响任何行为（实测 payoneer_olive/wayfair 现有数据
  的匹配结果与加此字段前完全一致）
- 必须是 OR 不能是 AND —— AND 要求两个字段都命中，几乎永远查不到
- `list_file_names` 的聚合仍只按 `from_file_name`，列出的是"当前文件名"，符合前端展示预期

## SQL / 存储

不涉及 SQL。读写 ES 索引（由调用方通过 `index_name` 参数指定，如 `payoneer_olive`）。

**读**：`_count`、`terms` 聚合、小 size 的 `search`（取样例/快照分页）。
**写**：只有 `update_by_query` 把 `del_flag` 置 1，不删文档、不改其它字段。

用到的字段：

| 字段 | 类型 | 用途 |
|---|---|---|
| `del_flag` | long | 过滤未删除；软删时写 1 |
| `from_type_norm` | **顶层 keyword** | 来源白名单过滤 |
| `ext_info.from_file_name` | text + `.keyword`(ignore_above 256) | 文件名匹配与聚合 |
| `data_type` | keyword | qa / segment 过滤与分布统计 |
| `audit_result` | long | 可选过滤与分布统计 |

## 为什么用 `_count`/聚合 + `update_by_query`

本集群（Aliyun serverless ES）在大结果集下会**取消分片却仍返回 200**，
`hits` 不全而 `hits.total` 照报全量。因此：

- 计数一律用 `_count` / `terms` 聚合 —— 不受 size 截断影响
- 删除用 `update_by_query` 服务端批处理 —— 不把成千上万条 hits 拉回本地
  （「先查 ID 再逐条删」正是会被静默截断的用法）
- 快照分页取，每页 500，且走 `_search_with_shard_check`（分片失败会抛错而非静默返回空）

## 模糊召回为什么要四路

实测：文件名字段的分词把 `text.docx` 切成**一个 token**，且 `wildcard *name*`
要求输入是真实名字的**子串**。所以用户多打一个字符（`Text.docxx`）时，
wildcard 和 match 两路**都召不回** —— 而这恰恰是最典型的输错场景。

因此 `should` 有四路（都只负责捞候选，判定一律交给 Dice）：

1. `wildcard *{name[:48]}*` —— 输入是真实名子串时命中
2. `match`(标准) —— 分词能对上时命中
3. `match` + `fuzziness: AUTO` —— 救「多打/打错几个字符」
4. `wildcard *{name[:60%]}*` —— 救「尾巴写错/写多」（如少写扩展名）

实测修复后：`Text.docxx`→`Text.docx`(0.941)、`Text.doc`→(0.933)、
`入驻会议_260724ver.pd`→`...pdf`(0.970)、`Newegg...（中文版）`→`...（中文版）.pdf`(0.938) 全部救回。

## 相关测试

`tests/test_delete_by_file.py`（21 个用例），重点：
- `test_scope_uses_whitelist_not_blacklist` —— 必须白名单，中文旧写法不能漏
- `test_exact_never_falls_back_to_fuzzy` / `test_fuzzy_never_falls_back_to_exact` —— 无兜底
- `test_wildcard_fragment_respects_max_wildcard_length` —— 不触发 400
- `test_overlong_filename_rejected_not_silently_zero` —— 超长名不能静默返 0
- `test_delete_takes_same_params_as_preview` —— 与 preview 入参一致，无 token
- `test_delete_aborts_when_nothing_matched` —— 没匹配上不执行
- `test_delete_soft_deletes_and_snapshots` —— 只软删且必须先写快照
