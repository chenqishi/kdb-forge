# tests.mining.test_excel_qa_segment_upload_control.test_run_command_list_preserves_space_containing_argument

## Signature

`test_run_command_list_preserves_space_containing_argument(tmp_path)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Offline执行限制

requires_process标记：本例原body/业务断言保持，因必须真实subprocess而在mandatory offline边界中明确deselect；裸pytest与runner统一，其他测试继续运行。

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`tests/mining/test_excel_qa_segment_upload_control.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
