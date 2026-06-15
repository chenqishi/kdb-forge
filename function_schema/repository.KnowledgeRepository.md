# KnowledgeRepository

## 所属文件
`src/kdb/crud/repository.py`

## 功能描述
纯向量 CRUD 层。把"向量已就绪的文档"原样进出 ES，封装并复用旧 `EsSearchInterface`（工厂，自动适配 ES7.x / OpenSearch2.19）。不生成 embedding、不生成 _id、不做任何业务过滤。所有方法委托底层旧引擎。

## 构造
`__init__(engine=None, engine_config_path=None, default_index=None)`
- `engine`: 旧 `EsSearchInterface` 实例；为 None 时用 `engine_config_path` 构造（显式 index_name=default_index）。
- `default_index`: 默认索引名；方法未显式传 index_name 时使用，回退到 engine 内部 index_name。

## 方法 Inputs/Outputs
- `ensure_index(index_name=None) -> None`：委托 `_impl._ensure_index`，用权威 mapping 建索引（已存在则增量加字段）。
- `insert(data: Dict, index_name=None, refresh_imm=False) -> bool`：前置 data 含 `_id`、`indexes[].embedding` 为 1024 维 list；委托 `engine.insert`（校验维度、过滤零向量、`es.update(doc_as_upsert=True)`）。
- `get(data_id: str, index_name=None) -> Optional[Dict]`：返回 `{"_id":..., **_source}` 或 None。
- `update_by_id(data_id: str, data: Dict, index_name=None) -> bool`：局部合并更新（非 upsert），委托 `engine.update`。
- `update_by_condition(update_value_dict: Dict, conditions: List[Dict], index_name=None) -> bool`：按条件批量改字段（软删除 del_flag=1 等），委托 `engine.update_value`。
- `delete(data_id: str, index_name=None, refresh=False) -> bool`：硬删除，委托 `engine.delete`。
- `search(query_dict: Dict, size=10, index_name=None) -> List[Dict]`：单引擎混合检索（不重排），委托 `engine.search`。
- `search_multi(query_dict, index_name=None, size=10, page_num=1) -> Tuple[List, int]`：委托 `engine.search_multi`。
- `search_by_page(query_dict, index_name=None, size=10, page_num=1, score_threshold=None) -> Tuple[List, int]`：委托 `engine.search_multi_by_page`。
- `get_unique_values(field_name, index_name=None, size=10000, include_doc_count=False, extra_query=None)`：委托 `engine.get_unique_values`。

query_dict 通用结构：`{"query": <text>, "vector": {"value": <list[float]|np.ndarray>}, "attribute": <dict|list[dict]>}`。

## 关键依赖
- `kdb.legacy_bridge.EsSearchInterface`（旧底层适配层）

## SQL
不直接读写 SQL。底层存储为 Elasticsearch / OpenSearch；mapping 由旧 `es_search_interface.py:_ensure_index` 定义（权威）。
