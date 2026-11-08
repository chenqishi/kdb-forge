# kdb.mining.tasks.submission.chat_batch.BatchChatQARequestRunner.get_enabled_appids

## Signature

`get_enabled_appids(self)`

## Description

从数据库查询启用了 `timing_run_chat_mining` 配置的 appid 列表，并关联获取对应的 client（customer）、user（application_name），以及该 app 的挖掘场景 `chat_mining_scene_type`（群聊/单聊）。

## Inputs

- `self` — `BatchChatQARequestRunner` 实例，需已初始化 `self.mysql_connector`

保留参数签名 `self`。从数据库获取启用的appid列表

## Outputs

- `list[dict]` — 每个元素包含:
  - `app_id` (str): 应用 ID
  - `client` (str): 平台客户名称（来自 `rf_app_info.customer`），缺失时为 `'default_client'`
  - `user` (str): 应用名称（来自 `rf_app_info.application_name`），缺失时为 `'default_user'`
  - `scene_type` (str): 挖掘场景，取值 `'group'` / `'single'` / `'group,single'`；未配置或取值非法时为 `'group'`（经 `_normalize_scene_type` 校验）

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.mining.tasks.submission.chat_batch`；全部依赖来自当前 kdb 包。

## SQL

### 涉及表

| 表名 | 库名 | 读/写 | 使用字段 |
|---|---|---|---|
| `rf_ai_role_config` | `rufitai` | 读 | `id`, `app_id`, `config_key`, `config_value`, `is_enabled`, `del_flag` |
| `rf_app_info` | `rufitai` | 读 | `id`, `customer`, `application_name`, `is_enabled`, `del_flag` |

### 查询逻辑
```sql
SELECT DISTINCT
    rc.app_id,
    ai.customer as client,
    ai.application_name as user,
    (SELECT sc.config_value
     FROM rufitai.rf_ai_role_config sc
     WHERE sc.app_id = rc.app_id
     AND sc.config_key = 'chat_mining_scene_type'
     AND IFNULL(sc.is_enabled, 1) = 1
     AND IFNULL(sc.del_flag, 0) != 1
     ORDER BY sc.id DESC LIMIT 1) as scene_type
FROM rufitai.rf_ai_role_config rc
LEFT JOIN rufitai.rf_app_info ai ON rc.app_id = ai.id
WHERE rc.config_key = 'timing_run_chat_mining'
AND rc.config_value = '1'
AND IFNULL(rc.is_enabled, 1) = 1
AND IFNULL(rc.del_flag, 0) != 1
AND rc.app_id IS NOT NULL
AND IFNULL(ai.is_enabled, 1) = 1
AND IFNULL(ai.del_flag, 0) != 1
```

### rf_app_info 关键字段
- `customer` varchar(100) — 平台客户名称 → 映射为 `client`
- `application_name` varchar(100) — 应用名 → 映射为 `user`

### rf_ai_role_config 关键 config_key
- `timing_run_chat_mining` — `'1'` 开启定时 chatqa 挖掘，`'0'` 关闭（`config_type='BOOLEAN'`）
- `chat_mining_scene_type` — 可选，挖掘场景。不配置即只挖群聊，保持历史行为

## 注意

- 子查询用 `ORDER BY sc.id DESC LIMIT 1`，同一 app 存在多行 `chat_mining_scene_type` 时取最新一条。
- `scene_type` 最终传给 `src/kdb/mining/chat/sources/sql.py`，那里只识别 `group` / `single` 两个词；两个都不命中会退化成"群聊单聊都不过滤"，所以必须经 `_normalize_scene_type` 白名单校验后再下发。

## SQL / ES

SQL只读：rufitai.rf_ai_role_config: id/app_id/config_key/config_value/is_enabled/del_flag；rf_app_info: id/customer/application_name/is_enabled/del_flag。来源为当前同名函数中原SQL；不新增SQL表/字段/写入。任务状态API/挖掘索引操作仍由原服务执行。

## 原业务契约

# get_enabled_appids

## Source

`src/kdb/mining/tasks/submission/chat_batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
