# tests.retrieval.test_list_file_names_source.test_invalid_source_type

## Signature

`test_invalid_source_type(fixture_service, monkeypatch, source_type)`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Inputs / Outputs

真实 HTTP 模型收到数组、对象、数字、布尔等非字符串来源时返回 422，
不调用聚合。合法空值语义由 test_http_source_filter 覆盖。

## SQL / Side effects

复用离线 fixture_service；无真实网络或数据库读写，无 SQL。

## Source

`tests/retrieval/test_list_file_names_source.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
