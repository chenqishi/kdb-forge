# bulk_update_doc

## 所属文件
`commons/es_http_client.py`（`EsHttpClient` 方法）

## 功能描述
`_bulk` 多字段 partial update。`bulk_update_field` 一次只能写一个字段，
而软删要**同时**写 `del_flag` 和 `flag`，故有此方法。

## Inputs
- `index` (str)
- `updates` (List[Tuple[str, Dict]]) — `[(_id, {field: value, ...}), ...]`
- `batch_size` (int, 默认 `DEFAULT_BULK_BATCH`=200) — 遇 413 自动折半，下限 10

## Outputs
`Dict` — `{'updated': int, 'failed': [{'_id':..., 'error':...}]}`

## SQL / ES schema
写 ES：只写 `updates` 里给出的字段，其余字段不动。
软删场景写的是 `del_flag`(int) 与 `flag`(keyword)。

## 为什么必须逐条查 items
**Serverless 返回 200 不代表成功**，错误藏在 `payload['items'][i]['update']['error']` 里。
只看 HTTP status 会把整批失败当成功。

## 复核
写回后立刻查会读到矛盾数字（refresh 延迟），要隔一轮再对账。
