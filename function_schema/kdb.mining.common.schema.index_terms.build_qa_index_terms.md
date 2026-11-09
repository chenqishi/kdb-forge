# kdb.mining.common.schema.index_terms.build_qa_index_terms

## Signature

`build_qa_index_terms(query, answer, plat_form=None)`

## Inputs

问题、答案和可选平台名称。沿用现有输入类型与真值判断，不增加转换或校验。

## Outputs

依次返回非空问题、带平台前缀的问题（平台为真时）、答案的 jieba topK=10 关键词逗号串（答案为真时）。纯本地索引词生成，不绑定远端平台。此次仅调整函数名称，参数、分支、关键词数量、返回顺序及异常行为均不变。

## SQL

无 SQL、网络、文件写入。

## Source

`src/kdb/mining/common/schema/index_terms.py`
