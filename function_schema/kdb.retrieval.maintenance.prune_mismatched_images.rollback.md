# kdb.retrieval.maintenance.prune_mismatched_images.rollback

## Signature

`rollback(config_path: str, index: str, rollback_file: str, embedding_config: str='config/config_ali_embedding.json', bulk_batch: int=DEFAULT_BULK_BATCH, execute: bool=False) -> Dict[str, Any]`

## Inputs

ES 配置、索引、rollback JSONL、embedding 配置、批大小与 execute。

## Outputs

默认只报告计划数；execute 时恢复 content/multimodal_contents 并重算 content_embedding 后批量更新。

## SQL

本函数无直接 SQL 语句；外部存储/模型行为见 Outputs 与调用模块的契约。

## Source

`src/kdb/retrieval/maintenance/prune_mismatched_images.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
