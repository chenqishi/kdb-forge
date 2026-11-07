# Excel QA数据上传任务说明

## 任务概述

`excel_qa_segment_upload` 任务用于从远程存储（如MinIO）下载审核后的Excel文件，并将其中的QA数据上传到搜索索引中。

这是对原始脚本 `control_script/insert_audit_excel.sh` 的远程任务改造。

## 任务流程

1. **文件下载**: 从MinIO等远程存储下载Excel文件
2. **Excel转JSON**: 将Excel文件转换为JSON格式（category信息在此阶段处理）
3. **插入索引**: 将处理后的数据插入到搜索索引

## 任务参数格式

```json
{
    "task_type": "excel_qa_segment_upload",
    "task_info": {
        "category_name": "广告-家具",
        "category_id": "2004013449381801986",
        "files": [
            {
                "ext": "xlsx",
                "store_method": "minio",
                "address": "rufit_demo/20250925/1971085389470494722.xlsx",
                "bucket_name": "boot-admin",
                "name": "谷歌家居园艺类全渠道广告策略手册"
            }
        ],
        "client": "customer_platform",
        "index_name": "customer_platform_admin"
    }
}
```

## 参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| category_name | string | 可选 | 类目名称，如"广告-家具" |
| category_id | string/number | 可选 | 类目ID |
| files | array | 必填 | 文件列表（仅处理第一个文件） |
| files[].ext | string | 必填 | 文件扩展名，如"xlsx" |
| files[].store_method | string | 必填 | 存储方式，如"minio" |
| files[].address | string | 必填 | 文件在存储中的地址 |
| files[].bucket_name | string | 可选 | 存储桶名称 |
| files[].name | string | 必填 | 文件名称 |
| client | string | 必填 | 客户标识 |
| index_name | string | 必填 | 搜索索引名称 |

## Excel文件格式要求

Excel文件应该包含以下列（参考审核后的格式）：

- **平台**: 平台标识（可选）
- **问题**: 问题内容
- **答案**: 答案内容
- **synonyms_title**: 同义标题，用"|"分隔
- **supply_info_query**: 补充查询信息，用"|"分隔

## API调用示例

### 启动任务

```bash
curl -X POST http://localhost:6000/start_task \
  -H "Content-Type: application/json" \
  -d '{
    "task_type": "excel_qa_segment_upload",
    "task_info": {
        "category_name": "广告-家具",
        "category_id": "2004013449381801986",
        "files": [
            {
                "ext": "xlsx",
                "store_method": "minio",
                "address": "rufit_demo/20250925/1971085389470494722.xlsx",
                "bucket_name": "boot-admin",
                "name": "谷歌家居园艺类全渠道广告策略手册"
            }
        ],
        "client": "customer_platform",
        "index_name": "customer_platform_admin"
    }
}'
```

### 查询任务状态

```bash
curl -X POST http://localhost:6000/task_info \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "<task_id>"
}'
```

### 停止任务

```bash
curl -X POST http://localhost:6000/stop_task \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "<task_id>"
}'
```

## 任务状态

- **0**: 未运行
- **1**: 异常
- **2**: 运行中
- **3**: 完成
- **4**: 排队中

## 任务阶段

- **file_download**: 文件下载
- **excel_to_json**: Excel转JSON（包含category信息处理）
- **index_insert**: 插入索引

## 日志文件

- 任务日志: `log/off_task/<task_id>.log`
- 阶段日志: `log/off_task_log/<task_id>/<stage_name>.log`
- 数据文件: `data/off_task_data/<task_id>/`

## 输出结果

任务完成后，会在任务信息中包含结果统计：

```json
{
    "task_result": {
        "upload_count": 100
    }
}
```

## 资源配置

该任务默认占用1个并发资源单位。可以在 `config/task_resource_config.json` 中调整：

```json
{
    "task_resource_usage": {
        "excel_qa_segment_upload": 1
    }
}
```

## 依赖文件

- `commons/schema_trans.py`: Excel转JSON转换
- `knowledge_interface_tools/search_index_data_interface.py`: 索引插入
- `off_task_tools/minio_downloader.py`: MinIO文件下载
- `off_task_tools/task_status_updater.py`: 任务状态更新

## 配置文件

- `config/mysql_conn_config.json`: MySQL连接配置
- `config/minio_config.json`: MinIO连接配置
- `config/<index_name>_config.json`: 索引配置文件
- `config/task_resource_config.json`: 任务资源配置

## 使用限制

1. Excel文件必须是 `.xlsx` 或 `.xls` 格式
2. 任务支持排队机制，当资源不足时会自动排队等待
3. 确保配置文件（MySQL、MinIO、索引）已正确配置

## 与原始脚本的差异

原始脚本 `insert_audit_excel.sh` 的主要差异：

1. **文件下载**: 新增了从远程存储下载文件的功能
2. **类目信息**: 新增了category_name和category_id参数支持（通过schema_trans处理）
3. **任务管理**: 集成到统一的任务管理系统，支持任务状态追踪
4. **日志管理**: 提供更详细的日志记录和阶段追踪
5. **错误处理**: 提供更完善的错误处理和回滚机制

## 注意事项

category信息的处理：
- 当前版本中，category_id 和 category_name 参数会传递给任务，但需要在 `schema_trans.py` 的 `trans_review_excel_to_json_file` 方法中支持这些参数
- 如果 `trans_review_excel_to_json_file` 尚未支持 category 参数，数据将不会包含类目信息
- 后续需要修改 `schema_trans.py` 以支持在 Excel 转 JSON 阶段添加 category 信息

