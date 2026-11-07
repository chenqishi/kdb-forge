# kdb.services.forge_compat.repository.KnowledgeRepository.search

## Signature

`KnowledgeRepository.search(self, query_dict: Dict[str, Any], size: int=10, index_name: Optional[Union[str, List[str]]]=None) -> List[Dict[str, Any]]`

## Inputs

`self, query_dict: Dict[str, Any], size: int=10, index_name: Optional[Union[str, List[str]]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

单引擎原始混合检索（不重排）。委托旧 `engine.search`。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
