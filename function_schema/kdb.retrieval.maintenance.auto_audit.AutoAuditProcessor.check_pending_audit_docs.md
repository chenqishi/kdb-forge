# kdb.retrieval.maintenance.auto_audit.AutoAuditProcessor.check_pending_audit_docs

## Signature

`check_pending_audit_docs(self, index_name: str, from_type_norm: List[str], hours: int=24, minutes: int=0) -> Dict[str, Any]`

## 概述

检查指定索引中待审核文档的数量和 quality_level 分布。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| index_name | str | 是 | ES/OpenSearch 索引名称 |
| from_type_norm | List[str] | 是 | 数据来源类型列表 |
| hours | int | 否 | 时间阈值（小时），默认24 |
| minutes | int | 否 | 时间阈值（分钟），与 hours 相加，默认0 |

## Outputs

| 字段 | 类型 | 说明 |
|------|------|------|
| index_name | str | 索引名称 |
| from_type_norm | List[str] | 数据来源类型 |
| total_count | int | 待审核文档总数 |
| quality_distribution | Dict[str, int] | quality_level 分布统计 |
| threshold_hours | int | 时间阈值（小时部分） |
| threshold_minutes | int | 时间阈值（分钟部分） |
| threshold_desc | str | 人类可读的时间窗口，如 `10分钟` / `1小时30分钟` |
| threshold_time | str | 阈值具体时间 |

## SQL/ES Schema

### 查询条件
- `from_type_norm`: term/terms 匹配
- `audit_result`: term 匹配 `-1`
- `insert_time`: range 条件，使用 `lte`（小于等于 threshold_time），仅统计超过指定时间阈值的旧数据
- 聚合：按 `quality_level` 分桶统计

### 关键逻辑
- threshold_time = datetime.now() - timedelta(hours=hours, minutes=minutes)

## Source

`src/kdb/retrieval/maintenance/auto_audit.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
