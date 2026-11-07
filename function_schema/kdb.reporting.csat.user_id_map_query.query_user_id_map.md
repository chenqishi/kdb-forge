# kdb.reporting.csat.user_id_map_query.query_user_id_map

## Signature

`query_user_id_map(mysql_connector, client, start_time, end_time, user_id=None, sid_robots_path=None, assistant_map_path=None)`

## Description

查询用户 cid / email / external_id 映射，支持公众号(`wechatcom_service_substitute`) 与
致趣(`zhiqu_external_id`) 双通道。

当前按 (cid, channel, robot) 平铺记录。zhiqu 行 email 按 (cid, robot 对应 user_id) 精确获取，其他行使用 cid 级 email；cid 级无任何可解析 email 时整组丢弃。external_id 是该行通道的 sid，未命中时为 None。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| mysql_connector | MySQLConnector | 是 | 已初始化的连接实例 |
| client | str | 是 | 租户标识，过滤 data_scrm.client。**支持别名扩展**：传入 `mercado` 时实际查询 `client IN ('mercado','mercado_local')`（见模块顶 `CLIENT_ALIASES`） |
| start_time | str | 是 | 查询起始时间，过滤 data_scrm.create_time >= start_time |
| end_time | str | 是 | 查询结束时间，过滤 data_scrm.create_time <= end_time |
| user_id | str / list | 否 | 若传入则追加 data_scrm.user_id IN (...) 过滤 |
| sid_robots_path | str | 否 | 覆盖默认 `config/zhiqu_sid_to_robots_{client}.json` |
| assistant_map_path | str | 否 | 覆盖默认 `config/zhiqu_assistant_id_map.json`（用于按 robot 精确取 email） |

## Outputs

`list[dict]`，**平铺多行**（按 (cid, channel, robot) 拆）：
| 字段 | 类型 | 说明 |
|---|---|---|
| cid | str | 系统内用户 id |
| email | str \| None | zhiqu 行：`(cid, robot 对应 marsmind uid)` 精确查 `data_scrm.customer_profile_info` 得到，查不到 `None`；wecom / 无 external_id 兜底行：cid 级任一 email |
| customer_name | str \| None | 客户用户名，rfwkt contact 表 nick_name 优先，fallback real_name |
| external_id | str \| None | 该行所属通道的 sid；cid 无任何 external_id → None |
| source | str \| None | `zhiqu` / `wecom_service` / None |
| robot_name | str \| None | 致趣机器人 nick_name（仅 `zhiqu` 行）；其他 None |

拆行规则：cid 仅致趣 N 机器人 → N 行；cid 两通道都有 → 致趣 N 行 + 公众号 1 行。robot_name 由 `config/zhiqu_sid_to_robots_{client}.json` 索引解析（cron 维护）；每 zhiqu 行的 email 通过 `config/zhiqu_assistant_id_map.json` 反查 `nick_name → rfwkt_we_com_user_id`，然后用 `(cid, uid)` 命中 `data_scrm.customer_profile_info` 得到独立 email（16 助手 scope 之外的 robot / data_scrm 里没有对应 uid 的行 → email 为 None）。customer_name 在 query 时按 cid 反查 `rf_wkt_we_com_contact`。

**cid 级过滤**：若该 cid 的所有 data_scrm 行都解析不出 email，则该 cid 整体丢弃（不进入结果集）；但只要至少一行有 email，该 cid 就会 emit（每个 robot 行的 email 独立，可能为 None）。

## SQL

### 读取表
- `data_scrm`：cid, user_id, customer_profile_info, client, create_time, status
- `data_scrm_id_map`：cid, sid, type
- `rf_wkt_we_com_contact`：we_com_contact_user_id、we_com_contact_nick_name、we_com_contact_real_name；按 we_com_contact_relation_type、we_com_contact_type、del_flag 过滤

### Step 1 — 查 data_scrm
```sql
-- clients 来自 CLIENT_ALIASES.get(client, [client])
SELECT cid, user_id, customer_profile_info
FROM data_scrm
WHERE client IN (%s, ...)
  AND create_time >= %s
  AND create_time <= %s
  AND (status IS NULL OR status != 'before_scrm')
  [AND user_id IN (...)]
```

### Step 2 — 查 data_scrm_id_map（双 type）
```sql
SELECT cid, sid, type
FROM data_scrm_id_map
WHERE cid IN (...)
  AND type IN ('wechatcom_service_substitute', 'zhiqu_external_id')
```

### email 解析
customer_profile_info 为 JSON 字符串：
```json
{"clue_cleaning": [{"cleaningKey": "email", "cleaningValue": "contact@example.invalid", ...}]}
```
取 `clue_cleaning` 列表中 `cleaningKey == "email"` 的第一条 `cleaningValue`。

## Source

`src/kdb/reporting/csat/user_id_map_query.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
