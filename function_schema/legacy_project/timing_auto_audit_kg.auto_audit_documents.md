# timing_auto_audit_kg.auto_audit_documents

> 2026-10-19：现行统一接口实现见 [timing_auto_audit_kg.AutoAuditProcessor.auto_audit_documents.md](timing_auto_audit_kg.AutoAuditProcessor.auto_audit_documents.md)；下面保留历史行为记录。统计输出新增分支计数/固定阈值，部分失败和冲突不再记为成功。

## 概述
自动审核 ES/OpenSearch 索引中满足条件的文档，根据 `quality_level` 设置不同的 `audit_result` 值。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| index_name | str | 是 | ES/OpenSearch 索引名称 |
| from_type_norm | List[str] | 是 | 数据来源类型列表，如 `["document", "html"]` |
| hours | int | 否 | 时间阈值小时数，默认 24 |
| minutes | int | 否 | 时间阈值分钟数，默认 0 |
| batch_size | int | 否 | 保留兼容参数，当前主路径由 ES `_update_by_query` + `scroll_size` 控制写入批次 |
| scroll_size | int | 否 | `_update_by_query` 内部 scroll/bulk 批次大小，默认 30 |
| dry_run | bool | 否 | 试运行模式，仅统计不更新 |

## Outputs
| 字段 | 类型 | 说明 |
|------|------|------|
| index_name | str | 处理的索引名称 |
| from_type_norm | List[str] | 数据来源类型 |
| threshold_hours | int | 时间阈值小时部分 |
| threshold_minutes | int | 时间阈值分钟部分 |
| threshold_desc | str | 人类可读的时间窗口 |
| threshold_time | str | 阈值具体时间，格式 `YYYY-MM-DD HH:MM:SS` |
| high_quality.updated | int | `quality_level=high` 更新数量 |
| high_quality.failures | list | high 分支 ES 失败列表 |
| other_quality.updated | int | 非 high 分支更新数量 |
| other_quality.failures | list | 非 high 分支 ES 失败列表 |
| total_updated | int | 总更新数量 |
| total_failures | int | 总失败数量 |

## SQL/ES Schema
### 查询条件
- `from_type_norm`: `term` / `terms` 匹配。
- `audit_result`: `term` 匹配 `-1`。
- `insert_time`: `range lte threshold_time`，只审核达到时间窗口的数据。
- `quality_level`: high 分支匹配 `"high"`；非 high 分支排除 `"high"`。
- `data_type`: 非 high 分支排除 `"segment"`。

### 写入字段
- `quality_level=high` → `audit_result=2`。
- `quality_level!=high` 且 `data_type!=segment` → `audit_result=0`。

## 关键逻辑
- 先统计待审核数量和质量分布。
- 正式执行时通过 `_run_update_by_query` 更新；该函数使用 `scroll_size` 控制 ES 内部 bulk 批次，并拉长同步请求超时时间。
