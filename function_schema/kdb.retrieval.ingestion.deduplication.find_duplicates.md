# kdb.retrieval.ingestion.deduplication.find_duplicates

## Signature

`find_duplicates(self, data: Dict[str, Any], topK: int=5, is_need_llm: bool=True, index_name: str=None, exclude_self: bool=False, is_only_title: bool=False, basic_threshold: float=0.7, title_basic_threshold: float=0.95) -> List[Dict[str, Any]]`

## Inputs

旧版 `find_duplicates(data, topK, is_need_llm, index_name, exclude_self, is_only_title,
basic_threshold, title_basic_threshold)`。

## Outputs

返回重复文档列表；候选来自相同 index、相同 data_type 的 ES8.17 在线召回，不限制 platform 或审核状态；保留 topK、向量阈值及 exclude_self 行为。精确文本与向量规则由 SimilityTools 实现，可选 LLM 直接调用，不再使用 Dify。

## SQL

无；读 Elasticsearch。

## Public bindings

下列方法绑定同一实现，调用时仍使用各自原实例；类方法/静态方法描述符不变。

- `kdb.retrieval.application.search_index_data_interface.SearchDataInterface.find_duplicates`

## Source

`src/kdb/retrieval/ingestion/deduplication.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
