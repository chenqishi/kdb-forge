# KnowledgeRepository.count_by_query

## Inputs
显式原始 `index_name: str` 与原始 `query: Dict[str, Any]`。

## Outputs
`int`，直接委托 engine.count_by_query(..., require_complete=True)，错误上抛。
不调用 _idx、不使用默认索引、不归一化或扩展索引、不附加业务条件。

## SQL
无；只读 ES8 native `_count`，不 ensure/create。
