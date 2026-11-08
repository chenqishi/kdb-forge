# kdb.mining.tasks.submission.chat_batch.BatchChatQARequestRunner.create_task_request

## Signature

`create_task_request(self, app_info, appid_records)`

## Description

为单个 appid 构造 `chat_qa_mining` 任务的 `task_info` 请求体，供 `send_task_request` POST 到任务控制服务 `/start_task`。

## Inputs

- `self` — `BatchChatQARequestRunner` 实例
- `app_info` (dict) — 来自 `get_enabled_appids()`，含 `app_id` / `client` / `user` / `scene_type`
- `appid_records` (dict) — `app_id -> last_run_time`（`'%Y-%m-%d %H:%M:%S'`），来自 `data/chatknowledge/appid_record.txt`

保留参数签名 `self, app_info, appid_records`。创建任务请求

## Outputs

- `dict` — `task_info`：

| 字段 | 取值 | 说明 |
|---|---|---|
| `client` | `app_info['client']` | 同时作为 `data_chat_history.customer` 查询条件 |
| `user` | `app_info['user']` | `application_name`，下游作为 robot key |
| `index` | `app_info['client']` | 作为 platform，最终决定 ES 索引名 |
| `app_id` | `app_info['app_id']` | |
| `start_time` | `appid_records[app_id]`，缺失时 `get_default_start_time()` | 增量水位线 |
| `end_time` | `get_end_time_formatted()` | |
| `black_nick_name` | `""` | 控制器仍会无条件叠加全局黑名单 |
| `need_process_name` | `"all"` | |
| `mining_type` | `"normal"` | **必须是 `normal`/`forward`**，写 `norm` 会让 `gen_knowledge_from_chat.py` 抛 `ValueError: 群类型错误` |
| `scene_type` | `app_info.get('scene_type', 'group')` | `group` / `single` / `group,single` |

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.mining.tasks.submission.chat_batch`；全部依赖来自当前 kdb 包。

## SQL

无直接 SQL 读写。`start_time` 来源于文件水位线，其余字段来源见 `batch_run_chatqa_request.get_enabled_appids.md`。

## 注意

- 不传 `index_name`，所以入库索引会回退成 `insert_data['platform']`（即 `index` = client）；若 client 也为空会落到 `config_es_engine.json` 的默认索引。
- `scene_type` 默认 `'group'`：不给某个 app 配置 `chat_mining_scene_type` 时，行为与改动前完全一致，单聊不会被挖。

## SQL / ES

本函数无直接 SQL；应用数据由 get_enabled_appids 读取 rufitai.rf_ai_role_config： id/app_id/config_key/config_value/is_enabled/del_flag；rf_app_info: id/customer/application_name/is_enabled/del_flag。来源为当前同名函数中原SQL；不新增SQL表/字段/写入。任务状态API/挖掘索引操作仍由原服务执行。

## 原业务契约

# create_task_request

## Source

`src/kdb/mining/tasks/submission/chat_batch.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
