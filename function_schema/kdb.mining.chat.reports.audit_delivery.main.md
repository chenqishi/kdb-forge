# kdb.mining.chat.reports.audit_delivery.main

## Signature

`main()`

## Inputs

保留参数签名 ``。输入结构、CLI位置参数与原实现一致。

## Outputs

保持当前同名函数的返回类型、异常、轮询超时、HTTP请求体、成功水位推进与报告格式。正式入口为 `python -m kdb.mining.chat.reports.audit_delivery`；全部依赖来自当前 kdb 包。

## SQL / ES

本函数不直接SQL。原gen_audit_data与trans_es_data_to_excel从ES读取审计数据并写本地txt/xlsx；报告函数保持相同接收人/发送URL参数。

## 子进程

`sh -x scripts/operations/export_audit_data.sh <platform> <es-config> -1 <data-dir> <flag> high chat_auto` 与当前解释器 `-m kdb.mining.chat.reports.knowledge gen_chatknowledge_report`。原argv和是否使用shell保持不变；环境经subprocess_env继承并前置当前src。

## Source

`src/kdb/mining/chat/reports/audit_delivery.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
