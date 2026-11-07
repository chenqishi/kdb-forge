# tests.mining.test_generic_mining_context.test_context_query_exclude_terms_filter_and_cache_key

## Signature

`test_context_query_exclude_terms_filter_and_cache_key(tmp_path, monkeypatch)`

## Inputs

- Pytest temporary directory and monkeypatch fixture.

原pytest参数/fixtures和测试数据结构不变。

## Outputs

- Regression assertions that excluded country terms are removed before intent summarization and that filter changes produce a distinct context cache key.

保留业务断言与mock语义；仅把旧import、source定位、mock目标、入口argv映射到当前kdb模块及scripts目录。

## SQL

None; chat loading is mocked.

无真实SQL/网络/子进程。沿原规则将确需真实subprocess的两例在offline runner中显式排除。

## 最终当前模块位置

依赖移为generation.processing、generation.builders及mining.quality.qa_quality_tools；只换import/mock目标/argv模块，业务断言不变。

## Source

`tests/mining/test_generic_mining_context.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
