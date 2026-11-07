# kdb.shared.config.loader.load_config

## Signature

`load_config(config_path: str) -> Dict[str, Any]`

## Description

读取 rebuild 的 JSON 配置（config_test.json）并返回 dict。配置只含指向旧 config 的绝对路径与 test_index_name，不含任何凭据。

## Inputs

- `config_path` (str): JSON 配置绝对路径。

## Outputs

- `Dict[str, Any]`：含 `engine_config_path` / `embedding_config_path` / `legacy_search_config_path` / `test_index_name`。

## SQL

无。

## Source

`src/kdb/shared/config/loader.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
