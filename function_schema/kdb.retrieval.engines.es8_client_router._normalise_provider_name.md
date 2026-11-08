# kdb.retrieval.engines.es8_client_router._normalise_provider_name

## Signature

`_normalise_provider_name(name: str) -> str`

## Inputs

provider 名字符串。

## Outputs

标准化的小写 provider 名；`pass` 标准化为 `paas`。

## SQL

无。

## Source

`src/kdb/retrieval/engines/es8_client_router.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
