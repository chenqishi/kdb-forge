# es_search_interface.EsSearchInterfaceOpen.__init__

## 2026-10-19 unified audit integration

Source: `knowledge_interface_tools/es_search_interface.py`

Inputs: `self, hosts: Optional[List[str]]=None, index_name: Optional[str]=None, username: Optional[str]=None, password: Optional[str]=None, vector_fields: Optional[Dict[str, int]]=None, config_path: Optional[str]=None, extra_params: Optional[Dict[str, Any]]=None`.

Behavior / Outputs: 初始化OpenSearch搜索接口
Args:
    hosts: OpenSearch服务器地址列表
    index_name: 索引名称
    username: 用户名
    password: 密码
    vector_fields: 向量字段配置，格式为 {field_name: dimension}
    config_path: 配置文件路径
    extra_params: 额外的OpenSearch客户端参数

ES / SQL: No SQL. Audit field writes use audit_result only via the existing conditional update contract; inventory/count/aggregation are read-only, no automatic index or mapping creation in opt-in maintenance mode.
