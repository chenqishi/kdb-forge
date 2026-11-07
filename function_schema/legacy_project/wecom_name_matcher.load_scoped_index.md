# Function Schema: wecom_name_matcher.load_scoped_index

## Description
载入这些企业微信助手账号名下的外部好友，建索引 `(account_uid, 名称) -> set(cid)`，
供「致趣 external_id → 本系统 cid」的名称关联使用。

**数据源是两张表的并集**（2026-08-19 起）：

| 表 | 覆盖 mercado 客户 | 说明 |
|---|---:|---|
| `rf_wkt_we_com_contact` | 23790 (75.9%) | 原有唯一数据源 |
| `lm_channel_contact` | 13547 (43.2%) | 后补入，与上表互补 |
| **并集** | **27080 (86.4%)** | 只有 rf_wkt 有 13533 / 只有 lm 有 3290 / 都有 10257 |

两张表**互补而非替代**，都必须保留：单用任一张都会丢客户（实测妮妮 rf_wkt 349 / lm 253 / 并集 440）。
并集后剩余未覆盖的 4250 个客户里 97.8% 归属 `wxid_*`（个人微信渠道，不在企微好友体系内，
本来就拿不到致趣 external_id），企微口径下并集覆盖率约 99.6%。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| cur | DictCursor | 是 | 字典游标 |
| we_com_user_ids | Iterable[str] | 是 | 助手账号 uid 集合（`rf_wkt_we_com_account.we_com_user_id`，与 `lm_channel_contact.account_id` 同一 id 空间，已实测 16 个助手命中 12 个） |

## Outputs
`dict[tuple(str,str), set[str]]`：键 `(account_uid, name.strip())`，值是命中的客户 cid 集合。
cid 等同于本系统 `data_scrm.cid`（数字串）。两张表命中的 cid 合并进同一个 key。

## SQL

### 表 1：`rf_wkt_we_com_contact`（原有，逻辑不变）
- 过滤：`we_com_user_id IN (...) AND we_com_contact_relation_type=2 AND we_com_contact_type=1 AND del_flag=0`
- 读取字段：`we_com_user_id`(助手), `we_com_contact_user_id`(cid), `we_com_contact_nick_name`, `we_com_contact_real_name`

### 表 2：`lm_channel_contact`（新增）
- 过滤：`account_id IN (...) AND del_flag='0' AND channel_type='we_com_wkteam' AND user_id <> account_id`
- 读取字段：`account_id`(助手), `user_id`(cid), `nickname`, `real_name`
- **三个坑**：
  1. `del_flag` 是**字符串** `'0'` 不是数字 0
  2. `channel_type` 混了 `we_com_wkteam`(企微 31766) 和 `wx_wkteam`(个人微信 4823)，
     后者 `account_id` 是 `wxid_*`，跟致趣对不上，必须过滤
  3. 这张表**没有 relation_type / type 字段**，无法像表 1 那样筛「外部个人好友」，
     存在 `user_id = account_id` 的自指行（助手自己），需显式排除

## 影响面
- 调用方 `build_zhiqu_external_id_map.py:231`(cron) 与 `build_external_id_map.py:433`(一次性脚本)
  **无需修改**：签名与返回结构不变
- 下游 `categorize` / 写 `data_scrm_id_map` / `sid_to_robots` / `/inner_external_user_id_map` 接口均不变
- 并集后候选变多，`ambiguous`（同一助手下同名多 cid）可能上升；脚本对歧义保守不写库，
  所以**只会少关联、不会关错**。注意 `lm_channel_contact` 有 3374 行单字符昵称（如 `.`），撞名概率不低
- 接口返回的 `customer_name` 走 `user_id_map_query._load_cid_to_name`（仍只查 `rf_wkt_we_com_contact`），
  本次未改，只在 lm 里有名字的客户 `customer_name` 仍为 null
