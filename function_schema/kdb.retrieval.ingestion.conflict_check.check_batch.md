# kdb.retrieval.ingestion.conflict_check.check_batch

## Signature

`check_batch(records: list[dict], candidates: list[dict], recall: Callable, rerank: Callable, judge: Callable, threshold: float | None=None, limit: int=60) -> list[dict]`

## Inputs

待检查记录、同一 index 候选、召回函数、重排函数、LLM 判定函数、可选重排阈值与候选上限（默认 60）。候选由调用方限定 index，QA 和 segment 分开比较。

## Outputs

逐条返回候选上限及截断标记、比较结果；不修改原始输入。不同关系不保存为相似项。运行失败明确标记，不代表没有重复。

## SQL

无；不读写数据库。

## Current behavior

同类型候选比较；重排0..1分数与主题规则；duplicate/overlap/conflict/different/uncertain，证据须在两侧原文逐字找到。政策冲突须确认共同生效版本/时段，否则uncertain。different仅计入evaluated_ids，不写关系；模型错误显式failed。

## Source

`src/kdb/retrieval/ingestion/conflict_check.py`
