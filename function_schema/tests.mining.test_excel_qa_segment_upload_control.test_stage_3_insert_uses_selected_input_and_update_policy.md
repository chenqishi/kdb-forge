# tests.mining.test_excel_qa_segment_upload_control.test_stage_3_insert_uses_selected_input_and_update_policy

## Signature

`test_stage_3_insert_uses_selected_input_and_update_policy(tmp_path, use_processed_input)`

## Inputs

pytest 临时目录及是否选择图片处理后输入的布尔参数；复用裸控制器，替换配置定位与命令执行。

## Outputs

断言阶段成功、index_insert 状态及完整 argv 列表，包括当前解释器、CLI 模块、所选含空格输入路径、配置路径、is_update_data=1 和目标 index。原始与处理后文件都存在，确保选择不依赖另一文件缺失。

## SQL

状态更新为本地 stub，命令执行为 Mock；仅写临时测试文件，不启动真实子进程或写 ES。

## Source

`tests/mining/test_excel_qa_segment_upload_control.py`
