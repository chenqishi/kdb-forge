# timing_auto_audit_kg.format_time_window

## 概述
把 `hours` / `minutes` 组合成人类可读的时间窗口描述，用于日志和控制台打印。

## Inputs
| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| hours | int | 否 | 小时部分，默认0 |
| minutes | int | 否 | 分钟部分，默认0 |

## Outputs
| 字段 | 类型 | 说明 |
|------|------|------|
| 返回值 | str | 如 `24小时` / `10分钟` / `1小时30分钟`；两者都为0时返回 `0（不设延迟，审核全部待审文档）` |

## 关键逻辑
- 两者都为 0 时不能只打印 "0小时"，那会让人以为参数没生效；显式说明这是「不设延迟」。

## SQL/ES Schema
不涉及。

## 测试
`tests/test_auto_audit_time_threshold.py`
