# kdb.integrations.data_control.retire_superseded_knowledge.fetch_current_state

## Signature

`fetch_current_state(es: EsHttpClient, index: str, ids: List[str], chunk: int=500) -> Dict[str, Dict[str, Any]]`

## Description

按 `_id` 批量取回文档当前的 `del_flag` / `flag` / `insert_time` / `quality_level` / `audit_result`，
供 `plan_retire` 判断该不该删。

## Inputs

- `es` (EsHttpClient)
- `index` (str)
- `ids` (List[str])
- `chunk` (int, 默认 500) — 每批 `ids` query 的大小

## Outputs

`Dict[str, Dict]` — `_id -> _source`。快照后被物理删掉的 `_id` 不会出现在返回值里。

## SQL / ES schema

只读 ES。读取字段：
- `del_flag` (int) — 1 表示已软删
- `flag` (keyword) — 批次标记
- `insert_time` (date, `yyyy-MM-dd HH:mm:ss`) — 索引里**没有 `create_time`**
- `quality_level` (keyword)、`audit_result` (int) — 仅用于日志核对

用 `{'ids': {'values': [...]}}` + `iter_search_after` 而不是逐条 `GET`：
几千条逐条 GET 会打满连接；也不能用 scroll（阿里云 ES Serverless 不支持）。

## Source

`src/kdb/integrations/data_control/retire_superseded_knowledge.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
