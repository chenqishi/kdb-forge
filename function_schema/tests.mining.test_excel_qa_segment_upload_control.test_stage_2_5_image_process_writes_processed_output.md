# tests.mining.test_excel_qa_segment_upload_control.test_stage_2_5_image_process_writes_processed_output

## Signature

`test_stage_2_5_image_process_writes_processed_output(tmp_path, monkeypatch)`

## Inputs

原pytest参数/fixtures和测试数据结构不变。

## Outputs

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## 当前子进程环境契约

fake_run接收env并断言当前src已在PYTHONPATH，原cmd/shell/output断言保留。

## Source

`tests/mining/test_excel_qa_segment_upload_control.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
