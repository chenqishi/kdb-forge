# 自动审核功能 - 文档索引

**✨ 兼容性**：✅ Elasticsearch 7.x  ✅ AWS OpenSearch 2.x

## 📋 快速导航

| 文档 | 大小 | 用途 | 推荐阅读顺序 |
|------|------|------|-------------|
| [AUTO_AUDIT_QUICKSTART.md](./AUTO_AUDIT_QUICKSTART.md) | 4.9K | 快速开始指南 | ⭐⭐⭐⭐⭐ 首先阅读 |
| [OPENSEARCH_COMPATIBILITY.md](./OPENSEARCH_COMPATIBILITY.md) | 8.2K | OpenSearch兼容性说明 | ⭐⭐⭐⭐⭐ OpenSearch用户必读 |
| [AUTO_AUDIT_README.md](./AUTO_AUDIT_README.md) | 7.6K | 详细使用文档 | ⭐⭐⭐⭐ 深入了解 |
| [AUTO_AUDIT_IMPLEMENTATION.md](./AUTO_AUDIT_IMPLEMENTATION.md) | 12K | 实现总结文档 | ⭐⭐⭐ 技术细节 |
| [example_auto_audit.sh](./example_auto_audit.sh) | 1.7K | 使用示例脚本 | ⭐⭐⭐⭐ 实际操作 |
| [config_example_auto_audit.json](./config_example_auto_audit.json) | 2.6K | 配置文件示例 | ⭐⭐⭐ 配置参考 |
| [timing_auto_audit_kg.py](./timing_auto_audit_kg.py) | 18K | 主程序脚本 | ⭐⭐ 源代码 |

## 🚀 快速开始（3步走）

### 1️⃣ 试运行（推荐）

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "your_index_name" \
    --from-type-norm "API" \
    --dry-run
```

### 2️⃣ 正式执行

```bash
python3 control_script/timing_auto_audit_kg.py \
    --config config/config_es_engine.json \
    --index "your_index_name" \
    --from-type-norm "API"
```

### 3️⃣ 设置定时任务

```bash
crontab -e
# 添加：每天凌晨2点执行
0 2 * * * cd /path/to/knowledge_database_builder && python3 control_script/timing_auto_audit_kg.py --config config/config_es_engine.json --index all --from-type-norm API --hours 24 >> log/auto_audit_$(date +\%Y\%m\%d).log 2>&1
```

## 📚 文档详细说明

### 🟢 AUTO_AUDIT_QUICKSTART.md（新手必读）

**适合人群**：第一次使用自动审核功能的用户（支持ES和OpenSearch）

**主要内容**：
- ✅ 功能概述
- ✅ 快速使用（3个命令搞定）
- ✅ 主要参数说明
- ✅ 定时任务配置
- ✅ 使用场景示例
- ✅ 常见问题解答

**特点**：简洁明了，10分钟上手

---

### 🔵 AUTO_AUDIT_README.md（详细手册）

**适合人群**：需要深入了解功能细节的用户

**主要内容**：
- ✅ 完整的参数说明表格
- ✅ 多种使用场景示例
- ✅ 定时任务详细配置
- ✅ 输出结果说明
- ✅ 注意事项和审核规则
- ✅ 相关文件说明

**特点**：全面详尽，涵盖所有使用场景

---

### 🟡 AUTO_AUDIT_IMPLEMENTATION.md（技术文档）

**适合人群**：开发者、需要了解实现细节的技术人员

**主要内容**：
- ✅ 技术实现架构
- ✅ 核心算法说明
- ✅ 数据结构要求
- ✅ 工作流程图
- ✅ 错误处理机制
- ✅ 性能优化考虑
- ✅ 扩展性说明
- ✅ 测试建议

**特点**：深入技术细节，适合二次开发

---

### 🟣 example_auto_audit.sh（示例脚本）

**适合人群**：希望通过实例学习的用户

**主要内容**：
- ✅ 6个典型使用场景
- ✅ 可直接执行的示例命令
- ✅ 参数组合示例

**特点**：实战导向，复制即用

---

### 🟢 OPENSEARCH_COMPATIBILITY.md（OpenSearch用户）

**适合人群**：使用AWS OpenSearch的用户

**主要内容**：
- ✅ OpenSearch兼容性说明
- ✅ 配置文件对比
- ✅ 使用示例
- ✅ 常见问题解答

**特点**：专门针对OpenSearch用户的指南

---

### 🟠 CONFIG_NOTE.md（配置说明）

**适合人群**：想了解配置文件的用户

**主要内容**：
- ✅ 直接使用现有 `config/config_es_engine.json`
- ✅ 无需额外配置审核规则
- ✅ 审核规则硬编码说明
- ✅ 如何修改规则（如有需要）

**特点**：说明为什么不需要配置审核规则

---

### 🟠 config_example_auto_audit.json（配置示例）

**适合人群**：需要参考配置格式的用户

**主要内容**：
- ✅ ES连接配置示例（最小化）

**特点**：简单的配置模板

---

### 🔴 timing_auto_audit_kg.py（源代码）

**适合人群**：开发者、需要修改功能的技术人员

**主要内容**：
- ✅ 完整的Python实现
- ✅ 类和方法定义
- ✅ 命令行参数解析
- ✅ 错误处理逻辑

**特点**：可直接执行，支持自定义修改

## 🎯 按需求选择阅读路径

### 路径1：我是新手，想快速上手（Elasticsearch）
```
1. AUTO_AUDIT_QUICKSTART.md（10分钟）
2. example_auto_audit.sh（试运行示例）
3. 完成✅
```

### 路径1-B：我是新手，使用OpenSearch
```
1. OPENSEARCH_COMPATIBILITY.md（了解兼容性）
2. AUTO_AUDIT_QUICKSTART.md（10分钟）
3. 使用config/config_es_engine_aws.json配置
4. 完成✅
```

### 路径2：我要在生产环境部署
```
1. AUTO_AUDIT_QUICKSTART.md（快速了解）
2. AUTO_AUDIT_README.md（详细了解）
3. config_example_auto_audit.json（配置ES）
4. 试运行测试
5. 设置定时任务
6. 完成✅
```

### 路径3：我要了解技术实现
```
1. AUTO_AUDIT_IMPLEMENTATION.md（架构和实现）
2. timing_auto_audit_kg.py（源代码）
3. 完成✅
```

### 路径4：我要二次开发
```
1. AUTO_AUDIT_IMPLEMENTATION.md（实现细节）
2. timing_auto_audit_kg.py（修改代码）
3. 参考：knowledge_interface_tools/supply_missing_field.py
4. 参考：knowledge_interface_tools/es_search_interface.py
5. 测试
6. 完成✅
```

## 🔗 相关参考文件

### 项目内参考

| 文件 | 说明 |
|------|------|
| `knowledge_interface_tools/supply_missing_field.py` | ES客户端初始化、索引操作参考 |
| `knowledge_interface_tools/es_search_interface.py` | ES/OpenSearch搜索和更新接口参考 |
| `knowledge_interface_tools/knowledge_tools.py` | 工具函数参考 |

### 配置文件

| 文件 | 说明 | 平台 |
|------|------|------|
| `config/config_es_engine.json` | 阿里云ES配置 | Elasticsearch 7.x |
| `config/config_es_engine_aws.json` | AWS OpenSearch配置 | OpenSearch 2.x |

## ❓ 常见场景快速查找

| 场景 | 推荐文档 | 章节 |
|------|----------|------|
| 第一次使用 | AUTO_AUDIT_QUICKSTART.md | 二、快速使用 |
| 设置定时任务 | AUTO_AUDIT_QUICKSTART.md | 四、设置定时任务 |
| 查看所有参数 | AUTO_AUDIT_README.md | 参数说明 |
| 审核规则说明 | AUTO_AUDIT_README.md | 审核规则说明 |
| 了解实现原理 | AUTO_AUDIT_IMPLEMENTATION.md | 技术实现 |
| 查看使用示例 | example_auto_audit.sh | 全部 |
| 配置ES连接 | config_example_auto_audit.json | hosts配置 |
| 报错处理 | AUTO_AUDIT_README.md | 注意事项 |
| 性能优化 | AUTO_AUDIT_IMPLEMENTATION.md | 性能考虑 |

## 📞 获取帮助

### 1. 查看命令行帮助

```bash
python3 control_script/timing_auto_audit_kg.py --help
```

### 2. 查看日志

```bash
# 查看今天的日志
tail -f log/auto_audit_$(date +%Y%m%d).log

# 查看最近的日志
ls -lt log/auto_audit_*.log | head -5
```

### 3. 阅读相关文档

按照"按需求选择阅读路径"选择合适的文档

## 🎉 开始使用

现在你已经了解了所有文档的用途，选择适合你的阅读路径，开始使用自动审核功能吧！

**推荐起点**：[AUTO_AUDIT_QUICKSTART.md](./AUTO_AUDIT_QUICKSTART.md)

---

*最后更新：2025-01-19*
