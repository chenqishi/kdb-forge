# kdb.mining.web.processing.greenchannel_records.main

## Signature

`main()`

## Inputs

原 argparse 命令参数。

## Outputs

加载类目并生成绿通记录，按原匹配规则写 JSON 并打印统计。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/web/processing/greenchannel_records.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
