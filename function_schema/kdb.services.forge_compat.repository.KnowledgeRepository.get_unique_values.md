# kdb.services.forge_compat.repository.KnowledgeRepository.get_unique_values

## Signature

`KnowledgeRepository.get_unique_values(self, field_name: str, index_name: Optional[str]=None, size: int=10000, include_doc_count: bool=False, extra_query: Optional[Dict[str, Any]]=None) -> Union[List[str], List[Dict[str, Any]]]`

## Inputs

`self, field_name: str, index_name: Optional[str]=None, size: int=10000, include_doc_count: bool=False, extra_query: Optional[Dict[str, Any]]=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

聚合获取某字段唯一值集合。委托旧 `engine.get_unique_values`。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
