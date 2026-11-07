# KnowledgeService.update

## Inputs
`self, data_id: str, doc: Dict[str, Any], index_name: Optional[str]=None, regenerate_embedding: bool=False, refresh: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/forge_protocol/.

## Outputs
按 _id 局部更新文本字段；可选重算向量。总是刷新 update_time。

refresh=True 时强制刷新索引以保证更新立即可见（serverless 上 get-by-id
非严格实时；测试与对齐场景必须传 True）。

## SQL
No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source
`src/kdb/services/forge_compat/adapter.py`; independent source proof is recorded in compat_source_proof.json for the restart.
