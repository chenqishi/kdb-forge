# kdb.services.forge_compat.adapter.KnowledgeService._load_legacy_search_cfg

## Signature

`KnowledgeService._load_legacy_search_cfg(cfg: Dict[str, Any]) -> Dict[str, Any]`

## Inputs

`cfg: Dict[str, Any]`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

Config dict with legacy_search_config_path or search_config_path.

## Outputs

Read the optional legacy service config without hiding missing configuration.

Loaded legacy config dict; warn and return {} if missing/unreadable.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

None; local JSON only.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
