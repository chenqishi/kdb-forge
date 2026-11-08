# kdb.entrypoints.http.retrieval.routes.insert

## Signature

`insert(request: InsertRequest)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: original HTTP InsertRequest, actual SearchDataInterface. Outputs: unchanged InsertResponse/status contract. Compute extension dict using corrected helper; forward it to insert_to_service rather than None. Missing/null extension and no actual extras forwards None; explicit empty object remains empty, leaving original engine partial object merge semantics intact. Existing category handling, type defaults, original _id/index_names and other explicit arguments remain. No endpoint or input model changes. 2026-10-05 user explicitly says 遇到问题就解决, authorizing the identified old service forwarding fix in isolated checkout, superseding earlier keep-business-unchanged for this specific defect; does not authorize deployment/restart/scripts. Real writes only via existing exact synthetic fixtures when testing. No SQL.

## SQL

None.

## Local activation authorization

2026-10-05 user explicitly authorizes restarting this local old8003 service and clarifies remote Git is unrelated. Apply only the verified ext_info service fix locally, preserving original requests, engine, configuration, other processes, data and dirty files. Production deployment rule remains for actual production; no commit/push or other-service restart authorized.

## Source

`src/kdb/entrypoints/http/retrieval/routes.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
