# kdb.entrypoints.http.retrieval.models.InsertRequest.get_ext_info_with_extra_fields

## Signature

`get_ext_info_with_extra_fields(self, defined_fields: List[str]=None) -> Dict[str, Any]`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: existing InsertRequest, optional document schema field names. Outputs: a deep-copied dictionary combining explicit ext_info and actual non-model, non-schema business extras; top-level extra overrides same key as existing legacy helper. Exclude request model fields and aliases (id/_id, index_names, refresh_imm, is_need_llm, is_update_data, category controls) from extension inference. Preserve zero/False/empty list/object business values; exclude top-level None as existing model_dump(exclude_none=True); preserve explicit nested nulls. Do not mutate the request or nested inputs. None defined_fields is valid. Public signature and request model fields/defaults/aliases unchanged. No SQL or I/O.

## SQL

None.

## Local activation authorization

2026-10-05 user explicitly authorizes restarting this local old8003 service and clarifies remote Git is unrelated. Apply only the verified ext_info service fix locally, preserving original requests, engine, configuration, other processes, data and dirty files. Production deployment rule remains for actual production; no commit/push or other-service restart authorized.

## Source

`src/kdb/entrypoints/http/retrieval/models.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
