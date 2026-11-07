# kdb.integrations.data_control.build_zhiqu_assistant_id_map.build_assistant_map

## Signature

`build_assistant_map(accounts, zhiqu_owners_by_name)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Description

一次性脚本：把 rfwkt 企业微信账号（`rf_wkt_we_com_account`）的 nick_name 与致趣
contact/list 拉出来聚合的 user_owner.name 按字符串相等撞，得到
`zhiqu employee_user_id ↔ rfwkt we_com_user_id` 的稳定映射，落
`config/zhiqu_assistant_id_map.json`。

由人工触发执行；cron 不会调它。账号增减/改名时手动跑一次。

## Inputs（命令行）

| 参数 | 默认 | 说明 |
|---|---|---|
| --client | mercado | 同凭据 json key |
| --corp-id | 1970325020467087 | rfwkt 端 we_com_corp_id 过滤（默认=美国国际销售深圳代表处） |
| --config | config/mysql_conn_config.json | rufitai MySQL 配置 |
| --cred-path | config/zhiqu_credentials.json | 致趣凭据 |
| --out | config/zhiqu_assistant_id_map.json | 输出映射 |
| --dry-kdb.mining.generation.run | false | 仅打印不写文件 |

## Outputs

`config/zhiqu_assistant_id_map.json`：
```json
{
  "<client>": {
    "corp_id": "<rfwkt we_com_corp_id>",
    "assistants": [
      {
        "nick_name": "...",
        "rfwkt_we_com_user_id": "...",
        "zhiqu_employee_user_id": "..."
      }
    ]
  }
}
```
存在时按 client key 增量合并；不影响其他 client 段。

## SQL

读取表 `rf_wkt_we_com_account`（过滤 `we_com_corp_id = ? AND del_flag = 0`）：
- 读取字段：`we_com_user_id`, `nick_name`, `we_com_mobile`

## 外部依赖

- 致趣 API: `POST /api/get-access-token`、`POST /mochat/open-api/contact/list`

## 匹配规则

- 仅按 `nick_name` 字符串等值撞 zhiqu owner.name
- nick_name 在致趣中**仅一个** employee_user_id → 加入 assistants
- 0 个 / ≥2 个 → 报 WARNING，跳过

## Source

`src/kdb/integrations/data_control/build_zhiqu_assistant_id_map.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
