# tests.retrieval.test_document_dedup.test_replace_defers_delete_and_checks_new_insert_count

## Signature

`test_replace_defers_delete_and_checks_new_insert_count(tmp_path, monkeypatch)`

## Inputs

参数以签名为准。

## Outputs

离线行为验证/明确的测试夹具，不访问生产数据。

## SQL / ES

无SQL；测试仅替换外部边界。真实LLM服务验证仅由独立入口显式启动。

## Source

`tests/retrieval/test_document_dedup.py`
