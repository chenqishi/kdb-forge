# 自动审核功能 - 速查卡

**✨ 兼容性**：✅ Elasticsearch 7.x  ✅ AWS OpenSearch 2.x

## ⚡ 一行命令

```bash
# 试运行（安全）- Elasticsearch
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --dry-run

# 试运行（安全）- OpenSearch
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine_aws.json --index all --from-type-norm API --dry-run

# 正式执行 - Elasticsearch
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API

# 正式执行 - OpenSearch
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine_aws.json --index all --from-type-norm API
```

## 📝 必需参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--config` | ES/OpenSearch配置 | `config/config_es_engine.json` (ES) 或 `config/config_es_engine_aws.json` (OpenSearch) |
| `--index` | 索引名（或all） | `knowledge_qa` / `all` |
| `--from-type-norm` | 数据来源（支持多值） | `API` / `API,Excel,Web` |

## 🎛️ 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--hours` | 24 | 时间阈值（小时），与 `--minutes` 相加 |
| `--minutes` | 0 | 时间阈值（分钟），与 `--hours` 相加。两者都不传才用默认 24 小时 |
| `--batch-size` | 100 | 批处理大小 |
| `--dry-run` | - | 仅查看不更新 |

## 🎯 审核规则（硬编码）

```
quality_level = high  → audit_result = 2 ✅
quality_level ≠ high  → audit_result = 0 ❌
```

**规则固定在脚本中，无需配置文件配置**

> ⚠️ 值的口径：脚本给 high 写的是 **2**，不是 1（历史文档和汇总文案曾误写成 1，已于 2026-08-20 修正）。
> 影响上真正重要的是 **0 是唯一会被默认检索排除的值**——检索侧默认条件是 `audit_result ∈ [1, 2, -1]`。
> 另注意旧的管理 API 文档写的是「1=通过 / 2=不通过」，与本脚本的 high→2 口径不一致，改动前先确认调用方怎么解读。

## ⏰ 定时任务

```bash
# 每天2点
0 2 * * * cd /path/to/project && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1

# 每6小时
0 */6 * * * cd /path/to/project && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

## 📋 常用命令

```bash
# 单索引
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index knowledge_qa --from-type-norm API

# 多索引
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --indexes "idx1,idx2,idx3" --from-type-norm API

# 所有索引
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API

# 多个数据来源类型（用逗号分隔）
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm "API,Excel,Web"

# 10分钟阈值（新知识入库满10分钟就审，wayfair 在用）
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index wayfair --from-type-norm "document,html" --minutes 10

# 48小时阈值
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 48

# 查看帮助
python3 control_script/timing_auto_audit_kg.py --help
```

## 🔍 查看日志

```bash
# 实时查看
tail -f log/auto_audit_$(date +%Y%m%d).log

# 查看最新
tail -100 log/auto_audit_$(date +%Y%m%d).log
```

## ⚠️ 注意事项

1. ✅ 首次使用加 `--dry-run`
2. ✅ 直接使用现有ES配置文件，无需额外配置
3. ✅ 审核规则已在代码中固定，不可修改
4. ✅ insert_time为字符串格式 `"yyyy-MM-dd HH:mm:ss"`
5. ✅ 必需字段：from_type_norm, insert_time, audit_result, quality_level

## 📖 完整文档

→ [AUTO_AUDIT_INDEX.md](./AUTO_AUDIT_INDEX.md)
