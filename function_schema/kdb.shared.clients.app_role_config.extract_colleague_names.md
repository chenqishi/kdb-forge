# kdb.shared.clients.app_role_config.extract_colleague_names

## Signature

`extract_colleague_names(config_items: List[Dict[str, Any]], config_keys: Sequence[str]=DEFAULT_ROLE_KEYS) -> List[str]`

## Description

从角色配置里抽出同事昵称列表，逻辑与 `chat_qa_mining_task_control._generate_prompt_file` 一致。

## Inputs

- `config_items` (List[Dict]) — `fetch_role_config` 的返回
- `config_keys` (Tuple[str], 默认 `('peer', 'teacher', 'management')`)

## Outputs

`List[str]` — 去重后的 `userName`，保持原顺序。

## configValue 的三种形态

| 形态 | 取法 |
|---|---|
| `list[dict]` | 每项取 `userName` |
| `dict` | 取 `userName` |
| 非空 `str` | 整个字符串当成一个名字 |

## SQL

无。

## Source

`src/kdb/shared/clients/app_role_config.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
