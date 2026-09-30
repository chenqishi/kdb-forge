# KnowledgeService.from_config

## Inputs
重构配置路径、可选 index_name。

## Outputs
加载 ES8.17 Repository、embedding client 和旧服务兼容配置后的 KnowledgeService。
默认索引优先级：显式参数 > default_index_name > test_index_name > engine 配置；
回退到测试索引/engine 时告警。旧配置从 legacy_search_config_path/search_config_path 读取。

## SQL
无；读取本地 JSON 配置。
