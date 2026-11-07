# kdb.services.forge_compat.adapter.KnowledgeService.update

## Signature

`KnowledgeService.update(self, data_id: str, doc: Dict[str, Any], index_name: Optional[str]=None, regenerate_embedding: bool=False, refresh: bool=False) -> bool`

## Inputs

`self, data_id: str, doc: Dict[str, Any], index_name: Optional[str]=None, regenerate_embedding: bool=False, refresh: bool=False`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

Document ID, partial document, optional index_name, regenerate_embedding, refresh.
Explicit indexes replaces the index list as before. Without explicit indexes,
title/synonyms changes with regeneration require reading the stored document.

## Outputs

按 _id 局部更新文本字段；可选重算向量。总是刷新 update_time。

refresh=True 时强制刷新索引以保证更新立即可见（serverless 上 get-by-id
非严格实时；测试与对齐场景必须传 True）。

Boolean write result. Preserves unrelated fields and caller input; refreshes
update_time. Updates both root vectors and derived indexes used by ES8 native KNN.
Missing/unreadable source when merging derived indexes raises ValueError before
writing, rather than silently erasing existing custom/image/synonym index entries.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

None; repository get/update on the same requested Elasticsearch index.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
