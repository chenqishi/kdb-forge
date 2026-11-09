# kdb.mining.common.schema.platform_records.add_attrs_and_indexs

## Signature

`add_attrs_and_indexs(data_file, plat_form='None')`

## Inputs

UTF-8 本地 TSV 文件，每个非空行含问题和答案；可选平台字段的原默认值为字符串 `'None'`。

## Outputs

逐行读取，调用 `build_qa_index_terms`，向标准输出打印问题、答案、平台属性和竖线分隔索引词。保留原始空行处理、字段拆分、输出格式和异常行为；只更新本地辅助函数名称，不调用远端平台。

## SQL

无 SQL 或网络；只读输入文件，输出至 stdout。

## Source

`src/kdb/mining/common/schema/platform_records.py`
