# kdb.retrieval.application.search_index_data_interface.SearchDataInterface.find_duplicates

## Signature

`SearchDataInterface.find_duplicates(self, data: Dict[str, Any], topK: int=5, is_need_llm: bool=True, index_name: str=None, exclude_self: bool=False, is_only_title: bool=False, basic_threshold: float=0.7, title_basic_threshold: float=0.95) -> List[Dict[str, Any]]`

## Inputs

旧版 `find_duplicates(data, topK, is_need_llm, index_name, exclude_self, is_only_title,
basic_threshold, title_basic_threshold)`。

## Outputs

返回重复文档列表；候选来自 ES8.17 检索，精确判断使用旧 SimilityTools 兼容实现。
通过 _get_simility_tools 懒加载；无旧依赖时用本地阈值工具，不再跳过查重。

## SQL

无；读 Elasticsearch。

## Source

`src/kdb/retrieval/application/search_index_data_interface.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
