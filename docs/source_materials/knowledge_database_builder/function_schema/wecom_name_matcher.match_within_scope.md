# Function Schema: wecom_name_matcher.match_within_scope

## Description
在已建好的 scoped 索引里，按 (账号 uid, 姓名) 取命中的外部好友 contact_id 列表（排序、去重）。
返回值即"该名字在该账号下对应的 data_scrm.cid 候选列表"。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| account_uid | str | 是 | 企业微信账号 we_com_user_id |
| name | str | 是 | 待匹配的好友名称（会 .strip()） |
| scoped | dict | 是 | `load_scoped_index` 的返回值 |

## Outputs
`list[str]`：命中的 `we_com_contact_user_id`（= data_scrm.cid）有序列表；无命中返回 `[]`。

## SQL
无 SQL（纯内存查表）。
