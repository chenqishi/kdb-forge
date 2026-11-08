# kdb.mining.chat.query_analysis.material_coverage._get_embedder

## Signature

`_get_embedder()`

## Inputs

本项目 config/config_ali_embedding.json。

## Outputs

首次构造 AliEmbedding，之后返回模块级 _EMB 缓存。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/mining/chat/query_analysis/material_coverage.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
