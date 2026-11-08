# kdb.mining.common.generation.segments.get_segment_knowledge_by_local_llm

## Signature

`get_segment_knowledge_by_local_llm(pdf_json_file, business_context, from_file_name, platform=None, use_image_content=0, model_name=None, provider=None, max_chars=12000)`

## Inputs

页面 JSON、业务背景、来源、平台、图片与模型参数，默认值见签名。

## Outputs

生成兼容原 segment_info 的主题段列表；保持裁剪、解析及不可用时返回空列表。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/common/generation/segments.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
