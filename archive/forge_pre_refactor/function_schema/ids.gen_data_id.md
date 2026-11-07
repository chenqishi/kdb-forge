# gen_data_id

## 所属文件
`src/kdb/crud/ids.py`

## 功能描述
生成文档唯一 _id。算法与旧 `search_index_data_interface.gen_data_id` 字节级一致：`md5(f"{title}_{content}_{data_type}")`。优先复用旧实现；旧 import 链不可用时退回内置复刻 `_builtin_gen_data_id`（同算法）。

## Inputs
- `data` (Dict): 含 `title` / `content` / `data_type`（缺失按空串）。

## Outputs
- `str`：32 位十六进制 MD5。

## 关键依赖
- `kdb.legacy_bridge.legacy_gen_data_id` / `HAS_LEGACY_GEN_DATA_ID`

## SQL
无。
