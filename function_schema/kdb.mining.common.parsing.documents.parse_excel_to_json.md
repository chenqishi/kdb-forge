# kdb.mining.common.parsing.documents.parse_excel_to_json

## Signature

`parse_excel_to_json(excel_path, data_dir, chunk_size=30)`

## Inputs

Excel 路径、数据目录和 chunk_size（默认 30）。

## Outputs

按工作表分块形成页面 JSON，保留文件名、表名、行号、列头；错误输出沿原实现。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/common/parsing/documents.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
