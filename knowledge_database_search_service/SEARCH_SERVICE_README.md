# 知识库搜索服务 API 文档

## 服务概述

知识库搜索服务是基于FastAPI构建的高性能搜索服务，提供知识库数据的检索和插入功能。服务运行在8003端口，支持多种搜索模式和数据类型。

**服务地址**: `http://localhost:8003`

## API 接口列表

### 1. 智能搜索接口 `/search`

**方法**: POST
**描述**: 执行智能搜索，支持语义检索和精确匹配，返回格式化的搜索结果

#### 请求参数

```json
{
  "text": "搜索关键词",
  "top_k": 1000,
  "score_threshold": -1,
  "index_names": "索引名称",
  "condition_dicts": [
    {
      "platform": "letian"
    }
  ],
  "search_type": "qa",
  "data_type": "text"
}
```

**参数说明**:
- `text` (string, 必填): 搜索文本
- `top_k` (int, 可选): 返回结果数量，默认1000
- `score_threshold` (float, 可选): 相似度阈值，默认-1（不过滤）
- `index_names` (string, 可选): 指定搜索的索引名称
- `condition_dicts` (array, 可选): 额外的过滤条件
- `search_type` (string, 可选): 搜索类型，默认"qa"
- `data_type` (string, 可选): 数据类型，默认"text"

#### 响应格式

```json
{
  "results": [
    {
      "q": "问题标题",
      "a": "答案内容",
      "content": "完整内容",
      "score": 0.95,
      "ext_info": {
        "platform": "letian",
        "from_file_name": "knowledge.txt"
      },
      "synonyms_title": "问题|同义question:相似问题",
      "metadata": {}
    }
  ]
}
```

#### cURL 示例

```bash
curl -X POST "http://localhost:8003/search" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "如何注册账户",
    "top_k": 10,
    "score_threshold": 0.7,
    "index_names": "letian",
         "condition_dicts": [
       {
         "platform": "letian"
       }
     ],
    "search_type": "qa",
    "data_type": "text"
  }'
```

### 2. Web搜索接口 `/web_search`

**方法**: POST
**描述**: 执行Web搜索，返回原始数据格式，支持分页

#### 请求参数

```json
{
  "text": "搜索关键词",
  "page_size": 10000,
  "page_num": 1,
  "index_names": "索引名称",
  "condition_dicts": [
    {
      "platform": "letian"
    }
  ]
}
```

**参数说明**:
- `text` (string, 可选): 搜索文本，默认空字符串
- `page_size` (int, 可选): 每页结果数量，默认10000
- `page_num` (int, 可选): 页码，默认1
- `index_names` (string, 可选): 指定搜索的索引名称
- `condition_dicts` (array, 可选): 过滤条件

#### 响应格式

```json
{
  "results": [
    {
      "_id": "文档ID",
      "title": "标题",
      "content": "内容",
      "platform": "平台名称",
      "score": 0.95,
      "data_type": "qa",
      "audit_result": 1,
      "insert_time": "2024-01-01 12:00:00",
      "ext_info": {
        "from_file_name": "source.txt"
      },
      "indexes": ["索引1", "索引2"],
      "tags": ["标签1", "标签2"]
    }
  ],
  "total_count": 1500,
  "current_count": 100
}
```

**响应字段说明**:
- `results` (array): 搜索结果数组，包含原始数据（已过滤embedding字段）
- `total_count` (int): 数据库中符合查询条件的总记录数
- `current_count` (int): 当前请求实际返回的数据条数

**分页说明**:
- `page_num`: 页码，从1开始
- `page_size`: 每页返回的记录数
- `total_count`: 可用于计算总页数 = ceil(total_count / page_size)
- `current_count`: 通常等于page_size，但最后一页可能少于page_size

#### cURL 示例

```bash
curl -X POST "http://localhost:8003/web_search" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "账户管理",
    "page_size": 50,
    "page_num": 1,
    "index_names": "letian,meikeduo",
         "condition_dicts": [
       {
         "data_type": "qa"
       }
     ]
  }'
```

### 3. 数据插入接口 `/insert`

**方法**: POST
**描述**: 向知识库插入新的数据记录

#### 请求参数

```json
{
  "title": "问题标题",
  "content": "答案内容",
  "data_type": "qa",
  "from_type": "chat",
  "index_names": "letian",
  "platform": "letian",
  "audit_result": -1,
  "_id": "custom_id_123",
  "ext_info": {
    "from_file_name": "manual_input.txt",
    "category": "account"
  }
}
```

**参数说明**:
- `title` (string, 必填): 数据标题
- `content` (string, 必填): 数据内容
- `data_type` (string, 可选): 数据类型，默认"qa"
- `from_type` (string, 可选): 来源类型，默认"chat"
- `index_names` (string, 必填): 目标索引名称
- `platform` (string, 必填): 平台名称
- `audit_result` (int, 可选): 审核结果，默认-1
- `_id` (string, 可选): 自定义文档ID
- `ext_info` (object, 可选): 额外信息

#### 响应格式

```json
{
  "success": true,
  "message": "数据已插入: 问题标题"
}
```

#### cURL 示例

```bash
curl -X POST "http://localhost:8003/insert" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "如何重置密码",
    "content": "1. 点击忘记密码链接 2. 输入邮箱地址 3. 查收重置邮件",
    "data_type": "qa",
    "from_type": "manual",
    "index_names": "letian",
    "platform": "letian",
    "audit_result": 1,
    "ext_info": {
      "category": "account_management",
      "priority": "high"
    }
  }'
```

### 4. 获取字段唯一值接口 `/get_unique_values`

**方法**: POST
**描述**: 获取指定索引中某个字段的所有唯一值，基于Elasticsearch聚合查询

#### 请求参数

```json
{
  "index_name": "letian",
  "field_name": "platform"
}
```

**参数说明**:
- `index_name` (string, 必填): 要查询的索引名称
- `field_name` (string, 必填): 要获取唯一值的字段名称

#### 响应格式

```json
{
  "index_name": "letian",
  "field_name": "platform", 
  "unique_values": ["letian", "amazon", "ebay"],
  "total_count": 3
}
```

**响应字段说明**:
- `index_name` (string): 查询的索引名称
- `field_name` (string): 查询的字段名称
- `unique_values` (array): 该字段的所有唯一值列表
- `total_count` (int): 唯一值的数量

#### cURL 示例

```bash
# 获取平台字段的唯一值
curl -X POST "http://localhost:8003/get_unique_values" \
  -H "Content-Type: application/json" \
  -d '{
    "index_name": "letian",
    "field_name": "platform"
  }'

# 获取数据类型的唯一值
curl -X POST "http://localhost:8003/get_unique_values" \
  -H "Content-Type: application/json" \
  -d '{
    "index_name": "open_shop",
    "field_name": "data_type"
  }'

# 获取来源类型的唯一值
curl -X POST "http://localhost:8003/get_unique_values" \
  -H "Content-Type: application/json" \
  -d '{
    "index_name": "open_shop", 
    "field_name": "from_type"
  }'

# 获取审核结果的唯一值
curl -X POST "http://localhost:8003/get_unique_values" \
  -H "Content-Type: application/json" \
  -d '{
    "index_name": "open_shop",
    "field_name": "audit_result"
  }'
```

#### 使用场景

**1. 数据分析和统计**
```bash
# 分析平台分布
curl -X POST "http://localhost:8003/get_unique_values" \
  -H "Content-Type: application/json" \
  -d '{"index_name": "open_shop", "field_name": "platform"}'
```

**2. 构建过滤器选项**
```bash
# 获取可用的数据类型，用于构建前端过滤器
curl -X POST "http://localhost:8003/get_unique_values" \
  -H "Content-Type: application/json" \
  -d '{"index_name": "letian", "field_name": "data_type"}'
```

**3. 数据质量检查**
```bash
# 检查标签字段的分布情况
curl -X POST "http://localhost:8003/get_unique_values" \
  -H "Content-Type: application/json" \
  -d '{"index_name": "open_shop", "field_name": "tags"}'
```

#### 注意事项

- 该接口基于Elasticsearch的terms聚合实现，默认最多返回10000个唯一值
- 对于大数据量的字段，建议结合其他过滤条件使用
- 支持keyword类型字段，text类型字段需要使用.keyword后缀
- 返回的唯一值列表已去重并按字典序排序

## 数据模型

### SearchResult 模型

```json
{
  "q": "问题文本",
  "a": "答案文本",
  "content": "完整内容",
  "score": 0.95,
  "ext_info": {},
  "synonyms_title": "同义词标题",
  "metadata": {}
}
```

### 过滤条件格式

```json
{
  "字段名": "字段值"
}
```

**常用过滤字段**:
- `platform`: 平台名称
- `data_type`: 数据类型
- `from_file_name`: 来源文件名
- `audit_result`: 审核状态
- `del_flag`: 删除标记（自动过滤del_flag=1的数据）

## 特殊功能

### 1. 自动del_flag过滤
所有搜索接口都会自动过滤已删除的数据（del_flag=1），无需手动指定。

### 2. 字段映射
- 使用`from_file_name`作为过滤条件时，会自动映射到`ext_info.from_file_name`

### 3. 同义词支持
搜索结果中包含`synonyms_title`字段，显示问题的同义词信息。

### 4. 重试机制
所有搜索接口都内置重试机制，最多重试3次，提高服务稳定性。

### 5. embedding字段过滤
web_search接口会自动过滤掉所有包含"embedding"关键字的字段，以减少数据传输量。

### 6. indexes字段处理
原始的indexes字段包含文本和embedding向量，在web_search返回时只保留文本部分：
```json
// 原始数据
"indexes": [
  {"text": "索引1", "embedding": [0.1, 0.2, ...]},
  {"text": "索引2", "embedding": [0.3, 0.4, ...]}
]

// 返回数据
"indexes": ["索引1", "索引2"]
```

## 错误处理

### 常见错误码

- `400 Bad Request`: 请求参数错误
  - "文本参数不能为空"
  - "index_names不能为空"
  - "检索结果错误"

### 错误响应格式

```json
{
  "detail": "错误详细信息"
}
```

## 性能建议

1. **合理设置top_k**: 避免返回过多结果影响性能
2. **使用过滤条件**: 通过condition_dicts缩小搜索范围
3. **设置相似度阈值**: 使用score_threshold过滤低质量结果
4. **指定索引名称**: 避免全局搜索，提高查询效率
5. **合理使用分页**: web_search接口建议page_size不超过1000条，避免单次返回过多数据
6. **利用total_count**: 使用返回的total_count字段计算总页数，实现前端分页显示

## 使用场景示例

### 场景1: 客服问答检索
```bash
curl -X POST "http://localhost:8003/search" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "订单退款流程",
    "top_k": 5,
    "score_threshold": 0.8,
    "index_names": "customer_service",
    "search_type": "qa"
  }'
```

### 场景2: 知识库内容管理（分页浏览）
```bash
curl -X POST "http://localhost:8003/web_search" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "",
    "page_size": 50,
    "page_num": 2,
    "index_names": "letian",
         "condition_dicts": [
       {"platform": "letian"},
       {"audit_result": 1}
     ]
  }'
```

**响应示例**:
```json
{
  "results": [...],  // 第51-100条记录
  "total_count": 300,  // 总共300条记录
  "current_count": 50  // 当前返回50条记录
}
```

### 场景3: 批量数据导入
```bash
curl -X POST "http://localhost:8003/insert" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "新功能介绍",
    "content": "详细功能说明...",
    "index_names": "product_knowledge",
    "platform": "system",
    "data_type": "document"
  }'
```

## 配置说明

服务启动时需要指定配置文件路径：
```bash
python knowledge_database_search_es.py ./config/config_for_search_index.json
```

配置文件应包含ES连接信息和其他必要参数。

## 部署说明

服务默认运行在8003端口，支持以下启动方式：

### 直接启动
```bash
cd knowledge_database_search_service/src
python knowledge_database_search_es.py ../../config/config_for_search_index.json
```

### 使用uvicorn启动
```bash
uvicorn knowledge_database_search_es:app --host 0.0.0.0 --port 8003 --reload
```

---

*本文档最后更新时间：2024年12月*

## 更新日志

### 2024年12月
- **web_search接口更新**: 支持分页功能，新增`total_count`和`current_count`返回字段
- **数据处理优化**: 自动过滤embedding字段，优化indexes字段返回格式
- **性能优化**: 新增分页相关的性能建议和使用示例