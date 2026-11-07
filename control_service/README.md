# 任务控制服务 (Task Control Service)

## 概述

这是一个用于管理后台数据挖掘任务的控制服务，提供任务启动、状态查询和监控功能。

## 功能特性

1. **任务启动** - 通过API启动后台数据挖掘任务
2. **状态查询** - 查询任务运行状态和进度
3. **自动监控** - 自动监控任务运行状态并更新数据库

## API接口

### 1. 启动任务 `/start_task`

**请求方法**: POST  
**请求格式**: JSON

#### 请求参数

##### 示例1：document_qa_mining 任务（生成QA问答对）

```json
{
    "task_type": "document_qa_mining",
    "task_info": {
        "files": [
            {
                "name": "文档名称",
                "ext": "pdf",
                "store_method": "minio",
                "address": "http://47.107.119.83:9001/browser/knowledge/document.pdf"
            }
        ],
        "index_name": "索引名称"
    }
}
```

##### 示例2：document_qa_segment_mining 任务（生成段落知识，支持分类）

```json
{
    "task_type": "document_qa_segment_mining",
    "task_info": {
        "files": [
            {
                "name": "技术文档",
                "ext": "pdf",
                "store_method": "minio",
                "address": "s3://knowledge/tech-doc.pdf"
            }
        ],
        "index_name": "tech_index",
        "category_name": "技术文档",
        "category_id": "cat_001"
    }
}
```

#### 响应格式

```json
{
    "code": 0,
    "msg": "任务启动成功",
    "data": {
        "task_id": "生成的任务ID"
    }
}
```

### 2. 查询任务信息 `/task_info`

**请求方法**: GET  
**请求参数**: task_id (查询参数)

#### 响应格式

```json
{
    "code": 0,
    "msg": "查询成功",
    "data": {
        "task_id": "任务ID",
        "task_type": "任务类型",
        "task_stage": "任务阶段",
        "task_process_rate": "进度百分比",
        "run_status": "运行状态"
    }
}
```

### 3. 停止任务 `/stop_task`

**请求方法**: POST  
**请求格式**: JSON

#### 请求参数

```json
{
    "task_id": "要停止的任务ID"
}
```

#### 响应格式

```json
{
    "code": 0,
    "msg": "任务停止成功",
    "data": {
        "task_id": "任务ID"
    }
}
```

### 4. 健康检查 `/health`

**请求方法**: GET

#### 响应格式

```json
{
    "code": 0,
    "msg": "服务正常",
    "data": {
        "timestamp": "当前时间",
        "active_tasks": "活跃任务数量"
    }
}
```

## 运行状态说明

- `run_status = 0`: 未运行
- `run_status = 1`: 异常
- `run_status = 2`: 运行中
- `run_status = 3`: 完成
- `run_status = 4`: 等待（排队中）

## 任务类型说明

### 1. document_qa_mining
生成文档问答对，适用于需要从文档中提取问题和答案的场景。

**支持的字段**：
- `files`: 文件列表（必填）
- `index_name`: 索引名称（必填）
- `client`: 客户端名称（可选）
- `need_translate`: 是否翻译（可选）

### 2. document_qa_segment_mining
生成文档段落知识，适用于需要将文档分段并提取关键信息的场景。支持分类标记。

**支持的字段**：
- `files`: 文件列表（必填）
- `index_name`: 索引名称（必填）
- `client`: 客户端名称（可选）
- `need_translate`: 是否翻译（可选）
- `category_name`: 分类名称（可选）
- `category_id`: 分类ID（可选）

**特别说明**：
- `category_name` 和 `category_id` 字段会被添加到生成的段落知识数据中
- 这些分类信息会在插入ES索引时保留，便于后续按分类检索和管理

### 3. chat_qa_mining
从聊天记录中挖掘问答对。

**支持的字段**：
- `client`: 客户端（必填）
- `user`: 用户（必填）
- `app_id`: 应用ID（必填）
- `start_time`: 开始时间（必填）
- `end_time`: 结束时间（必填）

### 4. html_qa_segment_mining
从HTML内容中生成段落知识。

## 任务阶段说明

- "排队中": 任务已创建，等待执行
- "运行中": 任务正在执行
- "运行完成": 任务成功完成
- "运行错误": 任务执行失败
- "启动失败": 任务启动失败

## 启动服务

### 基本启动

```bash
cd control_service
python off_task_control_service.py
```

### 带参数启动

```bash
# 指定脚本基础目录
python off_task_control_service.py --script-dir /path/to/your/project

# 指定端口和监听地址
python off_task_control_service.py --host 127.0.0.1 --port 8080

# 组合使用
python off_task_control_service.py --script-dir /home/user/projects --host 0.0.0.0 --port 5001
```

### 命令行参数

- `--script-dir`: 脚本基础目录路径，默认使用服务脚本所在目录的上级目录
- `--host`: 服务监听地址，默认为 `0.0.0.0`
- `--port`: 服务端口号，默认为 `5000`

### 脚本路径说明

当指定`--script-dir`参数时，服务会在以下路径查找挖掘脚本：
```
{script-dir}/control_service/document_qa_mining_task_control.py
```

例如：
- 如果`--script-dir=/home/user/myproject`
- 则脚本路径为：`/home/user/myproject/control_service/document_qa_mining_task_control.py`

如果不指定`--script-dir`，则使用默认路径（服务脚本上级目录）。

## 数据库配置

服务使用MySQL数据库存储任务信息，需要确保：

1. 配置文件 `{script-dir}/config/mysql_conn_config.json` 存在且正确
   - 如果指定了`--script-dir`，则使用`{script-dir}/config/mysql_conn_config.json`
   - 如果未指定，则使用默认路径`../config/mysql_conn_config.json`
2. 数据库中存在 `rufitai.task_kggen_info` 表

### 配置文件示例

```json
{
  "host": "your_mysql_host",
  "database": "rufitai",
  "user": "your_username",
  "password": "your_password"
}
```

## 注意事项

1. 服务会启动真实的`{script-dir}/control_service/document_qa_mining_task_control.py`脚本来处理任务
2. 任务监控系统会实时检查进程状态，根据进程退出码判断任务成功或失败
3. 支持任务手动停止，会优雅终止进程（3秒后强制终止）
4. 服务包含自动监控线程，每10秒检查一次任务状态并更新数据库
5. 任务ID基于task_type+task_info+timestamp生成MD5，允许同一任务重启
6. 配置文件路径和脚本路径都基于`--script-dir`参数或默认路径

## document_qa_mining_task_control.py 脚本详细说明

### 概述

`document_qa_mining_task_control.py` 是文档QA挖掘任务的执行脚本，基于原始的`platform_knowledge_generate_from_raw_document.sh`脚本改造而成，支持从远程文件系统（如MinIO）下载文档并生成问答对。

### 脚本功能

该脚本将整个文档处理流程分为7个主要阶段：

#### 阶段1：文件下载 (file_download)
- 支持从MinIO等S3兼容的存储系统下载文件
- 根据`task_info`中的`files`数组下载文件到本地
- 生成文件映射：`{platform}\t{file_name}\t{file_ext}\t{local_path}`
- 支持多种地址格式：HTTP URL、S3 URL等

#### 阶段2：文件解析 (document_parse)
- 使用`knowledge_clear_tool/wordtotext.py`解析文档
- 支持PDF、DOCX、DOC格式（DOCX/DOC先转换为PDF）
- 生成JSON格式的文档内容
- 输出映射：`{platform}\t{file_name}\t{file_path}\t{content_json_path}`

#### 阶段3：文本翻译 (document_translate)
- 可选阶段，仅当`task_info.need_translate=1`时执行
- 使用`knowledge_clear_tool/knowledge_translate_by_dify.py`进行翻译
- 保持原有的文件映射格式

#### 阶段4：QA生成 (qa_generation)
- 使用`knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py`生成问答对
- 自动处理文件名字段映射问题
- 生成包含问题、答案和元数据的QA对

#### 阶段5：QA质量处理 (qa_quality)
- 使用`quality_tools/qa_quality_tools.py`进行质量评估
- 提高QA对的质量和一致性

#### 阶段6：ES Schema转换 (schema_transform)
- 使用`commons/schema_trans.py`转换为搜索引擎格式
- 准备数据用于索引插入

#### 阶段7：ES插入索引 (index_insert)
- 使用`knowledge_interface_tools/search_index_data_interface.py`插入数据
- 将处理后的QA对存储到Elasticsearch索引中

### 配置文件要求

#### MinIO配置 (`config/minio_config.json`)
```json
{
    "endpoint_url": "http://your-minio-server:9000",
    "access_key": "your_access_key",
    "secret_key": "your_secret_key",
    "region": "us-east-1",
    "bucket_name": "knowledge-files"
}
```

#### 索引配置 (`config/{index_name}_config.json`)
脚本会根据`task_info.index_name`查找对应的索引配置文件。

### 文件名映射解决方案

为解决原始流程中的文件名映射问题，脚本采用了以下策略：

1. **批量处理**：将所有文件放入一个批量处理列表
2. **映射维护**：维护文件路径到文件信息的映射关系
3. **结果重组**：根据原始文件信息重新组织处理结果
4. **字段对齐**：确保后续阶段能正确识别文件名字段位置

### 输入参数

脚本接收以下命令行参数：
- `--script-dir`: 脚本根目录路径
- `--task-id`: 任务ID
- `--task-info`: 任务信息JSON字符串

### 任务信息格式

```json
{
    "files": [
        {
            "name": "文档名称",
            "ext": "pdf",
            "store_method": "minio", 
            "address": "s3://bucket/path/to/file.pdf"
        }
    ],
    "index_name": "目标索引名称",
    "client": "客户端名称（可选）",
    "need_translate": 0,
    "category_name": "分类名称（可选）",
    "category_id": "分类ID（可选）"
}
```

**字段说明**：
- `files`: 必填，要处理的文件列表
- `index_name`: 必填，目标索引名称
- `client`: 可选，客户端名称，默认使用index_name
- `need_translate`: 可选，是否需要翻译，0=不翻译，1=翻译，默认为0
- `category_name`: 可选，分类名称，用于标记生成的段落知识所属分类
- `category_id`: 可选，分类ID，用于标记生成的段落知识所属分类

**注意**：`category_name` 和 `category_id` 仅对 `document_qa_segment_mining` 任务类型有效，会被添加到生成的段落知识数据中，并在插入ES索引时保留。

### 日志和监控

- 每个阶段都会更新数据库中的`task_stage`字段
- 所有日志保存在`data/{task_id}/log/`目录下
- 中间文件保存在`data/{task_id}/`目录下
- 任务完成时`run_status`设为3，出错时设为1

### 依赖的工具模块

脚本依赖以下自定义工具：
- `off_task_tools/minio_downloader.py` - MinIO文件下载器
- `off_task_tools/task_status_updater.py` - 任务状态更新器

以及项目中已有的处理模块：
- `knowledge_clear_tool/wordtotext.py`
- `knowledge_clear_tool/knowledge_translate_by_dify.py`
- `knowledge_clear_tool/knowledge_clear_by_dify_model_longcontent.py`
- `quality_tools/qa_quality_tools.py`
- `commons/schema_trans.py`
- `knowledge_interface_tools/search_index_data_interface.py`

### 错误处理

- 每个阶段都有独立的错误处理机制
- 失败时会记录详细的错误日志
- 自动更新数据库状态为错误状态
- 支持中断时的清理操作

## 扩展说明

服务已经集成了真实的进程管理功能，会启动`{script-dir}/control_service/document_qa_mining_task_control.py`脚本。

要实现具体的挖掘脚本，需要创建该脚本并确保：

### 1. 脚本接口
脚本应接受一个JSON字符串参数（task_info）
```bash
python document_qa_mining_task_control.py '{"files": [...], "index_name": "..."}'
```

### 2. 退出码
脚本应正确设置退出码
- 成功: `sys.exit(0)`
- 失败: `sys.exit(1)` 或其他非零值

### 3. 基本结构示例
```python
#!/usr/bin/env python
import sys
import json
import logging

def main():
    try:
        if len(sys.argv) < 2:
            logging.error("缺少任务信息参数")
            return 1
        
        task_info = json.loads(sys.argv[1])
        files = task_info.get('files', [])
        index_name = task_info.get('index_name', '')
        
        # 处理文档挖掘逻辑
        # ... 
        
        logging.info("任务完成")
        return 0
        
    except Exception as e:
        logging.error(f"任务执行失败: {e}")
        return 1

if __name__ == '__main__':
    exit_code = main()
    sys.exit(exit_code)
```

### 4. 工作目录
脚本会在`{script-dir}/control_service/`目录下执行
/。 。；咯9iu好
### 5. 依赖路径
脚本可以使用相对路径访问项目内的其他模块和配置文件

## 测试服务

### 使用测试脚本

项目提供了测试脚本 `test_service.py` 来演示API的使用：

```bash
# 确保服务正在运行
python off_task_control_service.py &

# 运行测试
python test_service.py
```

### 手动测试API

#### 1. 启动任务
```bash
curl -X POST http://localhost:5000/start_task \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "document_qa_mining",
    "task_info": {
      "files": [
        {
          "name": "测试文档",
          "ext": "txt", 
          "store_method": "minio",
          "address": "http://example.com/test.txt"
        }
      ],
      "index_name": "test_index"
    }
  }'
```

#### 2. 查询任务状态
```bash
curl "http://localhost:5000/task_info?task_id=YOUR_TASK_ID"
```

#### 3. 停止任务
```bash
curl -X POST http://localhost:5000/stop_task \
  -H "Content-Type: application/json" \
  -d '{"task_id": "YOUR_TASK_ID"}'
```

#### 4. 健康检查
```bash
curl http://localhost:5000/health
```

## 常见问题

### Q: 服务启动时提示脚本目录不存在
A: 检查 `--script-dir` 参数是否正确，确保目录下存在 `control_service` 子目录

### Q: 数据库连接失败
A: 检查 MySQL 配置文件路径和内容是否正确，确保数据库服务正在运行

### Q: 任务启动失败
A: 检查挖掘脚本是否存在并有执行权限，查看日志获取详细错误信息

### Q: 任务状态一直显示运行中
A: 检查挖掘脚本是否正确设置了退出码，确保脚本能够正常结束