# Function Schema: build_external_id_map.*

## Description
通过"名称"关联，找出好友 External ID(wm 开头外部联系人ID) 与其企业微信 ID 的映射，并输出统计与比例。
数据库只读。核心难点：rf_wkt_we_com_contact 不存储 wm 开头的 External ID，外部好友的
we_com_contact_user_id 是数字ID，无法直接 join，只能用"名称"关联。

匹配口径：
- **仅在"添加人"本账号(account.nick_name -> we_com_user_id)的好友里按名称匹配，不跨账号。**
- **添加人账号不存在的整组直接移出分析**（不计入分母），单独输出到 excluded sheet。

模块函数：load_excel / build_mapping / compute_stats / write_output。
（`load_account_map` / `load_scoped_index` 已抽至 `data_control_tools/wecom_name_matcher.py`，
被本脚本与致趣 cron `build_zhiqu_external_id_map.py` 共用。）

## Inputs (main 命令行)
| 位置参数 | 默认 | 说明 |
|---|---|---|
| argv[1] config | config/mysql_conn_config.json | MySQL 连接配置(host/database/user/password)，库为 rufitai |
| argv[2] xlsx | data/meikeduo/external_id/external_id_sample.xlsx | 输入 Excel(Sheet1: External ID / 名称 / 添加人) |
| argv[3] out | data/meikeduo/external_id/external_id_wecom_map.xlsx | 输出映射 Excel |

### 关键函数签名
- `load_excel(xlsx_path) -> list[dict{external_id,name,adder}]`
- `load_account_map(cur, adder_names) -> dict{nick_name: we_com_user_id}`（del_flag=0）
- `load_scoped_index(cur, we_com_user_ids) -> dict{(we_com_user_id, 名称): set(we_com_contact_user_id)}`
- `build_mapping(rows, account_map, scoped) -> (results, excluded)`
- `compute_stats(results, excluded) -> dict`（含比例）

## Outputs
输出 Excel（首个 sheet 为最终漏斗）：
- `final_summary`：最终漏斗——① 仅原始名称可确定 / ② 加 chat history 再确定 / 累计可确定 / 剩余无法确定(拆分)
- `mapping`：External ID / 名称 / 添加人 / 添加人账号we_com_user_id /
  匹配到的企业微信ID(分号分隔) / 匹配个数 / 状态
  - 状态 status：`matched` / `name_not_found`（仅含"添加人账号存在"的行）
- `stats`：分析基数(已移除缺失账号组) / 已关联(数+比例) / 未关联(数+比例) /
  因添加人账号缺失被移出(数) / 按"关联企业微信ID个数"分布(数+占已关联比例)
- `per_account_stats`：每个添加人(企业微信账号)各自的 好友总数/已关联/未关联/关联率，账号缺失者标记并整组计 0
- `unmatched`：全部未关联(name_not_found)的行清单（External ID / 名称 / 添加人 / 账号uid）
- `excluded_account_missing`：被整组移出的行（External ID / 名称 / 添加人），其添加人账号在 account 表中不存在

- `multi_disambig_summary`：对"多关联(match_count>1)"的 external_id，用近 90 天对话消歧后的分类汇总
- `multi_disambig_detail`：一行一个候选企业微信ID，含近90天消息数/会话数/最近消息时间/对话对方账号/是否有对话/分类/建议归属ID
- `indistinguishable_count`：每个多关联 external_id 一行（候选总人数/可分清人数/无法分清人数）+ 合计行

辅助函数：
- `compute_per_account_stats(results, excluded, account_map) -> list[dict]`（按好友总数降序）。
- `load_chat_activity(cur, contact_user_ids, days=90) -> (dict{from_user_id: {...}}, cutoff)`
- `disambiguate_multi_by_chat(multi_results, activity) -> (detail_rows, summary)`
- `count_indistinguishable(multi_results, activity) -> (rows, summary)`

## 多关联消歧逻辑（近 90 天对话）
对一个 external_id 命中多个企业微信ID(候选)的情况，用 data_chat_history 近 CHAT_LOOKBACK_DAYS(=90) 天对话区分：
- 以候选 we_com_contact_user_id 作为 `from_user_id`（好友为消息来源）聚合对话活跃度。
- 按"有对话的候选数"分类：
  - 0 → `indistinguishable`（都无对话，视为一样）
  - 1 → `resolvable`（唯一有对话，可定位归属ID，输出建议归属ID）
  - ≥2 → `multi_active`（多个有对话，确为不同的人）

## "还剩多少人无法分清"口径（count_indistinguishable）
按"聊天记录指纹"给同一 external_id 下的候选分组：指纹 = `EMPTY`(近90天无对话) 或 唯一(有对话各自独立)。
- 指纹独一无二 → 分得清；指纹被 ≥2 个候选共享(实际即"都无对话"那批) → 无法分清。
- 单个 EMPTY(唯一)算分得清；只有 ≥2 个 EMPTY 才互相无法分清（与"分不清必≥2"一致）。
- 输出每个 external_id 的 候选总人数/可分清/无法分清，并汇总总数。

## Matching Logic
1. 添加人 nick_name → account.we_com_user_id（del_flag=0）。账号不存在 → 整行移入 excluded，不计入分母。
2. 在该账号的外部好友里按名称命中（scoped）。名称同时比对 nick_name 与 real_name。
3. 命中的 we_com_contact_user_id 去重；同账号内同名重复 → 一个 External ID 命中多个企业微信ID，全部列出。
4. 比例：关联率 = 已关联 / 分析基数；各"关联个数"桶占比 = 该桶 / 已关联数。

## SQL Schema

### Tables Read（数据库 rufitai，只读）

**rf_wkt_we_com_account**（过滤：nick_name IN <添加人集合> AND del_flag=0）
- 读取字段：nick_name, we_com_user_id
- 用途：添加人(企业微信账号名) → 账号 we_com_user_id

**rf_wkt_we_com_contact**（过滤：we_com_user_id IN <已匹配账号> AND relation_type=2 外部 AND type=1 好友 AND del_flag=0）
- 读取字段：we_com_user_id(所属员工账号), we_com_contact_user_id(好友企业微信ID,数字),
  we_com_contact_nick_name(昵称), we_com_contact_real_name(真实姓名,外部好友常为空)
- 注意：we_com_contact_user_id 是同一 corp 内稳定的外部联系人ID；表中无 wm 开头的 External ID 字段。

**data_chat_history**（过滤：from_user_id IN <多关联候选id> AND create_time >= 近90天 AND del_flag=0）
- 读取字段：from_user_id(消息来源=好友id), to_user_id(目标,一般企业微信主账号), session_id, create_time
- 聚合：msg_count=COUNT(*), session_count=COUNT(DISTINCT session_id), last_time=MAX(create_time),
  to_users=GROUP_CONCAT(DISTINCT to_user_id)
- 已验证：好友的 we_com_contact_user_id 即对话表中的 from_user_id（好友作为发送方时）。
