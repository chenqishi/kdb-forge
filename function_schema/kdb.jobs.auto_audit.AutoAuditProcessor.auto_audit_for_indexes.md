# kdb.jobs.auto_audit.AutoAuditProcessor.auto_audit_for_indexes

## Signature

`AutoAuditProcessor.auto_audit_for_indexes(self, index_names: List[str], from_type_norm: List[str], hours: int=24, minutes: int=0, batch_size: int=50, scroll_size: int=30, dry_run: bool=False) -> Dict[str, Any]`

## 概述

为多个索引批量执行自动审核，逐索引打印进度并汇总结果。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| index_names | List[str] | 是 | 索引名称列表 |
| from_type_norm | List[str] | 是 | 数据来源类型列表，如 ["document", "html"] |
| hours | int | 否 | 时间阈值（小时），默认24 |
| minutes | int | 否 | 时间阈值（分钟），与 hours 相加，默认0 |
| batch_size | int | 否 | 批处理大小，默认50 |
| scroll_size | int | 否 | update_by_query 内部 scroll 批次大小，默认30 |
| dry_run | bool | 否 | 试运行模式，默认 False |

## Outputs

| 字段 | 类型 | 说明 |
|------|------|------|
| results | Dict[str, Any] | 每个索引的处理结果（status: success/skipped/dry_run/failed） |
| summary | Dict[str, int] | 总索引数、成功/失败/跳过数、累计更新数 |

## 关键逻辑

- 索引不存在 → skipped(index_not_exists)；待审 0 条 → skipped(no_pending_docs)。
- `hours` / `minutes` 原样透传给 `check_pending_audit_docs` 和 `auto_audit_documents`，
  三者必须一致，否则「统计出的待审数」和「实际审核数」会对不上。

## SQL/ES Schema

见 `timing_auto_audit_kg.auto_audit_documents.md`。

## Source

`src/kdb/jobs/auto_audit.py`。SQL 表/字段来自本契约已记录的真实结构资料或该实现中的查询；未附真实 DDL 的部分仅表示代码使用范围，不能视为已验证的完整表结构。
