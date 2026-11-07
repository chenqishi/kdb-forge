# HTTP API

七服务按各自端口运行。以下接口以 `src/kdb/services/` 的实际请求模型和路由为准；FastAPI 服务可通过自身 `/docs`、`/openapi.json` 查看完整模型。启动方式见[运行配置](runtime_configuration.md)。

## 知识检索服务

入口 `kdb.services.retrieval.app`，默认端口 8003。

| 方法与路径 | 主要输入 | 输出与行为 |
|---|---|---|
| `POST /search` | `text`；可选 `top_k=100`、`index_names`、`condition_dicts`、`search_type=qa`、`data_type=text`、`use_synonyms=false` | `{results:[{id,q,a,score,…}]}` |
| `POST /web_search` | `text`、`index_names`、`client`、`page_num=1`、`page_size=10000`、条件与阈值 | `results`、`total_count`、`current_count` |
| `POST /insert` | `index_names`；标题、正文、类型、客户、类目、来源、审核及扩展字段；可选 `_id` | 写入，返回 `success`、`message` |
| `POST /delete` | `index_names`、`id`，可选 `refresh_imm` | 按 ID 删除 |
| `POST /get_value_collection` | `index_name`、`field_name`；可选 `size`、`include_doc_count`、`extra_query` | 字段聚合值与数量 |
| `POST /get_from_type_count` | 单个 `index_name`（兼容 `indexName`）、`from_type=chat_auto`、可选 `start/end` | `{success,count,message}`，严格原物理索引计数 |
| `POST /list_file_names` | `index_name`；可选 `keyword`、`size=200`、`from_type_norm` | 文件名列表、类型统计及数量 |
| `POST /preview_delete_by_file` | `index_name`、`file_names`，可选 `match_mode`、`data_types`、`audit_results`、`sample_size` | 只读，返回总数、文件分布、类型、样例与告警 |
| `POST /delete_by_file` | 与预览一致，去掉 `sample_size` | 写 JSONL 快照并软删，返回实际数量及 `snapshot_path` |
| `POST /update_by_condition` | `index_name`、`update_fields`、`conditions` | 条件 AND 更新；以实际 `success/message` 与后端结果判断 |
| `POST /modify_knowledge_direct_update` | `es_index`、`new_query_info`；可选旧知识、检索问题、`allow_insert` | 模型修改流程，返回是否有纠错及修改条目 |
| `POST /modify_knowledge` | 同上，需 `old_query_info`，可选 `write_db_id` | 模型召回/修改流程 |

检索示例：

```json
{"text":"如何查找帮助文档","index_names":"dedicated_test_index","top_k":10,"data_type":"qa"}
```

按文件删除的 `match_mode` 仅接受 `exact` 或 `fuzzy`，默认 exact，不回退到另一模式；默认覆盖 QA 与 segment，审核状态不限制。`sample_size` 为 0–50；先核对预览中的目标、类型及告警，再按明确范围执行真实软删。软删与 ID 硬删除语义不同。

计数的空索引返回 0；不接收通配符、多索引表达式或非法物理名。时间格式为不带时区的 `yyyy-MM-dd HH:mm:ss`，仅同时提供 start/end 时增加闭区间条件，不隐式添加审核或软删筛选。完整字段和异常语义见模型及函数契约。

## 配套服务

| 服务 | 接口 | 主要语义 |
|---|---|---|
| off_task | `/start_task`、`/task_info`、`/stop_task`、`/restart_task`、`/health`、`/task_access` | 排队、查询、停止、重启及成本估计，见[管道说明](pipelines.md) |
| crawler | `POST /process_params` | 接收抓取/处理参数，进入真实网页知识处理流程 |
| files | `GET|HEAD /<bucket>/<object_path>`、`POST /upload`、`POST /upload_from_url`、`GET /health` | 对象读取与上传；upload 为表单，upload_from_url 为 URL 拉取上传 |
| multilingual | `POST /lang_predict`、`GET /health` | fastText 与语言规则识别，需真实模型 |
| csat | `POST /csat_report`、`POST /inner_csat_report`、`POST /inner_external_user_id_map` | 满意度及用户映射查询 |
| fastgpt_proxy | `POST /search` | 请求 FastGPT chat/completions 上游，非 ES 检索入口 |

CSAT `/csat_report` 请求包含 `start_time`、`end_time`、`channel_type`、`client`、`timestamp`、`signature`；时间戳为 Unix 秒，签名为 `md5(secret + timestamp)`，允许时差 300 秒，可选 `include_chat_detail`。内部两个查询接口沿现有无签名协议，仅应置于相应的内部网络边界。用户映射请求含 `client/start_time/end_time`，可选 `user_id`。

SQL/LLM/ES/MinIO 失败与实际写入数量必须按具体接口和当前契约处理；离线返回示例不证明真实凭据、模型与后端已可用。
