# Knowledge Database Builder

知识库构建器项目，用于构建和管理知识检索系统。

## 项目结构

- `knowledge_database_search_service/` - 知识库搜索服务
- `knowledge_interface_tools/` - 知识接口工具
- `knowledge_clear_tool/` - 知识清理工具
- `knowledge_crawler_tool/` - 知识爬虫工具
- `knowledge_generate/` - 知识生成工具

## API 文档

详细的API接口文档请参考：[knowledge_database_search_service/API_DOCUMENTATION.md](knowledge_database_search_service/API_DOCUMENTATION.md)

### 主要接口

- **POST /search** - 普通搜索接口，用于智能问答
- **POST /web_search** - Web搜索接口，支持分页，用于数据展示
- **POST /insert** - 数据插入接口

### 最新更新

web_search接口现在支持分页功能，返回结果包含：
- `total_count`: 总记录数
- `current_count`: 当前返回的数据数量
- `results`: 搜索结果（已过滤embedding字段）

## 使用说明

### 启动搜索服务

```bash
cd knowledge_database_search_service/src
python knowledge_database_search_es.py config_path
```

### 配置文件

服务需要配置文件来指定ES连接信息、embedding服务等配置。

## 依赖

- Python 3.9+
- Elasticsearch 7.x
- FastAPI
- libreoffice 用于转换office: yum install libreoffice -y, aws 该方法比较难装，使用本地rpm方式
- 其他依赖见各模块的requirements文件
