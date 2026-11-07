# KnowledgeRepository.update_by_condition

## Inputs
`self, update_value_dict: Dict[str, Any], conditions: List[Dict[str, Any]], index_name: Optional[str]=None, refresh: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
按条件批量更新字段（如软删除 del_flag=1）。委托旧 `engine.update_value`。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
