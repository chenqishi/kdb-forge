# tests.retrieval.test_insert_check_duplicate_arg.test_chat_review_gate_only_attempts_accepted_high

## Signature

`test_chat_review_gate_only_attempts_accepted_high(monkeypatch, tmp_path)`

## Inputs

原pytest参数/fixtures和测试数据结构不变。

## Outputs

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## Source

`tests/retrieval/test_insert_check_duplicate_arg.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
