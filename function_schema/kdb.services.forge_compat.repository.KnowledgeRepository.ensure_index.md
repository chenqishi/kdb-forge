# kdb.services.forge_compat.repository.KnowledgeRepository.ensure_index

## Signature

`KnowledgeRepository.ensure_index(self, index_name: Optional[str]=None) -> None`

## Inputs

可选 index_name。

## Outputs

无；优先调用路由引擎的 `_ensure_index(index_name)`，保证 mapping 请求使用该 index 对应 provider；旧引擎则调用 `_impl._ensure_index`。

## SQL

无。

## Source

`src/kdb/services/forge_compat/repository.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
