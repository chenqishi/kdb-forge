# KnowledgeRepository.delete

## Inputs
`self, data_id: str, index_name: Optional[str]=None, refresh: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
按 _id 硬删除。委托旧 `engine.delete`。

旧 `engine.delete` 已传 refresh，但实测 Aliyun ES serverless 在高频
操作下仍可能 read-after-delete 看到旧版本，故 refresh=True 时额外
强制刷新索引一次，保证立即不可见。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/repository.py`; independent source proof is recorded in compat_source_proof.json for the restart.
