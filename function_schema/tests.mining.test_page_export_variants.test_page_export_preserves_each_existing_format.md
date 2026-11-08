# tests.mining.test_page_export_variants.test_page_export_preserves_each_existing_format

## Signature

`test_page_export_preserves_each_existing_format(export, tail, tmp_path, capsys)`

## Inputs

合成数据、临时目录与 pytest 替身；不访问线上服务。

## Outputs

文档模式保留有效图片 URL，审阅模式仅文本；页码默认值与打印/写文件结果保持一致。

## SQL

无直接 SQL；外部依赖在测试中由替身隔离。

## Source

`tests/mining/test_page_export_variants.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
