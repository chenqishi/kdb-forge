# fetch_role_config

## 所属文件
`commons/app_role_config.py`

## 功能描述
拉取某个应用（app_id）在某个 client 下的角色配置（peer / teacher / management / prompt 等）。

## Inputs
- `app_id` (str) — 如 `2071478687539675137`（payoneer_olive 橄榄枝计划机器人）
- `client` (str) — 如 `payoneer_olive`
- `timeout` (int, 默认 30)

## Outputs
`List[Dict]` — 接口 `data` 数组，每项 `{"configKey": str, "configValue": list|dict|str}`。
失败（HTTP 异常 / `code != "00000"`）抛 `RuntimeError`，不静默返回空——
名单为空会让「答案是否来自同事」的判定全部失效，必须让调用方感知。

## 接口
`GLOBAL_CONFIG['app_config_get_url']`
= `https://www.lufitglobalselling.com:8888/api/rufit-ai/intranet/ai/config/getRoleConfigList?appId={app_id}&client={client}`
（intranet，无需 token）。已有调用方：`control_service/chat_qa_mining_task_control.py:_generate_prompt_file`。

payoneer_olive / 2071478687539675137 实测：`peer` 727 人，`teacher` 0 人，无 `management` 键。

## SQL
无。
