# kdb.shared.clients.dify_tools.DifyWorkFlowRequest.request_dify

## Signature

`DifyWorkFlowRequest.request_dify(self, paragraph, other_inputs=None)`

## Description

调用 Dify workflow blocking API，并返回 `data.outputs.Final`。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| paragraph | str\|None | 否 | 写入 Dify inputs.paragraph 的主要文本 |
| other_inputs | dict\|None | 否 | 追加到 Dify inputs 的其他字段 |

## Outputs

| 类型 | 说明 |
|------|------|
| str\|None | Dify `Final` 输出；失败、超时或达到最大重试次数时返回 None |

## 行为

- 请求地址为 `{api_base}/workflows/kdb.mining.generation.run`。
- 请求模式为 blocking。
- HTTP timeout 使用实例初始化时传入的 `timeout`，默认 600 秒。
- 非 200、Dify failed、请求异常会按 `max_retries` 重试。

## SQL

No SQL access.

## Source

`src/kdb/shared/clients/dify_tools.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
