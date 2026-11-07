# update_index_map

## 所属文件
`knowledge_interface_tools/es_search_interface.py`
（`EsSearchInterfaceOri` / `EsSearchInterfaceOpen` 各有一份）

## 功能描述
把代码里定义的 mapping 与线上索引的实际 mapping 比对：
**缺失的字段补上**（`put_mapping`），**已存在但配置不一致的字段跳过并告警**。

只被 `_ensure_index` 调用。

## Inputs
- `index_name` (str) — 索引名，内部 `lower()`
- `new_mapping` (dict) — `{"properties": {...}}`，来自 `_ensure_index` 里的字面量

## Outputs
`bool`
- `True` — 比对完成（含「有不兼容字段但已跳过」的情况）
- `False` — 索引不存在、取 mapping 失败、或 `put_mapping` 本身失败

注意返回 `False` 已不再影响 `has_build_index`（见 `_ensure_index` schema）。

## 比对规则（`_mapping_config_equal`）
只检查 `new_mapping` 里出现的键（子集语义），并忽略三类**假冲突**：

| 忽略项 | 原因 |
|---|---|
| `index` / `similarity` 键 | 线上是 **ES 7.10.0**，`dense_vector` 只支持 `dims`；`index`/`similarity` 是 7.16+/8.x 才有的参数，写在 mapping 里会被 ES 静默丢弃。实测所有索引的实际 mapping 都是 `{"type":"dense_vector","dims":1024}` —— 代码里写的 `"similarity": "cosine"` 从来没落地过 |
| `type: object` 且线上无 `type` 键 | object 是 ES 的默认类型，返回的 mapping 不回显 `type`，`existing.get("type")` 是 `None` |
| 嵌套 `properties` 整体 `!=` | 原来把整个子属性字典做 `!=`，只要有一个孙字段带了上面两类无效参数，整块就判不等。改成递归比对 |

改之前这三类假冲突让**线上每一个索引**都 raise：

| 索引 | 触发 raise 的字段 |
|---|---|
| mercado | `indexes.properties`、`image_indexes.type`、`task_id.type`、`primary_category.type`、`multimodal_contents.type`、`ext_info.type` |
| mercado_local / mars_mind | `indexes.properties`、`image_indexes.properties`、`primary_category.type`、`ext_info.type` |
| payoneer_olive / wayfair | 同上 + `task_id.type` |

## 真冲突：不再连坐
`task_id` 线上是 `text`、代码期望 `keyword`（mercado / payoneer_olive / wayfair），
这是**真的改不了**，只能删索引重建。

改之前一次 raise 会掐掉整个函数，导致 mercado / wayfair 上**本该新增的 `categorys_info`
字段也一直加不上**。现在改成：冲突字段记录+跳过，其余新字段照常 `put_mapping`。

## 副作用受 `auto_update_mapping` 控制（默认关）
本函数对**已存在的索引**执行 `put_mapping` 前会先看 `self.auto_update_mapping`
（配置项 `config_es_engine.json` 的 `extra_params.auto_update_mapping`，默认 `False`）。

**默认关的理由**：全量 dry-run 显示放开后会一次性写到 66 个索引 ——
`categorys_info` 66 个、`task_id`/`multimodal_contents` 各 59 个、
`dataset`/`primary_category` 各 22 个、`image_indexes` 10 个，
`test_knowledge` 一个索引就要补 12 个字段。而这些写操作发生在**检索热路径**上。

更要命的是 mapping 字段类型**写进去就改不了**：代码里 `dataset` 的定义是
`{"type": "keyword", "index": False}`，`index: false` 对 keyword 是**真生效**的
（不同于 dense_vector 的 `similarity` 会被 ES 7.10 忽略）。给 22 个索引固化这个定义
意味着以后按 `dataset` 做 term 过滤会报
`Cannot search on field [dataset] since it is not indexed` —— `mars_mind` 已经踩过。

**新建索引不受此开关影响**，始终按完整 mapping 创建。

需要给存量索引补字段时，应当先确认字段定义正确，再显式打开开关（或写一次性运维脚本），
不要靠检索路径顺带完成。

## SQL
无。
