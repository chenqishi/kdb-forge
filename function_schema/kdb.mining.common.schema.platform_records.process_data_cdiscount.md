# kdb.mining.common.schema.platform_records.process_data_cdiscount

## Signature

`process_data_cdiscount(data_file)`

## Inputs

UTF-8 本地 TSV 文件，字段为切片主题、切片、标题和主题字符串。

## Outputs

跳过空行及字段数不为 4 的行，调用 `build_cdiscount_index_terms`，按原格式打印切片主题、切片、平台属性及索引词。只更新辅助函数名称，格式、顺序和异常行为不变。

## SQL

无 SQL 或网络；只读输入文件，输出至 stdout。

## Source

`src/kdb/mining/common/schema/platform_records.py`
