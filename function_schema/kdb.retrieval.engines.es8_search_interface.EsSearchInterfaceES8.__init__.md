# kdb.retrieval.engines.es8_search_interface.EsSearchInterfaceES8.__init__

## Signature

`__init__(self, hosts: Optional[Union[str, List[str]]]=None, index_name: Optional[str]=None, username: Optional[str]=None, password: Optional[str]=None, vector_fields: Optional[Dict[str, int]]=None, config_path: Optional[str]=None, extra_params: Optional[Dict[str, Any]]=None, *, config: Optional[Dict[str, Any]]=None, router: Optional[IndexClientRouter]=None, ensure_index: bool=True) -> None`

## Inputs

保持旧位置参数顺序：`hosts, index_name, username, password, vector_fields, config_path, extra_params`；额外支持 keyword-only `config`、注入测试用 `router`、`ensure_index`。

engine config 或 config_path、默认 index、向量字段、额外参数、可选 router；`ensure_index` 控制初始化时是否检查/创建 ES8 native KNN mapping。

## Outputs

初始化按 index 路由的 ES8.17 native KNN 引擎；默认检查/创建 HNSW mapping。

初始化按 index 路由的 ES8.17 native 查询引擎。

## SQL

无。

## Runtime safety

`extra_params.ensure_index_on_init=false` 可在只读盘点或空目标集群启动服务时关闭初始化建索引。缺省仍保持 `ensure_index=True`。旧 ES7 未索引 dense_vector 不能原地升级，检测到后抛出迁移错误。

`extra_params.ensure_index_on_init=false` 可在只读盘点或空目标集群启动服务时关闭初始化建索引；缺省仍保持原有 `ensure_index=True` 行为。该开关不改变检索 DSL，只避免启动时写入缺失索引。

## Source

`src/kdb/retrieval/engines/es8_search_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
