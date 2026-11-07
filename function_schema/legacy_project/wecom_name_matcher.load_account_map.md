# Function Schema: wecom_name_matcher.load_account_map

## Description
按"添加人 nick_name"反查企业微信账号 we_com_user_id（仅未删除账号）。同名 nick_name 取第一条。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|
| cur | DictCursor | 是 | 已连 rufitai 的字典游标 |
| adder_names | Iterable[str] | 是 | 添加人 nick_name 集合 |

## Outputs
`dict[str, str]`：`{nick_name: we_com_user_id}`。account 表中找不到的 nick_name 不在返回里。

## SQL
读取表 `rf_wkt_we_com_account`（过滤 `nick_name IN (...) AND del_flag = 0`）：
- 读取字段：`nick_name`, `we_com_user_id`
