# tests.retrieval.test_es8_interface.FakeClient.msearch

## Signature

`msearch(self, *, searches, max_concurrent_searches)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Inputs / Outputs

Inputs: ES8 searches alternating headers/bodies and concurrency.
Outputs: mock native batch with positional responses through existing fake search boundary, capturing msearch call; subsearch failures become error items. No real ES writes.

## SQL

None.

## Source

`tests/retrieval/test_es8_interface.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
