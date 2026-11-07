# ES索引字段补充工具

这个工具可以自动为ES索引补充缺失的字段，包括自动添加mapping和批量更新数据。

## 功能特性

- ✅ **自动获取索引**：支持获取ES中的所有索引或指定索引
- ✅ **智能mapping管理**：自动检查并添加缺失的字段mapping
- ✅ **批量数据补充**：高效批量为缺失字段的文档添加默认值
- ✅ **安全操作**：不影响现有字段和数据
- ✅ **试运行模式**：支持dry-run模式，先检查再执行
- ✅ **详细统计**：提供完整的操作统计和结果报告

## 文件说明

- `supply_missing_field.py` - 核心Python脚本
- `supply_missing_field.sh` - 便捷的Shell脚本
- `README_supply_missing_field.md` - 使用说明文档

## 使用方法

### 1. Shell脚本方式（推荐）

```bash
# 给脚本添加执行权限
chmod +x control_script/supply_missing_field.sh

# 检查单个索引的字段覆盖情况
./control_script/supply_missing_field.sh --check letian

# 检查所有索引的字段覆盖情况
./control_script/supply_missing_field.sh --check-all

# 为单个索引补充del_flag字段（试运行）
./control_script/supply_missing_field.sh --supply letian --dry-run

# 为单个索引补充del_flag字段（实际执行）
./control_script/supply_missing_field.sh --supply letian

# 为所有索引补充del_flag字段（试运行）
./control_script/supply_missing_field.sh --supply-all --dry-run

# 为指定的多个索引补充字段
./control_script/supply_missing_field.sh --supply-list letian,meikeduo,qutian

# 补充自定义字段
./control_script/supply_missing_field.sh --supply letian --field status --value 1 --type integer

# 补充动态字段（from_type_norm和tags）
./control_script/supply_missing_field.sh --supply letian --mode dynamic --dynamic-fields from_type_norm,tags

# 只补充from_type_norm字段
./control_script/supply_missing_field.sh --supply-all --mode dynamic --dynamic-fields from_type_norm --dry-run
```

### 2. Python脚本方式

```bash
# 检查单个索引
python3 -m knowledge_interface_tools.supply_missing_field \
    --config config/config_es_engine.json \
    --index letian \
    --dry-run

# 为所有索引补充del_flag字段
python3 -m knowledge_interface_tools.supply_missing_field \
    --config config/config_es_engine.json \
    --index all \
    --field del_flag \
    --value 0 \
    --type integer

# 为指定索引列表补充字段
python3 -m knowledge_interface_tools.supply_missing_field \
    --config config/config_es_engine.json \
    --indexes letian,meikeduo,qutian \
    --field del_flag \
    --value 0
```

## 参数说明

### Shell脚本参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--check INDEX_NAME` | 检查指定索引的字段覆盖情况 | `--check letian` |
| `--check-all` | 检查所有索引的字段覆盖情况 | `--check-all` |
| `--supply INDEX_NAME` | 为指定索引补充缺失字段 | `--supply letian` |
| `--supply-all` | 为所有索引补充缺失字段 | `--supply-all` |
| `--supply-list INDEX1,INDEX2` | 为指定的多个索引补充字段 | `--supply-list letian,meikeduo` |
| `--field FIELD_NAME` | 指定字段名称（默认: del_flag） | `--field status` |
| `--value VALUE` | 设置字段默认值（默认: 0） | `--value 1` |
| `--type FIELD_TYPE` | 设置字段类型（默认: integer） | `--type keyword` |
| `--batch-size SIZE` | 设置批处理大小（默认: 1000） | `--batch-size 2000` |
| `--dry-run` | 试运行模式（只检查不更新） | `--dry-run` |
| `--include-system` | 包含系统索引（默认排除） | `--include-system` |
| `--mode MODE` | 补充模式: static(默认) 或 dynamic | `--mode dynamic` |
| `--dynamic-fields FIELDS` | 动态字段名称，用逗号分隔 | `--dynamic-fields from_type_norm,tags` |

### Python脚本参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--config` | ES配置文件路径 | 必需 |
| `--index` | 索引名称，支持'all'获取所有索引 | - |
| `--indexes` | 多个索引名称，用逗号分隔 | - |
| `--field` | 字段名称 | del_flag |
| `--value` | 字段默认值 | 0 |
| `--type` | 字段类型 | integer |
| `--batch-size` | 批处理大小 | 1000 |
| `--dry-run` | 试运行模式 | False |
| `--exclude-system` | 排除系统索引 | True |

## 支持的字段类型

### 静态字段类型
- `integer` - 整数类型
- `long` - 长整数类型
- `keyword` - 关键词类型
- `text` - 文本类型
- `boolean` - 布尔类型
- `date` - 日期类型

### 动态字段（自动计算）
- `from_type_norm` - 标准化来源类型字段
  - 通过调用`knowledge_tools.get_from_norm_type()`函数生成
  - 根据文档的`from_type`和`ext_info.from_file_name`计算规范化值
  - 类型：keyword
- `tags` - 标签字段
  - 从现有的`keywords`字段复制值
  - 如果`keywords`不存在或为空，则设置为空列表
  - 类型：keyword

## 使用场景

### 1. 为历史数据补充del_flag字段

```bash
# 首先检查所有索引的del_flag覆盖情况
./control_script/supply_missing_field.sh --check-all

# 为所有索引补充del_flag=0（试运行）
./control_script/supply_missing_field.sh --supply-all --dry-run

# 确认无误后执行实际更新
./control_script/supply_missing_field.sh --supply-all
```

### 2. 为特定索引补充状态字段

```bash
# 为letian索引补充status字段，默认值为1
./control_script/supply_missing_field.sh --supply letian --field status --value 1 --type integer
```

### 3. 批量处理多个索引

```bash
# 为指定的索引列表补充字段
./control_script/supply_missing_field.sh --supply-list letian,meikeduo,qutian --field del_flag --value 0
```

### 4. 补充动态计算字段

```bash
# 为所有索引补充from_type_norm和tags字段（试运行）
./control_script/supply_missing_field.sh --supply-all --mode dynamic --dynamic-fields from_type_norm,tags --dry-run

# 确认无误后执行实际更新
./control_script/supply_missing_field.sh --supply-all --mode dynamic --dynamic-fields from_type_norm,tags

# 只补充from_type_norm字段
./control_script/supply_missing_field.sh --supply letian --mode dynamic --dynamic-fields from_type_norm
```

## 执行流程

1. **加载配置** - 读取ES连接配置
2. **获取索引列表** - 根据参数获取要处理的索引
3. **检查mapping** - 检查字段mapping是否存在，不存在则自动添加
4. **检查覆盖情况** - 统计字段覆盖情况
5. **执行更新** - 使用update_by_query批量更新缺失字段的文档
6. **验证结果** - 验证更新结果并生成报告

## 安全特性

- **非破坏性操作**：只为缺失字段的文档添加字段，不修改现有数据
- **试运行模式**：支持dry-run模式，可以先预览操作结果
- **批量确认**：对于批量操作会要求用户确认
- **错误处理**：完善的异常处理和错误报告
- **冲突处理**：自动处理版本冲突，确保操作的稳定性

## 性能优化

- **批量处理**：使用ES的update_by_query API进行批量更新
- **可调节速率**：支持调节批处理大小和执行速率
- **索引级并发**：支持同时处理多个索引
- **内存友好**：流式处理，不会占用大量内存

## 注意事项

1. **配置文件**：确保ES配置文件存在且正确
2. **权限要求**：需要ES索引的读写权限
3. **备份建议**：重要数据建议先备份再执行
4. **网络稳定**：大批量操作需要稳定的网络连接
5. **磁盘空间**：确保ES集群有足够的磁盘空间

## 错误排查

### 常见错误

1. **配置文件不存在**
   ```
   ❌ 配置文件不存在: config/config_es_engine.json
   ```
   解决：检查配置文件路径是否正确

2. **ES连接失败**
   ```
   初始化ES客户端失败: Connection refused
   ```
   解决：检查ES服务是否启动，配置是否正确

3. **权限不足**
   ```
   添加字段mapping失败: security_exception
   ```
   解决：检查ES用户权限

4. **索引不存在**
   ```
   检查索引覆盖情况失败: index_not_found_exception
   ```
   解决：确认索引名称是否正确

## 示例输出

```
============================================================
处理索引: letian
============================================================
总文档数: 50,000
已有字段: 30,000
缺失字段: 20,000
覆盖率: 60.0%
✅ 成功更新 20,000 个文档

============================================================
批量处理总结
============================================================
总索引数: 3
成功: 3
失败: 0
跳过: 0
总更新文档数: 45,000

🎉 处理完成！
``` 