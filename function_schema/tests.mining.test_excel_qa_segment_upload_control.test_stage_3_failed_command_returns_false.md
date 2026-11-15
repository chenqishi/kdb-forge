# tests.mining.test_excel_qa_segment_upload_control.test_stage_3_failed_command_returns_false

## Signature

`test_stage_3_failed_command_returns_false(tmp_path, execution_failure)`

## Inputs

pytest 临时目录；命令执行器分别返回 False 或抛出 RuntimeError。

## Outputs

调用实际 stage_3 逻辑，断言 False 返回且执行器只被调用一次，防止失败被误报成功。

## SQL

状态更新及命令执行均替换；无真实 SQL、网络或子进程。

## Source

`tests/mining/test_excel_qa_segment_upload_control.py`
