# tests.retrieval.maintenance.test_prune_dead_raw_urls.test_就地删_粘连的url

## Signature

`test_就地删_粘连的url()`

## Inputs

原pytest参数/fixtures和测试数据结构不变。

## Outputs

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## Source

`tests/retrieval/maintenance/test_prune_dead_raw_urls.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
