# HTTP API

四个核心服务按各自端口运行，CSAT 位于独立 assistant-data-tools 项目。核心接口以 `src/kdb/entrypoints/http/` 的实际请求模型和路由为准；FastAPI 服务可通过自身 `/docs`、`/openapi.json` 查看完整模型。启动方式见[运行配置](runtime_configuration.md)。

## 知识检索服务

入口 `kdb.entrypoints.http.retrieval.app`，默认端口 8003。

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
| `POST /update_by_condition` | `index_name`、`update_fields`、`conditions` | 条件 AND 更新；`success=true` 时 `updated_count` 是实际更新条数，含同值写入；0 条也成功 |
| `POST /modify_knowledge_direct_update` | `es_index`、`new_query_info`；可选旧知识、检索问题、`allow_insert` | 模型修改流程，返回是否有纠错及修改条目 |
| `POST /modify_knowledge` | 同上，需 `old_query_info`，可选 `write_db_id` | 模型召回/修改流程 |

条件更新发生冲突、超时或不完整响应时返回 `success=false`，此时 `updated_count=0` 是未获得完整计数的占位值；`message` 提示可能已有部分写入，不代表全部未写入或已回滚。

检索示例：

```json
{"text":"如何查找帮助文档","index_names":"dedicated_test_index","top_k":10,"data_type":"qa"}
```

按文件删除的 `match_mode` 仅接受 `exact` 或 `fuzzy`，默认 exact，不回退到另一模式；默认覆盖 QA 与 segment，审核状态不限制。`sample_size` 为 0–50；先核对预览中的目标、类型及告警，再按明确范围执行真实软删。软删与 ID 硬删除语义不同。

计数的空索引返回 0；不接收通配符、多索引表达式或非法物理名。时间格式为不带时区的 `yyyy-MM-dd HH:mm:ss`，仅同时提供 start/end 时增加闭区间条件，不隐式添加审核或软删筛选。完整字段和异常语义见模型及函数契约。

## 业务本体

已落地的模块调用关系、校验顺序、事务及选取逻辑见 [业务本体实现说明](business_ontology_implementation.md)。

业务本体挂在同一检索服务（8003），复用 `kdb.shared.database.mysql`。写接口需内网访问或置于网关之后；沿用原服务的认证行为，本期不新增 token 体系。`data_json` 是完整文档，五个投影列只能由文档生成。

| 方法与路径 | 主要输入 | 输出与行为 |
|---|---|---|
| `POST /insert_ontology` | `data_json` 为对象或 JSON 对象字符串；`status` 默认 active | 201，`ontology` 为 meta，含 document_bytes，不返回 data_json，UUID4 hex、revision=1；同 `(client,product,name)` 未删行冲突 409，draft 也占业务键 |
| `POST /get_ontology` | body 中必填 `ontology_id`；query 保留 `view=full/document/outline`、`include_deleted=false` | full 含完整文档和紧凑 UTF-8 `document_bytes`；document 为顶层 `ontology_id/revision/document`；outline 只含类及属性大纲与计数 |
| `POST /list_ontologies` | 可选 `client/product/status/q`、`deep=0/1`、`include_deleted=false`、`page=1`、`page_size=100`（1–100） | `total/page/page_size/items`，列表不加载/返回 `data_json`；未传作用域=不过滤，空串=只看公用 |
| `POST /update_ontology` | body 中必填 `ontology_id`、完整 `data_json`、正整数 `revision`；可选 `status` | 整篇替换并 revision+1，回 meta；作用域不可变；改名检查同作用域业务键；旧 revision 返回 409/current_revision |
| `POST /update_ontology_status` | body 中必填 `ontology_id`、`status=draft/active`、正整数 `revision` | 仅改行状态，revision+1；同状态也 +1，不重写文档 |
| `POST /delete_ontology` | body 中必填 `ontology_id`，可选正整数 `revision` | 软删，回 `deleted=true` 及含 del_flag 的 meta；重复删除 200/本体已删除 且不再 +1；不存在 404 |
| `POST /select_ontology` | `client/product` 默认空串，可选精确 `name`、`include_document=true` | 只返回一行、不合并；客户行业→客户通用→行业→全局，限 active 未删行；无匹配为 200/ontology=null |
| `GET /ontology_meta` | 无 | 结构版本、枚举与上限；不初始化数据库连接 |

所有 ID 字段统一为 body 中的 `ontology_id`（32位小写 hex），不再从路径取值。列表筛选和分页仍用 query，默认每页100；分页范围由 service 单点校验，路由只解析类型，失败统一400“请求参数不合法”。旧 `/ontology` 路径不再注册。创建、更新、状态变更和删除统一返回元数据，详情/列表/选取使用明确的 Pydantic 模型描述字段；列表不补读文档计算字节数。

成功沿用 `{success:true,message:"",…}`；失败固定 `{success:false,code,message,details:[]}`，不加 `data` 包装。错误码：400 `ONTOLOGY_BAD_REQUEST`；404 `ONTOLOGY_NOT_FOUND`；409 `ONTOLOGY_NAME_CONFLICT/ONTOLOGY_REVISION_CONFLICT/ONTOLOGY_SCOPE_IMMUTABLE`；413 `ONTOLOGY_PAYLOAD_TOO_LARGE`；422 `ONTOLOGY_VALIDATION_FAILED/ONTOLOGY_RESERVED_FIELD/ONTOLOGY_SCHEMA_VERSION_UNSUPPORTED`；503 `ONTOLOGY_DB_UNAVAILABLE`；500 `ONTOLOGY_INTERNAL_ERROR`。数据库错误不会伪装成无匹配。错误处理器按匹配路由的 ontology tag 生效，支持代理 root_path，其他路由继续使用原处理器。

所有字符串值去首尾空白；client/product 必须原本就是小写，禁止静默 lower。类、属性、关系、枚举、枚举值、规则和术语名禁止点号与 ASCII 控制字符。节点名、别名与引用按 NFKC+casefold 比较，存储保留规范化后的原始拼写；引用不重写。条件必填和引用错误都有 JSON 路径，最多 50 条。行控制字段禁止出现在文档任何层，`extensions` 子树例外。文档硬上限 1MB，200KB 起记录 warning；根 llm_hints/extensions 各 64KB，节点 llm_hints 16KB。

外部可用 [JSON Schema](../src/kdb/retrieval/ontology/ontology.schema.json) 校验单节点结构，过 schema 不等于能入库：跨节点唯一性、引用、保留键、组合约束由服务端校验。三层完整种子在 [resources/ontology](../resources/ontology/)；导入请求需包装为 `{"data_json":文档,"status":"active或draft"}`。

select_ontology 不传 name 时，同层按 update_time DESC、id DESC 稳定选取；传 name 时按 MySQL 列排序规则精确匹配。只传 client，优先该客户 product='' 的通用行；仅有该客户行业行时返回最近维护的一条，`scope=client_product,fallback=true`。fallback 严格等于“选中行作用域不等于请求作用域”，因此精确匹配 `(client,'')` 时为 false。任何场景都不补类、不合并。draft 客户行继续占业务键，但 select_ontology 回落行业或全局。

列表关键词 q 按名称精确 100、别名精确 90、名称前缀 70、名称包含 50、其他命中 20 排序，再按更新时间/id 倒序。别名精确用 JSON_CONTAINS，拉丁大小写敏感；别名包含匹配不区分大小写。`!/%/_` 均按字面量搜索。deep=1 **额外 OR 匹配**整篇 JSON，能找到仅在内部字段出现的词；这是管理端全扫描功能，不应接入 LLM 热路径。

### 存储、迁移和克隆

先在目标库执行 [20261117_ontology.sql](../migrations/20261117_ontology.sql)，不写死库名；MySQL 8.0 默认 utf8mb4_0900_ai_ci，5.7 需改为 utf8mb4_unicode_ci。数据库仅 PRIMARY(id) 与 uk_ontology_id 唯一，业务键无唯一索引/生成列。判重在插入/整篇更新的同一事务中 FOR UPDATE，只看 del_flag=0；每个写事务显式使用 REPEATABLE READ，避免部署默认 READ COMMITTED 导致缺失键并发重复。死锁整笔重试一次；仍失败或锁等待超时返回 503。绕过接口裸写不受业务判重保护。

连接配置取 `KDB_MYSQL_CONFIG`，未设置时用项目 `config/mysql_conn_config.json`；每个进程懒加载一个共享 MySQLConnector，池大小沿用 5，连接归还前关闭游标，读写均设置会话 utf8mb4，写操作显式 commit/rollback。安装基础依赖包含 mysql-connector-python；元信息、导入模块和生成 schema 不创建连接。

```bash
python -m kdb.retrieval.ontology.schema --check
python -m kdb.entrypoints.cli.tools.ontology_clone \
  --source-client '' --source-product ecommerce \
  --target-client wayfair --status draft --dry-run
```

克隆直接调用 service，解析源文档后整篇复制、改作用域、重校验，默认 draft；去掉 --dry-run 才写入。target-product 缺省为请求的 source-product。退出码 0 成功、2 源不存在、3 目标已有业务键、4 校验失败、5 数据库不可用；错误 code/details 写 stderr。模板变更不自动传播到客户。

### v8 设计中相互矛盾处的实现口径

- §7.4 的 deep SQL 写成 AND，会排除文档内部独有关键词；按 §8.4“额外全文检索”实现 OR，并验证真实 SQL。
- §7.8 原 SQL 在 product='' 时排除客户行业行，与明确的 client-only 回落场景相反；仅这个请求场景放宽该客户的 product 条件，空 product 行仍优先。
- §8.8 示例表把只传 client 的精确通用命中标成 fallback=true；使用该节指定的 describe_scope 公式，精确命中为 false。
- INSERT 返回生成的 ontology_id（不是 None），供创建后回查；列表只映射元数据，按ID查询及作用域选取读取返回视图必需列；document 视图单独响应模型，删除响应保留 del_flag，避免被通用模型丢弃。
- 全量归一化补默认值后再次检查 1MB 上限，防止入参未超限但实际入库文档超限。行业种子移除 Wayfair 专属例子与固定退款时效。

测试和 13 步 HTTP 验收入口见[测试说明](testing.md)。本期没有元素级接口、ES 同步、embedding、继承合并或历史版本表。

## 配套服务

| 服务 | 接口 | 主要语义 |
|---|---|---|
| off_task | `/start_task`、`/task_info`、`/stop_task`、`/restart_task`、`/health`、`/task_access` | 排队、查询、停止、重启及成本估计，见[管道说明](pipelines.md) |
| files | `GET|HEAD /<bucket>/<object_path>`、`POST /upload`、`POST /upload_from_url`、`GET /health` | 对象读取与上传；upload 为表单，upload_from_url 为 URL 拉取上传 |
| multilingual | `POST /lang_predict`、`GET /health` | fastText 与语言规则识别，需真实模型 |
| csat（独立项目） | `POST /csat_report`、`POST /inner_csat_report`、`POST /inner_external_user_id_map` | 满意度及用户映射查询 |

CSAT `/csat_report` 请求包含 `start_time`、`end_time`、`channel_type`、`client`、`timestamp`、`signature`；时间戳为 Unix 秒，签名为 `md5(secret + timestamp)`，允许时差 300 秒，可选 `include_chat_detail`。内部两个查询接口沿现有无签名协议，仅应置于相应的内部网络边界。用户映射请求含 `client/start_time/end_time`，可选 `user_id`。

SQL/LLM/ES/MinIO 失败与实际写入数量必须按具体接口和当前契约处理；离线返回示例不证明真实凭据、模型与后端已可用。
