# load_config

## 所属文件
`src/kdb/config/loader.py`

## 功能描述
读取 rebuild 的 JSON 配置（config_test.json）并返回 dict。配置只含指向旧 config 的绝对路径与 test_index_name，不含任何凭据。

## Inputs
- `config_path` (str): JSON 配置绝对路径。

## Outputs
- `Dict[str, Any]`：含 `engine_config_path` / `embedding_config_path` / `legacy_search_config_path` / `test_index_name`。

## SQL
无。
