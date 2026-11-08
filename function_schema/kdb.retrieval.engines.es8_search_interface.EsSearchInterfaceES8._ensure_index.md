# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8._ensure_index

## Signature

`_ensure_index(self, index_name: str, binding: Optional[SimpleNamespace]=None) -> None`

## Description

确保索引存在：不存在则按代码里的 mapping 定义创建，已存在则尝试把代码新增的字段补进去。
**同一进程内每个索引只执行一次**，结果记在 `self.has_build_index`。

## Inputs

- `index_name` (str) — 单个索引名。函数内部统一 `lower()`，ES 只接受小写索引名。
  **不接受逗号分隔的多索引串**，调用方（`_get_index_name`）负责拆开后逐个传入。

## Outputs

无返回值。副作用：
- 索引不存在 → `indices.create`
- 索引已存在 → `update_index_map`（失败只 warning，不抛）
- 成功走完 → `self.has_build_index[index_name.lower()] = True`
- 抛异常（如创建失败）→ **不置位**，保留下次重试的机会

无；新索引使用 `indices.create(mappings=..., settings=...)` 创建 native HNSW mapping；已存在的旧未索引向量索引抛迁移错误。

## `has_build_index` 的语义

**「本进程已检查过该索引」，不是「mapping 已完全同步成功」。**

改之前的语义是后者，而 `update_index_map` 对线上每一个索引都返回 `False`，
于是缓存永远不置位 —— `_get_index_name` 在**每次检索**时都会重跑一遍：
每索引 3 次 ES 往返（`exists` ×2 + `get_mapping` ×1），双索引检索就是 6 次白跑，

mapping 不兼容是**永久性**的（ES 不允许改已存在字段），重试一万次结果一样，
所以「检查过就记住」是正确语义。代价是：进程存活期间不会感知到索引 mapping 的外部变更，
需要重启服务才会重新检查 —— 这与「mapping 本来就只在部署时才变」的现实一致。

## 调用路径

`_get_index_name` → `_ensure_index`，而 `_get_index_name` 被 `search` / `search_multi` /
`search_multi_by_page` / `insert_data_with_vector` 等**读写两条路径**都会调用。
即：检索热路径上也会触发建索引/改 mapping，这是历史设计，本次未改动。

## SQL

无。

None.

## 相关配置

`extra_params.auto_update_mapping`（`config/config_es_engine.json`，默认 `False`）——
控制对**已存在索引**是否自动 `put_mapping` 补字段，详见
[update_index_map](es_search_interface.update_index_map.md)。

## 验证记录（2026-08-19）

- 首次每索引 3 次元数据请求（`exists` ×2 + `get_mapping` ×1），之后 **0 次**
- 大小写混用、逗号串形式都能命中缓存
- 全程未发生 `put_mapping`
- 这两个索引在新比对规则下是「无需新增mapping字段」，即假冲突已彻底消除

单测：`tests/test_es_mapping_compare.py`（16 条）

## Inputs / Outputs

Inputs: exact index and optional client binding. Create missing index with complete native HNSW mapping; leave existing fields unchanged with auto_update_mapping false. A concurrent resource_already_exists_exception must be followed by mapping validation. Never cache unsuccessful creation or incompatible mapping. No real business/staging test writes.

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
