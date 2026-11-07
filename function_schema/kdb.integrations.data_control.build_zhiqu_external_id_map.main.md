# kdb.integrations.data_control.build_zhiqu_external_id_map.main

## Signature

`main()`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Description

cron 主流程：致趣 `wx_external_userid` → 本系统 `cid` 映射，写
`rufitai.data_scrm_id_map`（`type='zhiqu_external_id'`）。

仅处理 `config/zhiqu_assistant_id_map.json` 中本 client 的助手 scope。其他 owner
添加的 contact 全部跳过。歧义/未命中不写库，落 TSV 日志。

## Inputs（命令行）

| 参数 | 默认 | 说明 |
|---|---|---|
| --client | mercado | 凭据 + 映射文件 + data_scrm_id_map 的 client 标识 |
| --map | config/zhiqu_assistant_id_map.json | 助手 id 映射 |
| --config | config/mysql_conn_config.json | rufitai MySQL 配置 |
| --cred-path | config/zhiqu_credentials.json | 致趣凭据 |
| --from-dump | (无) | 调试用：复用本地 contact dump JSON |
| --log-dir | logs | TSV 日志目录 |
| --dry-kdb.mining.generation.run | false | 只统计不写库 |

## Outputs

1. **MySQL 落库**（除 dry-kdb.mining.generation.run）：`INSERT INTO data_scrm_id_map (cid, client, type, sid,
   create_time, update_time)`，仅对差集 `(cid, sid)` 插入；已存在 `(client, type, cid, sid)`
   组合自动跳过。
2. **TSV 日志**：
   - `logs/ambiguous_zhiqu_YYYYMMDD.tsv`：同 owner scope 下 name 命中 ≥2 候选 cid
   - `logs/unmatched_zhiqu_YYYYMMDD.tsv`：scope 内 owner 但 name 在 rfwkt 没命中

## SQL Schema

### 读
- `rf_wkt_we_com_contact`（载入 scope 内的外部好友姓名索引 — 见 `wecom_name_matcher`）
- `data_scrm_id_map`：`SELECT cid, sid FROM ... WHERE client=? AND type='zhiqu_external_id'`

### 写
- `data_scrm_id_map`：INSERT（cid / client / type='zhiqu_external_id' / sid / create_time /
  update_time）。无主键约束 → 应用层做差集保证幂等。

## Pipeline

```
config/zhiqu_assistant_id_map.json   →  zhiqu employee_user_id ↔ rfwkt we_com_user_id (16 条)
致趣 contact/list (全量)             →  list[{wx_external_userid, name, owners}]
filter owners 在映射表内             →  in_scope contacts
load_scoped_index(rfwkt 16 uid)      →  (uid, name) → set(contact_id=data_scrm.cid)
match_within_scope(uid, name)        →  每 contact 取候选 cid 并集
  └─ 1 个候选  → matched, 进入差集 → INSERT
  └─ 0 个候选  → unmatched.tsv
  └─ ≥2 候选   → ambiguous.tsv
```

## 外部依赖

- 致趣 API: `POST /api/get-access-token`、`POST /mochat/open-api/contact/list`
- MySQL: rufitai DB

## Source

`src/kdb/integrations/data_control/build_zhiqu_external_id_map.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
