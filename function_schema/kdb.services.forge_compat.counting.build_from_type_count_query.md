# kdb.services.forge_compat.counting.build_from_type_count_query

## Signature

`build_from_type_count_query(from_type: str='chat_auto', start: Optional[str]=None, end: Optional[str]=None) -> Dict[str, Any]`

## Inputs

`from_type="chat_auto"`、`start=None`、`end=None`，来源及各时间先校验。

## Outputs

原生 bool/filter DSL：`quality_level=high` 与原始 `from_type` 两个 term。
仅 start/end 均不为 None 时加入 insert_time 的 gte/lte 闭区间；有效单边时间忽略。
倒序区间保留交由 ES 自然返回 0。
不加入 del_flag、audit_result、data_type、category 或 from_type_norm。

## SQL

无；纯本地构造 DSL，无 ES 请求。

## Source

`src/kdb/services/forge_compat/counting.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
