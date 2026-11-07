# tests.conftest.pytest_collection_modifyitems

## Signature

`pytest_collection_modifyitems(config, items)`

## Inputs

pytest config/items，requires_process标记代表原来必须真实子进程的两例。

## Outputs

优先明确deselect requires_process并打印逐例原因；回调pytest_deselected保留正确统计。其他业务断言完全不变。llm用例在offline套件保持skip，不能通过选marker绕过外部IO guard。

## SQL

禁止真实SQL/网络/子进程。

## Source

`tests/conftest.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
