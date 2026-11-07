# kdb.integrations.data_control.audit_chat_auto_qa_by_llm.main

## Signature

`main(argv: Optional[List[str]]=None) -> int`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Description

CLI：拉同事名单 → 拉待审 QA → LLM 判定 → 报告 →（`--execute`）写回 `quality_level`。

## Inputs（CLI）

| 参数 | 默认 | 说明 |
|---|---|---|
| `--index` | 必填 | `payoneer_olive` |
| `--client` | 必填 | `payoneer_olive` |
| `--app-id` | `example_app_id` | 取 peer 名单用 |
| `--limit` | 0（不限） | **本机只跑抽样**，硬盘小、别拉全量 |
| `--random-seed` | 0 | 非 0 时随机抽样（配合 `--limit`）|
| `--concurrency` | 4 | |
| `--model` | 空 | 默认取 `llm_config.models.quality` |
| `--work-dir` | `output/audit_chat_auto_<index>` | |
| `--execute` | 关 | 真写 ES |
| `--rollback` | 空 | 回滚文件路径，配合 `--execute` |

## Outputs

`<work-dir>/`：`colleagues.json`、`docs.jsonl`、`decisions.jsonl`、`report.json`、
`rollback.jsonl`（仅 `--execute`）。stdout 打印报告。

## 写回口径

**只写 `quality_level`**，不动 `audit_result` / `ext_info.quality_info` / `update_time`——
与 2026-08-05 那轮重打标一致。检索侧条件是
`(quality_level=high AND audit_result∈[1,2,-1]) OR audit_result∈[1,2]`
（`search_index_data_interface.py`），本批 `audit_result` 全是 -1，
把 `quality_level` 降下去就够把它挡在检索外。

## 跑在哪

本机只跑抽样（硬盘小 + LLM 凭证在本机 `config/llm_config.json`）；
全量去线上机器跑，**线上要先确认有 `config/llm_config.json`**（该文件在 .gitignore 里，
不会被 `git pull` 带过去）。

## SQL

无。

## 为什么脚本自带 bulk_update_doc

`EsHttpClient.bulk_update_doc` 目前只存在于本地工作区（`src/kdb/shared/clients/es_http_client.py` 的未提交改动），
生产机器上的版本没有它，线上 `--execute` 会 `AttributeError`。
`bulk_update_field` 只能写单字段。所以脚本里自带一份模块级 `bulk_update_doc(es, index, updates)`，
直接走 `es._request('POST', '/_bulk', raw_body=...)`，不依赖 commons 的新方法。

## Source

`src/kdb/integrations/data_control/audit_chat_auto_qa_by_llm.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
