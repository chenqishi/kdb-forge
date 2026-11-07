# test_delete_by_file.test_list_file_names_applies_scope_and_keyword

## Inputs / Outputs
用离线业务实例调用 list_file_names，明确传入 from_type_norm=document。
断言查询同时包含来源精确过滤与文件名 wildcard，返回字段及类型计数不变。
省略参数不再意味着删除白名单；空值行为由 HTTP 参数化测试覆盖。

## Side effects / SQL
Mock 聚合，无真实 ES/SQL 操作。
