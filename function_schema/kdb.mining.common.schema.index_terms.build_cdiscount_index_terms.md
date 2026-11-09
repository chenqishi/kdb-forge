# kdb.mining.common.schema.index_terms.build_cdiscount_index_terms

## Signature

`build_cdiscount_index_terms(seg_topic, segment, title, topics)`

## Inputs

切片主题、切片文本、标题和逗号分隔主题字符串。保留原有必填参数和字符串处理。

## Outputs

依次返回非空切片主题、非空标题及其 `cdiscount` 前缀形式、切片的 jieba topK=5 关键词逗号串。保留反斜杠 n 的替换及 topics.split 调用，即使拆分结果当前未使用。此次仅改函数名称，不改输出或异常行为。

## SQL

无 SQL、网络、文件写入。

## Source

`src/kdb/mining/common/schema/index_terms.py`
