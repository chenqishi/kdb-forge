# kdb.shared.clients.app_role_config.fetch_role_config

## Signature

`fetch_role_config(app_id: str, client: str, timeout: int=30) -> List[Dict[str, Any]]`

## Description

拉取某个应用（app_id）在某个 client 下的角色配置（peer / teacher / management / prompt 等）。

## Inputs

- `app_id` (str) — 如 `example_app_id`（payoneer_olive 橄榄枝计划机器人）
- `client` (str) — 如 `payoneer_olive`
- `timeout` (int, 默认 30)

## Outputs

`List[Dict]` — 接口 `data` 数组，每项 `{"configKey": str, "configValue": list|dict|str}`。
失败（HTTP 异常 / `code != "00000"`）抛 `RuntimeError`，不静默返回空——
名单为空会让「答案是否来自同事」的判定全部失效，必须让调用方感知。

## 接口

`GLOBAL_CONFIG['app_config_get_url']`
= `https://www.lufitglobalselling.com:8888/api/rufit-ai/intranet/ai/config/getRoleConfigList?appId={app_id}&client={client}`
（intranet，无需 token）。已有调用方：`src/kdb/mining/pipelines/chat_qa.py:_generate_prompt_file`。

## SQL

无。

## Source

`src/kdb/shared/clients/app_role_config.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
