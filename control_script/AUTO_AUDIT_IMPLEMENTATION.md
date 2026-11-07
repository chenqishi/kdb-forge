# 自动审核功能实现总结

## 一、实现概述

在 `control_script/timing_auto_audit_kg.py` 中实现了定期自动审核通过数据的功能。

**✨ 兼容性**：
- ✅ Elasticsearch 7.x（阿里云ES）
- ✅ AWS OpenSearch 2.x
- ✅ 自动版本检测和适配

### 核心功能

1. **自动查找待审核数据**
   - 查找ES中满足条件的文档（指定from_type_norm、insert_time超过阈值、audit_result=-1）
   - 支持按时间阈值过滤（默认24小时）

2. **智能审核规则**
   - `quality_level=high` → `audit_result=2`（审核通过）
   - `quality_level!=high` → `audit_result=0`（审核不通过）

3. **灵活的索引管理**
   - 支持单个索引审核
   - 支持多个索引批量审核
   - 支持所有索引自动获取和审核

## 二、技术实现

### 2.1 架构设计

```
timing_auto_audit_kg.py
├── AutoAuditProcessor 类（兼容ES和OpenSearch）
│   ├── __init__(): 初始化ES/OpenSearch客户端
│   ├── _detect_es_version(): 自动检测版本
│   ├── get_all_indexes(): 获取所有索引
│   ├── check_pending_audit_docs(): 检查待审核文档
│   ├── auto_audit_documents(): 自动审核单个索引
│   └── auto_audit_for_indexes(): 批量审核多个索引
└── main(): 命令行入口
```

### 2.2 核心算法

#### 时间阈值计算

```python
threshold_time = datetime.now() - timedelta(hours=hours)
# 转为字符串格式 "yyyy-MM-dd HH:mm:ss"
threshold_time_str = threshold_time.strftime("%Y-%m-%d %H:%M:%S")
```

#### 查询条件构建

```python
query = {
    "query": {
                "bool": {
                    "must": [
                        {"term": {"from_type_norm": from_type_norm}},
                        {"term": {"audit_result": -1}},
                        {"range": {"insert_time": {"lt": "2026-01-18 12:00:00"}}}
                    ]
                }
            }
        }
```

#### 分类审核

1. **高质量数据审核**（audit_result=2）
```python
high_quality_query = {
    "query": {
        "bool": {
                    "must": [
                        {"term": {"from_type_norm": from_type_norm}},
                        {"term": {"audit_result": -1}},
                        {"term": {"quality_level": "high"}},
                        {"range": {"insert_time": {"lt": "2026-01-18 12:00:00"}}}
                    ]
        }
    },
    "script": {
        "source": "ctx._source.audit_result = params.audit_result",
        "params": {"audit_result": 1}
    }
}
```

2. **其他质量数据审核**（audit_result=0）
```python
other_quality_query = {
    "query": {
        "bool": {
            "must": [...],
            "must_not": [
                {"term": {"quality_level": "high"}}
            ]
        }
    },
    "script": {
        "source": "ctx._source.audit_result = params.audit_result",
        "params": {"audit_result": 0}
    }
}
```

### 2.3 ES/OpenSearch操作方法

参考以下文件的实现：
- `knowledge_interface_tools/supply_missing_field.py`：ES客户端初始化、索引获取、批量更新
- `knowledge_interface_tools/es_search_interface.py`：ES/OpenSearch搜索和更新接口
  - `EsSearchInterfaceOri`: Elasticsearch 7.x实现
  - `EsSearchInterfaceOpen`: OpenSearch 2.x实现
  - `EsSearchInterface`: 工厂类，自动选择实现

### 2.4 版本自动检测

```python
def _detect_es_version(self) -> str:
    """自动检测ES/OpenSearch版本"""
    es_info = self.es.info()
    version_number = es_info["version"]["number"]
    distribution = es_info.get("version", {}).get("distribution", "").lower()
    
    if "opensearch" in distribution:
        return f"OpenSearch {version_number}"
    elif version_number.startswith("2."):
        return f"OpenSearch {version_number}"
    else:
        return f"Elasticsearch {version_number}"
```

## 三、创建的文件

| 文件 | 说明 | 平台支持 |
|------|------|----------|
| `timing_auto_audit_kg.py` | 主脚本，实现自动审核功能 | ES 7.x / OpenSearch 2.x |
| `AUTO_AUDIT_INDEX.md` | 文档索引 | - |
| `AUTO_AUDIT_README.md` | 详细使用文档 | ES 7.x / OpenSearch 2.x |
| `AUTO_AUDIT_QUICKSTART.md` | 快速开始指南 | ES 7.x / OpenSearch 2.x |
| `AUTO_AUDIT_CHEATSHEET.md` | 速查卡 | ES 7.x / OpenSearch 2.x |
| `AUTO_AUDIT_IMPLEMENTATION.md` | 实现总结文档（本文件） | ES 7.x / OpenSearch 2.x |
| `OPENSEARCH_COMPATIBILITY.md` | OpenSearch兼容性说明 | OpenSearch 2.x |
| `example_auto_audit.sh` | Elasticsearch使用示例脚本 | ES 7.x |
| `example_auto_audit_opensearch.sh` | OpenSearch使用示例脚本 | OpenSearch 2.x |
| `config_example_auto_audit.json` | 配置文件示例 | ES 7.x / OpenSearch 2.x |

## 四、使用方法

### 4.1 基本使用

#### Elasticsearch 7.x

```bash
# 试运行
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API" \
    --dry-run

# 正式执行
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "knowledge_qa" \
    --from-type-norm "API"
```

#### OpenSearch 2.x

```bash
# 试运行
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine_aws.json \
    --index "knowledge_qa" \
    --from-type-norm "API" \
    --dry-run

# 正式执行
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine_aws.json \
    --index "knowledge_qa" \
    --from-type-norm "API"
```

**命令完全相同，只需更换配置文件！**

### 4.2 命令行参数

| 参数 | 必需 | 默认值 | 说明 |
|------|------|--------|------|
| `--config` | ✅ | - | ES配置文件路径 |
| `--index` | ⚠️ | - | 索引名称或"all" |
| `--indexes` | ⚠️ | - | 多个索引（逗号分隔） |
| `--from-type-norm` | ✅ | - | 数据来源类型 |
| `--hours` | ❌ | 24 | 时间阈值（小时） |
| `--batch-size` | ❌ | 100 | 批处理大小 |
| `--dry-run` | ❌ | False | 试运行模式 |
| `--exclude-system` | ❌ | True | 排除系统索引 |

⚠️ 注意：`--index` 和 `--indexes` 必须指定其中一个

### 4.3 定时任务

#### Crontab配置

```bash
# 每天凌晨2点执行
0 2 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1

# 每6小时执行一次
0 */6 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

## 五、数据结构要求

### 5.1 必需字段

文档必须包含以下字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `from_type_norm` | keyword | 数据来源类型 |
| `insert_time` | text/keyword | 插入时间（字符串格式 `"yyyy-MM-dd HH:mm:ss"`） |
| `audit_result` | integer | 审核结果（-1/0/1） |
| `quality_level` | keyword | 质量等级 |

### 5.2 字段值说明

#### audit_result

| 值 | 含义 |
|----|------|
| -1 | 待审核 |
| 0 | 审核不通过 |
| 1 | 审核通过 |

#### quality_level

| 值 | 审核结果 |
|----|----------|
| high | audit_result=2 |
| medium | audit_result=0 |
| low | audit_result=0 |
| 其他 | audit_result=0 |

## 六、工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    1. 初始化ES客户端                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              2. 获取要处理的索引列表                         │
│   • 单个索引：直接使用                                       │
│   • 多个索引：解析逗号分隔的列表                            │
│   • all：调用get_all_indexes()获取所有索引                 │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│           3. 对每个索引执行以下操作                          │
├─────────────────────────────────────────────────────────────┤
│   3.1 检查索引是否存在                                      │
│   3.2 查询待审核文档数量和质量分布                          │
│   3.3 如果是dry-run模式，显示统计后跳过                     │
│   3.4 执行两次update_by_query：                             │
│       • 第一次：quality_level=high，设audit_result=2        │
│       • 第二次：quality_level!=high，设audit_result=0       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  4. 汇总并输出结果                           │
│   • 成功/失败/跳过索引数                                     │
│   • 总更新文档数                                             │
│   • 分质量等级的统计                                         │
└─────────────────────────────────────────────────────────────┘
```

## 七、错误处理

### 7.1 索引不存在

```python
if not self.es.indices.exists(index=index_name):
    # 跳过处理，记录为skipped
```

### 7.2 无待审核文档

```python
if stats['total_count'] == 0:
    # 跳过处理，记录为skipped
```

### 7.3 更新失败

```python
try:
    result = self.es.update_by_query(...)
except Exception as e:
    logging.error(f"更新失败: {str(e)}")
    # 记录为failed
```

## 八、日志记录

### 8.1 日志级别

- `INFO`：正常流程日志
- `WARNING`：警告信息
- `ERROR`：错误信息

### 8.2 关键日志

```python
logging.info(f"开始自动审核索引 {index_name}")
logging.info(f"审核quality_level=high的文档，设置audit_result=2")
logging.info(f"quality_level=high: 更新了 {high_updated} 个文档")
logging.info(f"索引 {index_name} 自动审核完成")
logging.error(f"自动审核索引 {index_name} 失败: {str(e)}")
```

## 九、性能考虑

### 9.1 批量更新

使用 `update_by_query` API，ES内部自动处理批量更新。

### 9.2 冲突处理

```python
conflicts="proceed"  # 遇到版本冲突时继续执行
```

### 9.3 刷新策略

```python
refresh=True  # 更新后立即刷新，确保数据可见
```

## 十、扩展性

### 10.1 支持新的质量等级

修改 `auto_audit_documents` 方法中的查询条件即可。

### 10.2 支持更复杂的审核规则

可以添加更多的 `update_by_query` 调用，每个调用处理不同的规则。

### 10.3 支持其他字段更新

在 `script` 部分添加更多字段的更新逻辑。

## 十一、测试建议

### 11.1 功能测试

```bash
# 1. 测试试运行模式
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index test_index --from-type-norm API --dry-run

# 2. 测试单索引审核
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index test_index --from-type-norm API

# 3. 测试多索引审核
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --indexes "test1,test2" --from-type-norm API

# 4. 测试所有索引
python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API
```

### 11.2 边界测试

- 空索引
- 无待审核文档
- 索引不存在
- 所有文档都是high质量
- 所有文档都不是high质量

### 11.3 性能测试

- 大量文档（10万+）
- 多个索引并发处理

## 十二、注意事项

1. ⚠️ **首次使用请加 `--dry-run`**：确保了解将要处理的数据
2. ⚠️ **确保ES配置正确**：包括host、用户名、密码
3. ⚠️ **确保必需字段存在**：from_type_norm、insert_time、audit_result、quality_level
4. ⚠️ **insert_time格式**：必须是字符串格式 `"yyyy-MM-dd HH:mm:ss"`
5. ⚠️ **监控执行日志**：定期检查日志确保正常运行
6. ⚠️ **备份重要数据**：执行大规模更新前建议先备份

## 十三、OpenSearch兼容性

### 13.1 兼容的API

所有使用的API在ES和OpenSearch中都是兼容的：

| API | ES 7.x | OpenSearch 2.x |
|-----|--------|----------------|
| `cat.indices` | ✅ | ✅ |
| `indices.exists` | ✅ | ✅ |
| `count` | ✅ | ✅ |
| `search` | ✅ | ✅ |
| `update_by_query` | ✅ | ✅ |
| `info` | ✅ | ✅ |

### 13.2 版本检测

脚本会自动检测ES/OpenSearch版本：

```python
es_info = self.es.info()
version_number = es_info["version"]["number"]
distribution = es_info.get("version", {}).get("distribution", "").lower()

if "opensearch" in distribution:
    # OpenSearch
    return f"OpenSearch {version_number}"
else:
    # Elasticsearch
    return f"Elasticsearch {version_number}"
```

### 13.3 查询语法

查询语法在两个平台中完全一致，包括：
- Bool查询
- Term查询
- Range查询
- Painless脚本

详细说明请参考：[OPENSEARCH_COMPATIBILITY.md](./OPENSEARCH_COMPATIBILITY.md)

## 十四、未来改进方向

1. **支持更多审核规则**：可配置化审核规则
2. **支持邮件通知**：审核完成后发送邮件通知
3. **支持审核历史记录**：记录每次审核的详细信息
4. **支持回滚功能**：审核错误时可快速回滚
5. **支持webhook通知**：集成到监控系统
6. **支持更详细的统计报表**：生成审核报表

## 十五、参考文档

### Elasticsearch文档
- ES 7.x官方文档：https://www.elastic.co/guide/en/elasticsearch/reference/7.x/
- update_by_query API：https://www.elastic.co/guide/en/elasticsearch/reference/7.x/docs-update-by-query.html
- Painless脚本语言：https://www.elastic.co/guide/en/elasticsearch/reference/7.x/modules-scripting-painless.html

### OpenSearch文档
- OpenSearch 2.x官方文档：https://opensearch.org/docs/2.x/
- update_by_query API：https://opensearch.org/docs/latest/api-reference/document-apis/update-by-query/
- Painless脚本：https://opensearch.org/docs/latest/api-reference/script-apis/

### 项目文档
- [OPENSEARCH_COMPATIBILITY.md](./OPENSEARCH_COMPATIBILITY.md) - OpenSearch兼容性详细说明

## 十六、联系方式

如有问题或建议，请联系开发团队。
