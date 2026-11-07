# kdb.integrations.data_control.wecom_name_matcher.match_within_scope

## Signature

`match_within_scope(account_uid, name, scoped)`

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

## Source

`src/kdb/integrations/data_control/wecom_name_matcher.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
