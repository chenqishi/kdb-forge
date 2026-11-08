# kdb.mining.common.schema.page_export.write_page_content

## Signature

`write_page_content(page_content_file, add_page_num, wrtite_file, formatter)`

## Inputs

原页面 JSON 文件、页码开关和输出路径（保留历史参数拼写 wrtite_file）；formatter 为原调用来源对应的 trans_page_content_to_text。

## Outputs

沿用 bool(add_page_num)、JSON 读取、原 formatter 调用以及写文件/print 的顺序与异常。文档版本保留有效图片地址；审阅版本仅保留文字，不能用一个格式化器替换两种行为。

## SQL

无。

## Source

`src/kdb/mining/common/schema/page_export.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
