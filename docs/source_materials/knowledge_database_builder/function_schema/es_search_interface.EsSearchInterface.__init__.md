# EsSearchInterface.__init__

## Inputs
原有 hosts/index_name/username/password/vector_fields/config_path/extra_params/es_version。
`es_version` 或配置顶层 `es_version` 为 `es8`/`8.17` 时选择 ES8.17 实现；未指定时保留原 ES7/OpenSearch 自动检测和默认行为。
## Outputs
旧接口代理工厂；ES8 配置返回 `EsSearchInterfaceES8`。
## SQL
无。
