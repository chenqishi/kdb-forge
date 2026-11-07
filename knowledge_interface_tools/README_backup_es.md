# ES数据备份工具使用说明

## 概述

ES数据备份工具提供了完整的Elasticsearch索引数据备份解决方案，支持数据、mapping和settings的备份，支持多种格式和压缩选项。

## 功能特性

- ✅ 支持备份所有索引或指定索引
- ✅ 支持备份索引数据、mapping和settings
- ✅ 支持JSON和NDJSON格式
- ✅ 支持GZIP压缩
- ✅ 支持批量处理和进度显示
- ✅ 支持试运行模式
- ✅ 自动排除系统索引
- ✅ 自动排除dense_vector字段（可选）
- ✅ 详细的统计报告

## 使用方式

### 1. Shell脚本方式（推荐）

```bash
# 列出所有索引
./control_script/backup_es_data.sh --list-indexes

# 备份单个索引
./control_script/backup_es_data.sh --backup letian /data/backup

# 备份所有索引（压缩）
./control_script/backup_es_data.sh --backup-all /data/backup --compress

# 备份指定索引列表（包含mapping和settings）
./control_script/backup_es_data.sh --backup-list letian,meikeduo /data/backup --include-mapping --include-settings

# 试运行模式（查看将要备份的信息）
./control_script/backup_es_data.sh --backup-all /data/backup --dry-run

# 包含dense_vector字段的备份
./control_script/backup_es_data.sh --backup-all /data/backup --include-dense-vector
```

### 2. Python脚本方式

```bash
# 列出所有索引
python3 -m knowledge_interface_tools.backup_es_data \
    --config config/config_es_engine.json \
    --list-indexes

# 备份单个索引
python3 -m knowledge_interface_tools.backup_es_data \
    --config config/config_es_engine.json \
    --index letian \
    --backup-dir /data/backup

# 备份所有索引
python3 -m knowledge_interface_tools.backup_es_data \
    --config config/config_es_engine.json \
    --index all \
    --backup-dir /data/backup \
    --compress
```

## 参数说明

### Shell脚本参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--backup-all BACKUP_DIR` | 备份所有索引到指定目录 | `--backup-all /data/backup` |
| `--backup INDEX_NAME BACKUP_DIR` | 备份指定索引到指定目录 | `--backup letian /data/backup` |
| `--backup-list INDEX1,INDEX2 DIR` | 备份指定索引列表到目录 | `--backup-list letian,meikeduo /data/backup` |
| `--list-indexes` | 列出所有索引 | `--list-indexes` |
| `--format FORMAT` | 备份格式 (json\|ndjson) 默认: ndjson | `--format json` |
| `--batch-size SIZE` | 批处理大小，默认: 1000 | `--batch-size 2000` |
| `--include-mapping` | 包含索引mapping信息 | `--include-mapping` |
| `--include-settings` | 包含索引settings信息 | `--include-settings` |
| `--compress` | 压缩备份文件 | `--compress` |
| `--exclude-system` | 排除系统索引（默认排除） | `--exclude-system` |
| `--include-system` | 包含系统索引 | `--include-system` |
| `--exclude-dense-vector` | 排除dense_vector字段（默认排除） | `--exclude-dense-vector` |
| `--include-dense-vector` | 包含dense_vector字段 | `--include-dense-vector` |
| `--use-search-after` | 强制使用search_after API（适用于阿里云ES等） | `--use-search-after` |
| `--dry-run` | 试运行模式，只显示将要备份的信息 | `--dry-run` |

### Python脚本参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--config` | ES配置文件路径（必需） | `--config config/config_es_engine.json` |
| `--index` | 索引名称，支持'all'获取所有索引 | `--index letian` 或 `--index all` |
| `--indexes` | 多个索引名称，用逗号分隔 | `--indexes letian,meikeduo` |
| `--backup-dir` | 备份目录路径 | `--backup-dir /data/backup` |
| `--list-indexes` | 列出所有索引 | `--list-indexes` |
| `--format` | 备份格式 (json\|ndjson) 默认: ndjson | `--format json` |
| `--batch-size` | 批处理大小，默认: 1000 | `--batch-size 2000` |
| `--include-mapping` | 包含mapping信息 | `--include-mapping` |
| `--include-settings` | 包含settings信息 | `--include-settings` |
| `--compress` | 压缩备份文件 | `--compress` |
| `--exclude-system` | 排除系统索引（默认） | `--exclude-system` |
| `--exclude-dense-vector` | 排除dense_vector字段（默认） | `--exclude-dense-vector` |
| `--include-dense-vector` | 包含dense_vector字段 | `--include-dense-vector` |
| `--use-search-after` | 强制使用search_after API | `--use-search-after` |
| `--dry-run` | 试运行模式 | `--dry-run` |

## 备份文件结构

备份文件会按以下结构组织：

```
/data/backup/
├── letian/
│   ├── letian_data_20250130_143022.ndjson.gz      # 数据文件
│   ├── letian_mapping_20250130_143022.json.gz     # mapping文件
│   └── letian_settings_20250130_143022.json.gz    # settings文件
├── meikeduo/
│   ├── meikeduo_data_20250130_143025.ndjson.gz
│   ├── meikeduo_mapping_20250130_143025.json.gz
│   └── meikeduo_settings_20250130_143025.json.gz
└── ...
```

## 数据格式说明

### NDJSON格式（推荐）
每行一个JSON文档，适合大数据量的流式处理：
```json
{"_index": "letian", "_id": "1", "_source": {...}}
{"_index": "letian", "_id": "2", "_source": {...}}
```

### JSON格式
标准JSON数组格式，适合小数据量：
```json
[
  {"_index": "letian", "_id": "1", "_source": {...}},
  {"_index": "letian", "_id": "2", "_source": {...}}
]
```

## 使用场景

### 1. 日常备份
```bash
# 每日备份所有索引（压缩）
./control_script/backup_es_data.sh --backup-all /data/backup/$(date +%Y%m%d) --compress
```

### 2. 迁移前备份
```bash
# 备份指定索引的完整信息
./control_script/backup_es_data.sh --backup-list letian,meikeduo /data/migration_backup \
    --include-mapping --include-settings --compress
```

### 3. 测试环境数据备份
```bash
# 先试运行查看影响
./control_script/backup_es_data.sh --backup-all /data/test_backup --dry-run

# 确认后执行实际备份
./control_script/backup_es_data.sh --backup-all /data/test_backup --compress
```

### 4. 增量备份（通过时间戳）
```bash
# 可以结合时间戳和查询条件实现增量备份
# （需要在代码中自定义查询条件）
```

## 性能建议

1. **批处理大小**：
   - 小文档（<1KB）：使用 `--batch-size 2000`
   - 中等文档（1-10KB）：使用 `--batch-size 1000`（默认）
   - 大文档（>10KB）：使用 `--batch-size 500`

2. **压缩选项**：
   - 网络传输或存储空间有限时使用 `--compress`
   - 本地快速备份可不使用压缩

3. **并发处理**：
   - 可以并行备份不同索引以提高效率

## 错误处理

工具会自动处理常见错误：
- 网络连接中断：自动重试
- 磁盘空间不足：提前检查并报错
- 索引不存在：跳过并记录
- 权限不足：明确报错信息

## dense_vector字段处理

**默认行为**：工具默认排除所有`dense_vector`字段，因为：
- dense_vector字段通常占用大量存储空间
- 向量数据可以通过重新生成获得
- 排除这些字段可以显著减少备份文件大小和备份时间

**如需包含dense_vector字段**：
```bash
# Shell脚本方式
./control_script/backup_es_data.sh --backup-all /data/backup --include-dense-vector

# Python脚本方式
python3 -m knowledge_interface_tools.backup_es_data \
    --config config/config_es_engine.json \
    --index all \
    --backup-dir /data/backup \
    --include-dense-vector
```

## 阿里云ES兼容性

**问题**：阿里云ES某些版本不支持scroll API，会出现以下错误：
```
TransportError(410, 'serverless_unsupported_exception', 'current uri is not supported in serverless. Contact support if needed.')
```

**解决方案**：
1. **自动回退**：工具会自动检测scroll API错误并切换到search_after API
2. **手动指定**：可以使用`--use-search-after`参数强制使用search_after API

**使用示例**：
```bash
# 针对阿里云ES的备份
./control_script/backup_es_data.sh --backup-all /data/backup --use-search-after

# Python脚本方式
python3 -m knowledge_interface_tools.backup_es_data \
    --config config/config_es_engine.json \
    --index all \
    --backup-dir /data/backup \
    --use-search-after
```

## 注意事项

1. **磁盘空间**：确保备份目录有足够空间（建议预留索引大小的2-3倍，如包含dense_vector字段则需要更多空间）
2. **网络稳定性**：大数据量备份建议在网络稳定的环境下进行
3. **ES负载**：备份过程会对ES产生一定负载，建议在业务低峰期执行
4. **权限要求**：确保有读取ES索引和写入备份目录的权限
5. **dense_vector字段**：默认排除以节省空间和时间，如需要可使用`--include-dense-vector`参数
6. **阿里云ES**：如遇到scroll API不支持错误，工具会自动切换到search_after API，或可手动使用`--use-search-after`参数

## 恢复数据

备份的数据可以通过以下方式恢复：

1. **使用Elasticsearch Bulk API**恢复NDJSON格式数据
2. **使用logstash**等工具批量导入
3. **自定义脚本**解析备份文件并重新索引

## 故障排除

### 常见问题

1. **配置文件不存在**
   ```
   ❌ 配置文件不存在: config/config_es_engine.json
   ```
   解决：检查配置文件路径是否正确

2. **连接ES失败**
   ```
   ❌ 初始化ES客户端失败
   ```
   解决：检查ES服务状态和网络连接

3. **权限不足**
   ```
   ❌ 无法创建备份目录
   ```
   解决：检查备份目录的写入权限

4. **磁盘空间不足**
   ```
   ❌ 备份失败：磁盘空间不足
   ```
   解决：清理磁盘空间或更换备份目录

## 技术支持

如有问题，请检查：
1. ES服务状态
2. 配置文件格式
3. 网络连接
4. 磁盘空间
5. 日志文件中的详细错误信息 