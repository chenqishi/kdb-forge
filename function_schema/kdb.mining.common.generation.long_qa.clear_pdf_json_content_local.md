# kdb.mining.common.generation.long_qa.clear_pdf_json_content_local

## Signature

`clear_pdf_json_content_local(pdf_json_file, output_file, business_context, from_file_name, use_image_content=0, model_name=None, provider=None, quality_profile='', max_chars=12000, image_placeholder_map=None)`

## Inputs

页面 JSON、输出文件、业务背景、来源、图片选项及模型参数，默认值见签名。

## Outputs

生成与原后端兼容的 QA 列表并写出文件；保持内容裁剪、字段过滤及失败返回。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/common/generation/long_qa.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
