# tests.mining.test_excel_qa_segment_upload_control.test_stage_3_missing_input_or_config_does_not_run

## Signature

`test_stage_3_missing_input_or_config_does_not_run(tmp_path, missing)`

## Inputs

pytest 临时目录；missing 分别为 input 或 config。输入缺失时保留另一候选文件，防止误用旧文件。

## Outputs

断言返回 False、不会调用命令执行器，保留既有 index_insert 阶段更新；输入缺失时不继续解析配置，配置缺失时不启动任务。

## SQL

状态更新及命令执行均替换；无真实 SQL、网络或子进程。

## Source

`tests/mining/test_excel_qa_segment_upload_control.py`
