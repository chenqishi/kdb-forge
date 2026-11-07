# 自动审核脚本使用文档

## 功能说明

`timing_auto_audit_kg.py` 是一个定期自动审核ES/OpenSearch数据的工具脚本，主要功能：

**✨ 兼容性**：
- ✅ Elasticsearch 7.x（阿里云ES）
- ✅ AWS OpenSearch 2.x
- ✅ 自动检测版本并适配

1. **自动查找待审核数据**：查找满足以下条件的文档
   - 指定 `from_type_norm` 的数据
   - `insert_time` 距离当前时间超过指定小时数（默认24小时）
   - `audit_result = -1`（待审核状态）

2. **智能审核规则**：
   - 如果 `quality_level = high`，设置 `audit_result = 2`（审核通过）
   - 其他 `quality_level`，设置 `audit_result = 0`（审核不通过）

3. **灵活的索引选择**：
   - 支持单个索引
   - 支持多个索引（逗号分隔）
   - 支持所有索引（`--index all`）

## 使用方法

### 基本语法

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config <配置文件路径> \
    --index <索引名称或all> \
    --from-type-norm <数据来源类型> \
    [其他可选参数]
```

### 参数说明

| 参数 | 必需 | 说明 | 示例 |
|------|------|------|------|
| `--config` | ✅ | ES/OpenSearch配置文件路径 | `config/config_es_engine.json` (ES) 或 `config/config_es_engine_aws.json` (OpenSearch) |
| `--index` | ⚠️ | 索引名称，支持'all'获取所有索引 | `knowledge_qa` 或 `all` |
| `--indexes` | ⚠️ | 多个索引名称，用逗号分隔 | `index1,index2,index3` |
| `--from-type-norm` | ✅ | 数据来源类型，**支持多个值用逗号分隔** | `API` 或 `API,Excel,Web` |
| `--hours` | ❌ | 时间阈值（小时），默认24 | `24`, `48`, `72` |
| `--batch-size` | ❌ | 批处理大小，默认100 | `100`, `500`, `1000` |
| `--dry-run` | ❌ | 试运行模式，只检查不更新 | - |
| `--exclude-system` | ❌ | 排除系统索引（默认开启） | - |

⚠️ 注意：`--index` 和 `--indexes` 必须指定其中一个

### 使用示例

#### 1. 试运行模式（推荐先执行）

在正式执行前，先使用 `--dry-run` 查看将要处理的数据量：

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API" \
    --hours 24 \
    --dry-run
```

输出示例：
```
==========================================================
处理索引: knowledge_qa
from_type_norm: API
时间阈值: 24小时
==========================================================
待审核文档数: 1,234
quality_level分布: {'high': 456, 'medium': 567, 'low': 211}
🔍 试运行模式：将审核 1,234 个文档
```

#### 2. 审核单个索引

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API" \
    --hours 24
```

#### 3. 审核多个指定索引

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --indexes "knowledge_qa,knowledge_doc,knowledge_faq" \
    --from-type-norm "API" \
    --hours 24
```

#### 4. 审核所有索引

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "all" \
    --from-type-norm "API" \
    --hours 24 \
    --exclude-system
```

#### 5. 自定义时间阈值

审核创建时间超过48小时的数据：

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API" \
    --hours 48
```

#### 6. 不同的数据来源类型

审核Excel导入的数据：

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "all" \
    --from-type-norm "Excel" \
    --hours 24
```

#### 7. 审核多个数据来源类型

同时审核多种数据来源（用逗号分隔）：

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "all" \
    --from-type-norm "API,Excel,Web" \
    --hours 24
```

## 定时任务配置

### 使用 crontab 设置定时任务

#### 1. 编辑 crontab

```bash
crontab -e
```

#### 2. 添加定时任务

每天凌晨2点执行自动审核（审核API导入的数据）：

```bash
0 2 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

每6小时执行一次：

```bash
0 */6 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

每天早8点和晚8点执行：

```bash
0 8,20 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

#### 3. 查看已配置的定时任务

```bash
crontab -l
```

### 使用脚本方式

创建定时执行脚本 `run_auto_audit.sh`：

```bash
#!/bin/bash

# 进入项目目录
cd /path/to/knowledge_database_builder

# 配置文件路径
CONFIG_PATH="config/config_es_engine.json"

# 日志目录
LOG_DIR="log"
mkdir -p ${LOG_DIR}

# 日志文件（按日期命名）
LOG_FILE="${LOG_DIR}/auto_audit_$(date +%Y%m%d).log"

# 执行自动审核
echo "========== 开始执行自动审核 ==========" >> ${LOG_FILE}
echo "执行时间: $(date '+%Y-%m-%d %H:%M:%S')" >> ${LOG_FILE}

python3 control_script/timing_auto_audit_kg.py \
    --config ${CONFIG_PATH} \
    --index "all" \
    --from-type-norm "API" \
    --hours 24 \
    >> ${LOG_FILE} 2>&1

echo "执行完成: $(date '+%Y-%m-%d %H:%M:%S')" >> ${LOG_FILE}
echo "" >> ${LOG_FILE}
```

然后在 crontab 中调用这个脚本：

```bash
0 2 * * * /path/to/knowledge_database_builder/control_script/run_auto_audit.sh
```

## 输出说明

### 成功输出示例

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

### 错误处理

脚本会记录详细的错误日志，包括：
- 索引不存在
- ES连接失败
- 更新失败的文档

## 注意事项

1. **配置文件**：
   - **直接使用现有配置**：`config/config_es_engine.json`（Elasticsearch）或 `config/config_es_engine_aws.json`（OpenSearch）
   - **无需额外配置审核规则**：审核规则已在脚本中写死
     - `quality_level = high` → `audit_result = 2`
     - `quality_level != high` → `audit_result = 0`
2. **权限**：确保脚本有执行权限（`chmod +x timing_auto_audit_kg.py`）
3. **索引存在**：确保指定的索引存在于 ES 中
4. **字段存在**：确保文档中存在以下字段：
   - `from_type_norm`
   - `insert_time`
   - `audit_result`
   - `quality_level`
5. **时间格式**：`insert_time` 字段应为字符串格式 `"yyyy-MM-dd HH:mm:ss"`（如：`"2026-01-17 17:31:14"`）
6. **试运行**：建议先使用 `--dry-run` 模式测试
7. **日志监控**：定期检查日志文件，确保定时任务正常执行

## 审核规则说明

**审核规则已在脚本中硬编码，无需在配置文件中配置：**

| quality_level | audit_result | 说明 |
|--------------|--------------|------|
| high | 1 | 高质量数据，审核通过 |
| medium | 0 | 中等质量数据，审核不通过 |
| low | 0 | 低质量数据，审核不通过 |
| 其他 | 0 | 未知质量等级，审核不通过 |

**规则固定，不可配置修改。**

## 相关文件

- 主脚本：`control_script/timing_auto_audit_kg.py`
- 示例脚本：`control_script/example_auto_audit.sh`
- 参考实现：`knowledge_interface_tools/supply_missing_field.py`
- ES接口：`knowledge_interface_tools/es_search_interface.py`

## 技术支持

如有问题，请联系开发团队或查看相关文档。
