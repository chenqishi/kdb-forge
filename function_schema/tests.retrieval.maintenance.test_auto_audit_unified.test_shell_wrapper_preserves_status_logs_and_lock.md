# tests.retrieval.maintenance.test_auto_audit_unified.test_shell_wrapper_preserves_status_logs_and_lock

## Signature

`test_shell_wrapper_preserves_status_logs_and_lock(tmp_path)`

## Inputs

原pytest参数/fixtures和测试数据结构不变。

## Outputs

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## Offline执行限制

requires_process标记：本例原body/业务断言保持，因必须真实subprocess而在mandatory offline边界中明确deselect；裸pytest与runner统一，其他测试继续运行。

## Source

`tests/retrieval/maintenance/test_auto_audit_unified.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
