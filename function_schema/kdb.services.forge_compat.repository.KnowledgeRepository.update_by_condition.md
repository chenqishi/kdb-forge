# kdb.services.forge_compat.repository.KnowledgeRepository.update_by_condition

## Signature

`KnowledgeRepository.update_by_condition(self, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]], index_name: Optional[str]=None, refresh: bool=False) -> bool`

## Inputs

`self, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]], index_name: Optional[str]=None, refresh: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

按条件批量更新字段（如软删除 del_flag=1）。委托旧 `engine.update_value`。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
