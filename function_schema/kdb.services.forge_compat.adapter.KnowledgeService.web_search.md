# kdb.services.forge_compat.adapter.KnowledgeService.web_search

## Signature

`KnowledgeService.web_search(self, query: str, client=None, index_name=None, condition_dicts=None, page_size=None, page_num: int=1, score_threshold=None) -> Tuple[List[Dict[str, Any]], int]`

## Inputs

`self, query: str, client=None, index_name=None, condition_dicts=None, page_size=None, page_num: int=1, score_threshold=None`. Retain the original forge protocol and defaults; see original contracts in function_schema/.

query, client, index_name (string/list), condition_dicts, page_size, page_num,
score_threshold.

## Outputs

Thin protocol forwarding to the single published implementation; preserves normal return values and exceptions.

Delegate to web_search_data: generic explicit category filters, pagination, score
normalization and multimodal rendering. No mining-specific inference.

## SQL

No direct SQL. Only the original injected repository, category, embedding or published application boundaries are called when the public operation requires them.

None; Elasticsearch/category HTTP reads only.

## Source

`src/kdb/services/forge_compat/adapter.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
