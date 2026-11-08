# tests.retrieval.test_insert_ext_info.test_request_models_remain_unchanged

## Signature

`test_request_models_remain_unchanged()`

## Inputs

原pytest参数/fixtures和测试数据结构不变。

## Outputs

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## 显式HTTP模型字段契约

原测试依赖已外移Git commit和真实git子进程。改为当前11个Request类的显式注解/默认值/Field约束/别名/Config字典比较，保留原10类并覆盖FromTypeCountRequest；无历史Git或外部旧仓依赖。

## Source

`tests/retrieval/test_insert_ext_info.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
