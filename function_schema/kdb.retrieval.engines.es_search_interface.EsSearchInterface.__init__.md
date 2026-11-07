# kdb.retrieval.engines.es_search_interface.EsSearchInterface.__init__

## Signature

`EsSearchInterface.__init__(self, hosts: Optional[List[str]]=None, index_name: Optional[str]=None, username: Optional[str]=None, password: Optional[str]=None, vector_fields: Optional[Dict[str, int]]=None, config_path: Optional[str]=None, extra_params: Optional[Dict[str, Any]]=None, es_version: Optional[str]=None, *, maintenance_mode: bool=False)`

## Inputs

原有 hosts/index_name/username/password/vector_fields/config_path/extra_params/es_version。
`es_version` 或配置顶层 `es_version` 为 `es8`/`8.17` 时选择 ES8.17 实现；未指定时保留原 ES7/OpenSearch 自动检测和默认行为。

## Outputs

旧接口代理工厂；ES8 配置返回 `EsSearchInterfaceES8`。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es_search_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
