# kdb.services.forge_compat.repository.KnowledgeRepository.update_by_id

## Signature

`KnowledgeRepository.update_by_id(self, data_id: str, data: Dict[str, Any], index_name: Optional[str]=None, refresh: bool=False) -> bool`

## Inputs

`self, data_id: str, data: Dict[str, Any], index_name: Optional[str]=None, refresh: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

## Outputs

按 _id 局部更新（部分字段合并，非 upsert）。委托旧 `engine.update`。

旧 `engine.update` 不接受 refresh，但在 Aliyun ES serverless 上 get-by-id
并非严格实时——更新后立即读取可能仍返回旧版本。这里 refresh=True 时
额外强制刷新索引，保证 read-after-write 一致性（测试与对齐场景必需）。

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
