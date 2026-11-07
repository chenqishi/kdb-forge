# kdb.services.fastgpt_proxy.app.query_remote_service

## Signature

`query_remote_service(text: str, api_key=_private_value('7651402af9aa2029f6e02e2f')) -> Dict`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Description

Inputs: text:str; api_key default retains the original published literal via private_value lookup evaluated at function definition time.
Outputs: original asynchronous HTTP response flow unchanged.
SQL: no SQL; original remote FastGPT/HTTP access unchanged. No external operation performed during refactor audit.

## SQL

本契约未新增 SQL；具体外部边界见所列当前实现。

## Source

`src/kdb/services/fastgpt_proxy/app.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
