# tests.retrieval.test_delete_by_file.test_list_file_names_applies_scope_and_keyword

## Signature

`test_list_file_names_applies_scope_and_keyword()`

## Inputs

参数见当前签名与本文件所列的行为约束。

## Outputs

返回与副作用见下列具体契约；执行位置见 Source。

## Inputs / Outputs

用离线业务实例调用 list_file_names，明确传入 from_type_norm=document。
断言查询同时包含来源精确过滤与文件名 wildcard，返回字段及类型计数不变。
省略参数不再意味着删除白名单；空值行为由 HTTP 参数化测试覆盖。

## SQL / Side effects

Mock 聚合，无真实 ES/SQL 操作。

## Source

`tests/retrieval/test_delete_by_file.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
