# _mapping_config_equal

## 所属文件
`knowledge_interface_tools/es_search_interface.py`（模块级函数，两个实现类共用）

## 功能描述
判断一段「代码期望的 mapping 配置」与「ES 返回的实际配置」是否等价，
忽略 ES 会静默丢弃的参数和可省略的默认值。供 `update_index_map` 使用。

## Inputs
- `expected` (Any) — 代码里定义的配置片段
- `existing` (Any) — `indices.get_mapping` 返回的对应片段；字段不存在时传 `None`

## Outputs
`bool` — 等价为 `True`

## 规则
1. 两边都是 `dict` → 只遍历 `expected` 的键（**子集语义**：线上多出来的键不算差异），逐键递归
2. 键在 `_MAPPING_IGNORED_KEYS`（`{"index", "similarity"}`）中 → 跳过
3. 键是 `type` 且值为 `"object"` 且 `existing` 里没有 `type` → 跳过（ES 对 object 不回显 type）
4. 其余 → `expected == existing`

## 为什么忽略 `index` / `similarity`
线上 ES 版本 `7.10.0`（`GET /` 实测）。`dense_vector` 的 `index` 与 `similarity`
参数是 7.16+/8.x 才引入的，7.10 直接忽略。原代码已经有 `if key == "index": continue`
（说明以前踩过一次同样的坑打了半个补丁），但漏了 `similarity`。

**升级到 ES 8 / OpenSearch 时要重新审视这个忽略表** —— 那时这两个参数是生效的，
忽略它们会掩盖真实的 knn 配置差异。

## SQL
无。
