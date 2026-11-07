# 自动审核脚本 - 快速开始

## 一、功能概述

自动审核ES/OpenSearch中满足以下条件的文档：
- ✅ **兼容性**：支持 Elasticsearch 7.x 和 AWS OpenSearch 2.x
- ✅ 指定 `from_type_norm` 的数据
- ✅ `insert_time` 超过24小时（可配置）
- ✅ `audit_result = -1`（待审核状态）

**审核规则**：
- `quality_level = high` → `audit_result = 2` ✅ 审核通过
- `quality_level != high` → `audit_result = 0` ❌ 审核不通过

## 二、快速使用

**📌 配置说明**：直接使用现有的 `config/config_es_engine.json`，无需额外配置审核规则！

### 1. 试运行（推荐第一次使用）

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API" \
    --dry-run
```

### 2. 正式执行

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API"
```

### 3. 审核所有索引

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "all" \
    --from-type-norm "API"
```

## 三、主要参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--config` | ES/OpenSearch配置文件（必需） | `config/config_es_engine.json` 或 `config/config_es_engine_aws.json` |
| `--index` | 索引名称或"all" | `knowledge_qa` 或 `all` |
| `--from-type-norm` | 数据来源类型（必需），支持多个值用逗号分隔 | `API` 或 `API,Excel,Web` |
| `--hours` | 时间阈值（小时），与 `--minutes` 相加，两者都不传时默认24 | `24`, `48`, `72` |
| `--minutes` | 时间阈值（分钟），与 `--hours` 相加 | `10`（入库满10分钟即审） |
| `--dry-run` | 试运行，不实际更新 | - |

## 四、设置定时任务

### 每天凌晨2点自动执行

```bash
# 编辑crontab
crontab -e

# 添加以下行
0 2 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

### 每6小时执行一次

```bash
0 */6 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

## 五、使用场景示例

### 场景1: 审核API导入的数据

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "all" \
    --from-type-norm "API" \
    --hours 24
```

### 场景2: 审核Excel导入的数据

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "all" \
    --from-type-norm "Excel" \
    --hours 24
```

### 场景3: 审核特定索引（48小时阈值）

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API" \
    --hours 48
```

### 场景4: 审核多个索引

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --indexes "knowledge_qa,knowledge_doc,knowledge_faq" \
    --from-type-norm "API" \
    --hours 24
```

### 场景5: 审核多个数据来源类型

```bash
# 同时审核API、Excel、Web三种来源的数据
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "all" \
    --from-type-norm "API,Excel,Web" \
    --hours 24
```

## 六、输出示例

```
==========================================================
处理索引: knowledge_qa
from_type_norm: API
时间阈值: 24小时
==========================================================
待审核文档数: 1,234
quality_level分布: {'high': 456, 'medium': 567, 'low': 211}
✅ 成功审核 1,234 个文档
   - quality_level=high: 456 个
   - quality_level!=high: 778 个

==========================================================
批量自动审核总结
==========================================================
总索引数: 1
成功: 1
失败: 0
跳过: 0
总审核文档数: 1,234
  - quality_level=high (audit_result=2): 456
  - quality_level!=high (audit_result=0): 778

🎉 处理完成！
```

## 七、注意事项

1. ⚠️ **首次使用请加 `--dry-run` 参数**，确认数据无误后再正式执行
2. ⚠️ **确保ES配置文件路径正确**
3. ⚠️ **确保文档中存在必需字段**：`from_type_norm`, `insert_time`, `audit_result`, `quality_level`
4. ⚠️ **insert_time应为字符串格式** `"yyyy-MM-dd HH:mm:ss"`（如：`"2026-01-17 17:31:14"`）
5. ⚠️ **建议设置日志文件**，便于追踪执行情况

## 八、常见问题

### Q1: 如何查看有哪些from_type_norm值？

可以先在Kibana或直接查询ES查看现有的from_type_norm值。

### Q2: 如何确认审核是否成功？

在ES中查询文档的audit_result字段，确认是否已更新为0或1。

### Q3: 如何回滚审核结果？

可以使用ES的update_by_query API手动将audit_result改回-1。

### Q4: 脚本执行失败怎么办？

检查：
1. ES配置文件是否正确
2. ES服务是否可访问
3. 索引是否存在
4. 必需字段是否存在（from_type_norm, insert_time, audit_result, quality_level）

## 九、相关文档

- 详细文档：[AUTO_AUDIT_README.md](./AUTO_AUDIT_README.md)
- 示例脚本：[example_auto_audit.sh](./example_auto_audit.sh)
- 主脚本：[timing_auto_audit_kg.py](./timing_auto_audit_kg.py)

## 十、查看帮助

```bash
python3 control_script/timing_auto_audit_kg.py --help
```
