# KnowledgeRepository.ensure_index

## Inputs
可选 index_name。
## Outputs
无；优先调用路由引擎的 `_ensure_index(index_name)`，保证 mapping 请求使用该 index 对应 provider；旧引擎则调用 `_impl._ensure_index`。
## SQL
无。
