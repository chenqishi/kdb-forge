# kdb.services.forge_compat.repository.KnowledgeRepository.search_by_page

## Signature

`KnowledgeRepository.search_by_page(self, query_dict: Dict[str, Any], index_name: Optional[Union[str, List[str]]]=None, size: int=10, page_num: int=1, score_threshold: Optional[float]=None) -> Tuple[List[Dict[str, Any]], int]`

## Inputs

`self, query_dict: Dict[str, Any], index_name: Optional[Union[str, List[str]]]=None, size: int=10, page_num: int=1, score_threshold: Optional[float]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

分页 + score_threshold 过滤检索，返回 (docs, total_num)。委托旧 `engine.search_multi_by_page`。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
