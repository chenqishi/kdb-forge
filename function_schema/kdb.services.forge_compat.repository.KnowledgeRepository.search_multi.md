# kdb.services.forge_compat.repository.KnowledgeRepository.search_multi

## Signature

`KnowledgeRepository.search_multi(self, query_dict: Dict[str, Any], index_name: Optional[Union[str, List[str]]]=None, size: int=10, page_num: int=1, recall_mode: Optional[str]=None) -> Tuple[List[Dict[str, Any]], int]`

## Inputs

query_dict、index_name、size、page_num、可选 recall_mode。

## Outputs

委托路由引擎返回 `(docs, total)`；默认配置为 dual，显式 recall_mode 可切回 legacy。

## SQL

无。

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
