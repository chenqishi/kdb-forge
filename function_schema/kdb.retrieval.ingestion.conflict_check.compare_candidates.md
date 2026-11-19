# kdb.retrieval.ingestion.conflict_check.compare_candidates

## Signature

`compare_candidates(current: dict, candidates: list[dict], rerank: Callable, judge: Callable, threshold: float | None=None, min_shared_topics: int=0, aliases=None) -> dict[str, Any]`

## Inputs

待比较知识、同一 index 的候选列表、重排函数、LLM 判定函数及可选分数阈值。只比较同一 data_type 的 qa 或 segment；候选由调用方限定 index。重排函数返回与输入顺序对应的相关分数；判定函数返回关系、理由与两条原文证据。

## Outputs

返回 similarity_info、比较状态、候选数量和失败信息。different 不写入 similarity_info；不确定或证据不属于原文时保留 uncertain。任一请求失败标记 failed，不当成无重复。

## SQL

无；函数不直接访问数据库或写入。

## Current behavior

同类型候选比较；重排0..1分数与主题规则；duplicate/overlap/conflict/different/uncertain，证据须在两侧原文逐字找到。政策冲突须确认共同生效版本/时段，否则uncertain。different仅计入evaluated_ids，不写关系；模型错误显式failed。

## Source

`src/kdb/retrieval/ingestion/conflict_check.py`
