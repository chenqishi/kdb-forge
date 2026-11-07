# Function Schema: zhiqu_contact_fetcher.fetch_all_contacts

## Description
调致趣 OpenAPI `/mochat/open-api/contact/list` 分页拉某 client 的全量企业微信外部联系人。
读凭据 `config/zhiqu_credentials.json`，进程内缓存 access_token（2h TTL，10003 自动刷新）。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| client | str | 是 | 凭据 JSON 中的 client key，如 `mercado` |
| cred_path | str | 否 | 凭据文件路径，默认 `config/zhiqu_credentials.json` |
| page_size | int | 否 | 每页条数，默认 100 |

## Outputs
`list[dict]`，每条：
| 字段 | 类型 | 说明 |
|---|---|---|
| wx_external_userid | str | 致趣返回的 wm... 外部联系人 ID（落 data_scrm_id_map.sid） |
| name | str | 联系人 name |
| owners | list[str] | 添加人企业微信账号 nick_name 列表。is_primary=1 在前，去重保序 |

## SQL
无（纯外部 HTTP 调用）。

## 外部依赖
- HTTP: `POST https://openapi.beschannels.com/api/get-access-token`
- HTTP: `POST https://openapi.beschannels.com/mochat/open-api/contact/list?access_token=...`

## 错误码
| code | 含义 | 处理 |
|---|---|---|
| 0 | 成功 | — |
| 10003 | token 过期 | 内部刷新重试一次 |
| 其他非 0 | 业务错误 | 抛 RuntimeError，包含原始 resp |
