# EsSearchInterface.__init__

## Inputs
原有 hosts/index_name/username/password/vector_fields/config_path/extra_params/es_version。
`es_version` 或配置顶层 `es_version` 为 `es8`/`8.17` 时选择 ES8.17 实现；未指定时保留原 ES7/OpenSearch 自动检测和默认行为。
## Outputs
旧接口代理工厂；ES8 配置返回 `EsSearchInterfaceES8`。
## SQL
无。

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_search_interface.py`

Inputs: `self, hosts: Optional[List[str]]=None, index_name: Optional[str]=None, username: Optional[str]=None, password: Optional[str]=None, vector_fields: Optional[Dict[str, int]]=None, config_path: Optional[str]=None, extra_params: Optional[Dict[str, Any]]=None, es_version: Optional[str]=None, *, maintenance_mode: bool=False`.

Behavior / Outputs: 初始化ES搜索接口工厂类
Args:
    hosts: ES服务器地址列表
    index_name: 索引名称
    username: 用户名
    password: 密码
    vector_fields: 向量字段配置，格式为 {field_name: dimension}
    config_path: 配置文件路径
    extra_params: 额外的ES客户端参数
    es_version: ES版本信息，可选值：'es7'（默认）、'opensearch2'

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
