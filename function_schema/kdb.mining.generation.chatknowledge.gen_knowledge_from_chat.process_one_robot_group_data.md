# kdb.mining.generation.chatknowledge.gen_knowledge_from_chat.process_one_robot_group_data

## Signature

`process_one_robot_group_data(robot_name, data_file, robot_room_type_config, robot_white_list_dict, robot_room_process_record=None, need_robot_reply=False, need_add_chat_history=True, prompt_file=None, client=None, identity_lookup=None, mysql_config_file='config/mysql_conn_config.json', run_stats=None)`

## Description

处理单个机器人（robot = `rf_app_info.application_name`）的全部聊天数据：按群重组消息、
逐群决定群类型/平台、调用 Dify 抽取 QA、按黑名单过滤答案来源，并记录每个群的处理水位线。

## Inputs

- `robot_name` (str) — 机器人标识，同时是 `robot_room_type_config` 的 key
- `data_file` (str) — `chat_data.txt` 路径，3 列 TSV：`send_name \t message_time \t message_info_json`
- `robot_room_type_config` (dict) — 由 `robot_room_type_config.txt` 解析，
  含 `type`（`normal`/`forward`）、`platform`、`black_group`；`'all'` 为通配条目
- `robot_white_list_dict` (dict) — 每个群的白名单
- `robot_room_process_record` (dict | None) — `robot -> group -> 已处理到的时间`，用于增量
- `need_robot_reply` (bool) — 默认 `False`，为 False 时丢弃 `type == 'reply'` 的机器人回复
- `need_add_chat_history` (bool) — 是否给每条 QA 附 `from_chat_history` 便于审核
- `prompt_file` (str | None) — system prompt 文件路径，`None` 时用 Dify 应用内置 prompt

## Outputs

- `list[dict]` — 该机器人所有群抽取到的 QA

## 关键行为

### 逐群失败隔离
每个群的 `process_one_group_data` 调用包在 `try/except` 里，异常只跳过该群并记
`logging.error(..., exc_info=True)`，**不会丢掉其它群已经抽好的 QA**。

改动前没有这层保护：任意一个群抛异常（最常见是 Dify 返回 `None` 导致
`parse_qa_answer` 的 `AttributeError`）会让整个机器人这一轮的 `all_qa_list` 全部丢失，
表现为任务在 `qa_generation` 阶段失败、产出 0 条。

### 群的取舍顺序
1. `group_name` 命中 `robot_room_type_config` → 用该群自己的 type/platform
2. 否则若配置里有 `'all'` → 先判黑名单（`group_name in black_group` 则跳过），再用 `all` 的 type/platform
3. 两者都不满足 → 跳过该群

### 答案来源过滤
配置含 `'all'` 时，最终按 `qa_info['source'] not in black_group` 过滤，剔除非专业人士给出的答案。

## SQL

无直接 SQL 读写。

## Source

`src/kdb/mining/generation/chatknowledge/gen_knowledge_from_chat.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
