# kdb.retrieval.maintenance.auto_audit.resolve_time_threshold

## Signature

`resolve_time_threshold(hours=None, minutes=None)`

## 概述

解析 `--hours` / `--minutes` 两个命令行参数，返回最终生效的 `(hours, minutes)` 时间阈值。
从 `main()` 中抽出为模块级纯函数，便于单测（不需要连 ES）。

## Inputs

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| hours | Optional[int] | 否 | `--hours` 的原始值，未传为 None |
| minutes | Optional[int] | 否 | `--minutes` 的原始值，未传为 None |

## Outputs

| 字段 | 类型 | 说明 |
|------|------|------|
| (hours, minutes) | Tuple[int, int] | 最终时间阈值，两段相加使用 |

## 关键逻辑

- **两者都为 None 才回落到历史默认值 `(24, 0)`**。这是本函数存在的全部理由：
  `--hours` 原先的 argparse 默认值是 24，如果保留该默认值，只传 `--minutes 10`
  会得到「24小时10分钟」，静默变成几乎不审任何新数据。所以 argparse 里两个参数的
  default 都改成了 None，由本函数统一裁决。
- 任一被显式传入时，另一个缺省按 0 处理。
- 负数抛 `ValueError`，由 `main()` 转成 `parser.error()`。

## SQL/ES Schema

不涉及。

## 测试

`tests/test_auto_audit_time_threshold.py`

## Source

`src/kdb/retrieval/maintenance/auto_audit.py`。SQL 字段依据保留在上面的 SQL 契约中；没有真实 DDL 的部分不宣称完整表结构已核验。
